import json

from acme_engine.runtime.run_flow import _import_callable, main


def sample_func(x, y=1):
    return x + y


def test_import_callable_colon(monkeypatch):
    # Inject the function into a dummy module namespace
    import types

    dummy = types.ModuleType("dummy_mod")
    dummy.sample_func = sample_func
    import sys as _sys

    _sys.modules["dummy_mod"] = dummy
    func = _import_callable("dummy_mod:sample_func")
    assert func is sample_func


ess_run_called = []


def test_main_executes_function(monkeypatch):
    import types
    import sys

    dummy = types.ModuleType("dummy_mod2")

    def f(a, b=2):
        return {"sum": a + b}

    dummy.f = f
    sys.modules["dummy_mod2"] = dummy
    code = main([
        "--target",
        "dummy_mod2:f",
        "--args",
        json.dumps([3]),
        "--kwargs",
        json.dumps({"b": 4}),
    ])
    assert code == 0
