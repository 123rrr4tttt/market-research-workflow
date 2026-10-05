from .failure import Failure, FailureFamily

"""Canonical form: JCS restricted to the safe-integer subset (see CONVENTIONS.md)."""
codec_failures: FailureFamily
SAFE_MAX: int
def code_unit_key(s: str) -> bytes:
    """Sort key equal to UTF-16 code-unit order (JCS key order)."""
    ...

def escape_string(s: str) -> str:
    ...

def canonicalize(value: object, path: str = ...) -> str | Failure:
    ...

def sha256_hex(utf8: str) -> str:
    ...

def digest_of(value: object) -> str | Failure:
    ...
