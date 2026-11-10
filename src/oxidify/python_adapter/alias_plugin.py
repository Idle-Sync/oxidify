"""pytest plugin that makes `import <name>` give the Rust-backed `<name>_rs` package.

Loaded with `-p` from a folder outside the checkout, before any test module is imported. The
names to alias come from `OXIDIFY_ALIASED_IMPORT_NAMES`, separated by spaces. It runs in the
port environment, so it imports nothing from oxidify.
"""

import importlib
import os
import sys

for import_name in os.environ["OXIDIFY_ALIASED_IMPORT_NAMES"].split():
    sys.modules[import_name] = importlib.import_module(f"{import_name}_rs")
