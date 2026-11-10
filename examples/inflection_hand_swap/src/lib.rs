//! `dasherize` from inflection, hand-ported to Rust and exposed to Python as `inflection_rs._rust`.

use pyo3::prelude::*;
use pyo3::types::{PyBytes, PyString};

/// Replace every underscore with a dash in UTF-8 text.
///
/// Works on bytes rather than `&str` because a Python `str` can hold lone surrogates, which a
/// Rust `&str` cannot; Python encodes them with `surrogatepass` and they come back unchanged.
/// An underscore is the single byte 0x5F, which never occurs inside a multi-byte sequence.
pub fn dasherize(word: &[u8]) -> Vec<u8> {
    word.iter()
        .map(|&byte| if byte == b'_' { b'-' } else { byte })
        .collect()
}

// The docstring is the original's `__doc__`, which Python 3.13 and later store without its
// indentation, so the original doctest runs against this function under the same test id.
#[pyfunction(name = "dasherize")]
#[doc = "Replace underscores with dashes in the string.\n\nExample::\n\n    >>> dasherize(\"puni_puni\")\n    'puni-puni'\n\n"]
fn dasherize_python<'py>(word: &Bound<'py, PyString>) -> PyResult<Bound<'py, PyString>> {
    let python = word.py();
    let encoded = word.call_method1("encode", ("utf-8", "surrogatepass"))?;
    let dasherized = dasherize(encoded.cast::<PyBytes>()?.as_bytes());
    PyString::from_encoded_object(
        &PyBytes::new(python, &dasherized),
        Some(c"utf-8"),
        Some(c"surrogatepass"),
    )
}

#[pymodule]
fn _rust(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let function = wrap_pyfunction!(dasherize_python, module)?;
    // doctest only collects a built-in whose `__module__` is the package it is found in.
    function.setattr("__module__", "inflection_rs")?;
    module.add_function(function)
}

#[cfg(test)]
mod tests {
    use super::dasherize;

    #[test]
    fn underscores_become_dashes() {
        assert_eq!(dasherize(b"puni_puni"), b"puni-puni");
    }

    #[test]
    fn text_without_underscores_is_unchanged() {
        assert_eq!(dasherize(b"puni-puni puni"), b"puni-puni puni");
    }

    #[test]
    fn multi_byte_characters_are_kept() {
        let word = "caf\u{e9}_\u{1f600}_x";
        assert_eq!(
            dasherize(word.as_bytes()),
            "caf\u{e9}-\u{1f600}-x".as_bytes()
        );
    }

    #[test]
    fn surrogatepass_bytes_are_kept() {
        // b"\xed\xb0\x80" is how Python encodes the lone surrogate "\udc00" with surrogatepass.
        assert_eq!(dasherize(b"a_\xed\xb0\x80"), b"a-\xed\xb0\x80");
    }
}
