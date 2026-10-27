"""Load the pure core of roost as a package, without running __init__.py (which needs Home Assistant)."""
import importlib
import os
import sys
import types

_DIR = os.path.join(os.path.dirname(__file__), "..", "custom_components", "roost_quatt")


def load(name: str):
    if "roost" not in sys.modules:
        pkg = types.ModuleType("roost")
        pkg.__path__ = [os.path.abspath(_DIR)]
        sys.modules["roost"] = pkg
    return importlib.import_module(f"roost.{name}")


def run_all(namespace: dict) -> None:
    """Run the test_ functions of a module without pytest: python3 tests/test_x.py"""
    failed = 0
    tests = [(n, f) for n, f in namespace.items() if n.startswith("test_") and callable(f)]
    for n, f in tests:
        try:
            f()
            print(f"ok    {n}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {n}: {type(e).__name__}: {e}")
    print(f"{len(tests) - failed}/{len(tests)} passed")
    if failed:
        raise SystemExit(1)
