"""Import graph, swap order, coverage and unsupported constructs of the original."""

import ast
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from oxidify import port_folder as paths
from oxidify.state import FORMAT_VERSION, new_coverage_map, read_state, write_state

SCRIPTS_FOLDER = Path(__file__).parent / "analysis_scripts"
NOT_YET_PORTED = "not yet ported"
DATA_NOT_A_CALL_PATH = "data, not a call path"
# Builtins reported when called by bare name (`re.compile` is not the builtin).
UNSUPPORTED_BUILTINS = {"eval", "exec", "compile", "__import__"}
REGEX_FUNCTIONS = {
    "compile",
    "match",
    "search",
    "sub",
    "subn",
    "split",
    "findall",
    "finditer",
    "fullmatch",
}
NAMESPACE_WRITE_METHODS = {"update", "setdefault", "pop", "popitem", "clear"}
INLINE_FLAGS = re.compile(r"\(\?([aiLmsux]+)[:)]")


class AnalysisFailed(Exception):
    """A step of the source analysis could not run or its command failed."""


def run_in_port_environment(
    port_folder: Path, arguments: list[str], working_folder: Path, extra_env: dict[str, str]
) -> str:
    """Run a command on the port environment's interpreter and return its standard output.

    Bytecode caches are switched off because the working folder may be the read-only checkout.
    """
    venv_python = paths.venv_python(port_folder)
    if not venv_python.exists():
        raise AnalysisFailed(f"{venv_python} does not exist; run prepare_environment first")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **extra_env}
    command = [str(venv_python), *arguments]
    result = subprocess.run(command, cwd=working_folder, env=env, capture_output=True, text=True)
    if result.returncode != 0:
        output = (result.stdout + result.stderr).strip()[-2000:]
        raise AnalysisFailed(f"{' '.join(command)} exited {result.returncode}: {output}")
    return result.stdout


def read_import_graph(port_folder: Path, import_names: list[str]) -> dict[str, Any]:
    script = str(SCRIPTS_FOLDER / "import_graph.py")
    output = run_in_port_environment(port_folder, [script, *import_names], port_folder, {})
    return json.loads(output)


def read_public_names(port_folder: Path, modules: list[str]) -> dict[str, dict[str, bool]]:
    """Public names of each module, each mapped to whether it is callable."""
    script = str(SCRIPTS_FOLDER / "public_names.py")
    output = run_in_port_environment(port_folder, [script, *modules], port_folder, {})
    return json.loads(output)


def swap_order_groups(modules: list[str], edges: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Strongly connected components of the import graph, each after the groups it imports.

    Tarjan's algorithm emits a component only after every component reachable from it, which
    is the leaf-first order the port needs. A component of more than one module is coupled.
    """
    imports: dict[str, list[str]] = {module: [] for module in modules}
    for edge in edges:
        imports[edge["importer"]].append(edge["imported"])

    index_of: dict[str, int] = {}
    lowest_reachable: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    groups: list[dict[str, Any]] = []

    def visit(module: str) -> None:
        index_of[module] = lowest_reachable[module] = len(index_of)
        stack.append(module)
        on_stack.add(module)
        for imported in sorted(imports[module]):
            if imported not in index_of:
                visit(imported)
                lowest_reachable[module] = min(lowest_reachable[module], lowest_reachable[imported])
            elif imported in on_stack:
                lowest_reachable[module] = min(lowest_reachable[module], index_of[imported])
        if lowest_reachable[module] != index_of[module]:
            return
        members = []
        while True:
            member = stack.pop()
            on_stack.remove(member)
            members.append(member)
            if member == module:
                break
        groups.append({"modules": sorted(members), "coupled": len(members) > 1})

    for module in sorted(modules):
        if module not in index_of:
            visit(module)
    return groups


def measure_coverage(
    port_folder: Path, import_names: list[str], modules: list[dict[str, str]]
) -> dict[str, float]:
    """Run the port's tests under coverage.py against the original; percent covered per module."""
    port = read_state(paths.port_json_path(port_folder), "port")
    test_command = port["test_command"]
    if test_command[0] != "python":
        raise AnalysisFailed(f"test_command must start with python, got {test_command[0]!r}")
    data_file = paths.coverage_data_path(port_folder)
    data_file.parent.mkdir(parents=True, exist_ok=True)
    environment = {"COVERAGE_FILE": str(data_file)}
    checkout = paths.checkout_folder(port_folder)
    # No pytest cache folder: it would be written into the checkout.
    run_in_port_environment(
        port_folder,
        [
            "-m",
            "coverage",
            "run",
            f"--source={','.join(import_names)}",
            *test_command[1:],
            *port["test_paths"],
            "-p",
            "no:cacheprovider",
        ],
        checkout,
        environment,
    )
    report = run_in_port_environment(
        port_folder,
        ["-m", "coverage", "json", "-o", "-"],
        port_folder,
        environment,
    )
    percent_by_file = {
        file: details["summary"]["percent_covered"]
        for file, details in json.loads(report)["files"].items()
    }
    percent_by_module = {}
    for module in modules:
        for file, percent in percent_by_file.items():
            if file == module["file"] or file.endswith("/" + module["file"]):
                percent_by_module[module["name"]] = round(percent, 2)
    for module in modules:
        if module["name"] not in percent_by_module:
            raise AnalysisFailed(f"coverage.py reported nothing for {module['name']}")
    return percent_by_module


def regex_features(pattern: str, verbose_flag: bool) -> list[str]:
    """Features of a pattern whose meaning differs between Python's `re` and the Rust `regex`."""
    escaped_characters = set()
    index = 0
    while index < len(pattern):
        if pattern[index] == "\\" and index + 1 < len(pattern):
            escaped_characters.add(pattern[index + 1])
            index += 2
        else:
            index += 1
    inline_flags = "".join(INLINE_FLAGS.findall(pattern))
    before_dollar = pattern[:-1]
    backslashes_before_dollar = len(before_dollar) - len(before_dollar.rstrip("\\"))

    features = []
    if any(opening in pattern for opening in ("(?=", "(?!", "(?<=", "(?<!")):
        features.append("lookaround")
    if "(?P=" in pattern or any(character in escaped_characters for character in "123456789"):
        features.append("backreference")
    if "Z" in escaped_characters:
        features.append("end_of_string_Z")
    if "i" in inline_flags:
        features.append("inline_ignore_case")
    if pattern.endswith("$") and backslashes_before_dollar % 2 == 0:
        features.append("trailing_dollar")
    if escaped_characters & set("wWbB"):
        features.append("word_class_or_boundary")
    if verbose_flag or "x" in inline_flags:
        features.append("verbose")
    return features


def is_name(node: ast.expr, name: str) -> bool:
    return isinstance(node, ast.Name) and node.id == name


def namespace_call_kind(node: ast.expr) -> str | None:
    """`globals_write` or `locals_write` when the node is a call to globals() or locals()."""
    if not isinstance(node, ast.Call):
        return None
    for function in ("globals", "locals"):
        if is_name(node.func, function):
            return f"{function}_write"
    return None


def uses_verbose_flag(call: ast.Call) -> bool:
    flag_expressions = [*call.args[1:], *[keyword.value for keyword in call.keywords]]
    for expression in flag_expressions:
        for node in ast.walk(expression):
            if isinstance(node, ast.Attribute) and node.attr in ("VERBOSE", "X"):
                return True
    return False


def regex_pattern_entry(call: ast.Call, module: str, file: str) -> dict[str, Any] | None:
    """Description of a `re.<function>(pattern, ...)` call, or None when the call is not one."""
    function = call.func
    if not (isinstance(function, ast.Attribute) and is_name(function.value, "re")):
        return None
    if function.attr not in REGEX_FUNCTIONS or not call.args:
        return None
    entry: dict[str, Any] = {"module": module, "file": file, "line": call.lineno}
    pattern = call.args[0]
    if isinstance(pattern, ast.Constant) and isinstance(pattern.value, str):
        entry["pattern"] = pattern.value
        entry["features"] = regex_features(pattern.value, uses_verbose_flag(call))
    else:
        entry["pattern"] = None
        entry["features"] = ["built_at_runtime"]
    return entry


def construct_entry(node: ast.AST, module_level: bool) -> str | None:
    """Kind of unsupported construct the node is, or None."""
    if isinstance(node, ast.Call):
        function = node.func
        if isinstance(function, ast.Name) and function.id in UNSUPPORTED_BUILTINS:
            return function.id
        if is_name(function, "import_module"):
            return "import_module"
        if isinstance(function, ast.Attribute) and function.attr == "import_module":
            return "import_module"
        if isinstance(function, ast.Attribute) and function.attr in NAMESPACE_WRITE_METHODS:
            return namespace_call_kind(function.value)
    if isinstance(node, ast.ClassDef):
        if any(keyword.arg == "metaclass" for keyword in node.keywords):
            return "metaclass"
    if isinstance(node, ast.FunctionDef) and node.name == "__getattr__" and module_level:
        return "module_getattr"
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
        targets = node.targets if not isinstance(node, ast.AugAssign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Subscript):
                return namespace_call_kind(target.value)
    return None


def scan_source(
    source: str, file: str, module: str
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Unsupported constructs and `re` patterns found in one source file, in line order."""
    tree = ast.parse(source)
    module_level_nodes = set(tree.body)
    constructs = []
    patterns = []
    nodes = sorted(
        ast.walk(tree),
        key=lambda item: (getattr(item, "lineno", 0), getattr(item, "col_offset", 0)),
    )
    for node in nodes:
        kind = construct_entry(node, node in module_level_nodes)
        if kind is not None:
            constructs.append(
                {"kind": kind, "module": module, "file": file, "line": getattr(node, "lineno", 0)}
            )
        if isinstance(node, ast.Call):
            entry = regex_pattern_entry(node, module, file)
            if entry is not None:
                patterns.append(entry)
    return constructs, patterns


def write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def analyse_source(port_folder: Path) -> None:
    """Write the analysis files under `<port>/analysis/` and the initial coverage map.

    Everything is computed before anything is written, so a failing test command leaves no
    analysis file behind.
    """
    port = read_state(paths.port_json_path(port_folder), "port")
    graph = read_import_graph(port_folder, port["import_names"])
    module_names = [module["name"] for module in graph["modules"]]
    callable_by_name = read_public_names(port_folder, module_names)
    percent_by_module = measure_coverage(port_folder, port["import_names"], graph["modules"])

    constructs = []
    patterns = []
    for module in graph["modules"]:
        source = Path(module["path"]).read_text()
        module_constructs, module_patterns = scan_source(source, module["file"], module["name"])
        constructs += module_constructs
        patterns += module_patterns

    coverage_map = new_coverage_map(
        {module: list(names) for module, names in callable_by_name.items()}
    )
    for module, names in callable_by_name.items():
        coverage_map["modules"][module]["coverage_percent"] = percent_by_module[module]
        for name, is_callable in names.items():
            reason = NOT_YET_PORTED if is_callable else DATA_NOT_A_CALL_PATH
            coverage_map["modules"][module]["public_names"][name]["reason"] = reason

    header = {"format_version": FORMAT_VERSION}
    write_json_file(
        paths.import_graph_path(port_folder),
        {**header, "modules": module_names, "edges": graph["edges"]},
    )
    write_json_file(
        paths.swap_order_path(port_folder),
        {**header, "groups": swap_order_groups(module_names, graph["edges"])},
    )
    write_json_file(paths.coverage_path(port_folder), {**header, "modules": percent_by_module})
    write_json_file(
        paths.unsupported_path(port_folder),
        {**header, "constructs": constructs, "regex_patterns": patterns},
    )
    write_state(paths.coverage_map_path(port_folder), "coverage_map", coverage_map)
