# Functorial Kit Local Patch (v1)

- Status: `LOCAL_PATCH_ACTIVE`
- Kit checkout: `/Users/wangyiliang/Desktop/functorial-kit`
- Base commit: `785ff25e201c9eae84c862e68e786bc975e7a800`
- Patched surfaces:
  - `python/functorial_kit/arch/gates.py`
  - `python/functorial_kit/arch/scan.py`
  - `python/tests/test_arch.py`

## Purpose

The v0 scanner documented path-based configuration but did not scan a Python
file listed directly in `core_paths` or `shell_paths`. It also treated a nested
shell path as core when a parent directory was listed in `core_paths`.

The local patch adds:

1. single-file path scanning;
2. shell-path precedence over an enclosing core path;
3. same-line `kit:boundary` exemption for import-direction;
4. focused kit tests for all three behaviors.

## Validation

```text
uv run --no-sync \
  --with pytest --with hypothesis \
  --with-editable /Users/wangyiliang/Desktop/functorial-kit/python \
  python -m pytest -q -p no:cacheprovider \
  /Users/wangyiliang/Desktop/functorial-kit/python/tests
```

Observed result:

```text
43 passed in 2.45s
```

## Project impact

This patch is required to classify MRW nested adapter directories and shell
composition roots accurately. It must be upstreamed before depending on this
checkout outside the local machine.
