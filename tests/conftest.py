"""Bootstrap so the extension's own modules can be imported and exercised
without a running LNbits instance or database.

``_lnbits_stub`` registers fake ``lnbits.*`` modules (a real LNbits install is
not required), and an in-memory CRUD (``_inmem_crud``) is registered as
``events.crud``.

pytest imports this conftest as part of the ``events.tests`` package, which
means the extension package (and its DB-backed ``events.crud``) may already be
in ``sys.modules``.  The data layer is therefore dropped and rebuilt after the
stub is in place, so that ``events.services`` -- whose ``from .crud import ...``
bindings resolve at import time -- talks to the in-memory store.
"""
import importlib.util
import sys
import types
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO_DIR = TESTS_DIR.parent

for _p in (str(TESTS_DIR), str(REPO_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load(name, filename):
    """Load a helper module from this directory under an explicit name."""
    spec = importlib.util.spec_from_file_location(name, TESTS_DIR / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# If the ``events`` package is not importable as a package yet, register a
# lightweight one so the heavy ``events/__init__`` (routers, DB) is not executed.
if "events" not in sys.modules:
    _pkg = types.ModuleType("events")
    _pkg.__path__ = [str(REPO_DIR)]
    _pkg.__package__ = "events"
    sys.modules["events"] = _pkg

# 1. fake lnbits.* modules, registered before any extension module is rebuilt.
_lnbits_stub = _load("_lnbits_stub", "_lnbits_stub.py")  # noqa: F841

# 2. rebuild the data layer against the stub + the in-memory store.  Only the
#    modules that bind crud are rebuilt: `events.models` is pure pydantic and
#    is kept as-is (re-executing it would trip pydantic's duplicate-validator
#    guard for the same qualified names).
for _mod in ("events.services", "events.crud"):
    sys.modules.pop(_mod, None)

import events.models  # noqa: E402,F401

_inmem_crud = _load("events.crud", "_inmem_crud.py")
# `from events import crud` resolves the package attribute, not sys.modules, so
# rebind it explicitly (the original DB-backed crud is still the attribute).
sys.modules["events"].crud = _inmem_crud

import events.services  # noqa: E402,F401


@pytest.fixture(autouse=True)
def _clean_store():
    """Give every test an empty in-memory store."""
    _inmem_crud.reset()
    yield
    _inmem_crud.reset()
