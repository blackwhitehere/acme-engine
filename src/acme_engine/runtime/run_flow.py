"""
Minimal runtime to import and execute a Python callable by import path.

This is intended to run inside the ECS container. It accepts:
- --target: dotted import path to a callable (e.g., package.module:function)
- --args: JSON array of positional args
- --kwargs: JSON object of keyword args

Exit code is non-zero on failures; errors are logged to stderr.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
from typing import Any, Callable


def _import_callable(path: str) -> Callable[..., Any]:
    if ":" in path:
        module_name, attr = path.split(":", 1)
    elif "." in path:
        # Support package.module.callable form
        parts = path.rsplit(".", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid target import path: {path}")
        module_name, attr = parts
    else:
        raise ValueError(
            "Target must be in 'pkg.module:callable' or 'pkg.module.callable' form"
        )
    mod = importlib.import_module(module_name)
    try:
        func = getattr(mod, attr)
    except AttributeError as e:
        raise ImportError(f"Callable '{attr}' not found in module '{module_name}'") from e
    if not callable(func):
        raise TypeError(f"Imported object is not callable: {path}")
    return func


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Python callable by import path")
    parser.add_argument("--target", required=True, help="Import path to callable, e.g. pkg.mod:func")
    parser.add_argument("--args", default="[]", help="JSON array of positional args")
    parser.add_argument("--kwargs", default="{}", help="JSON object of keyword args")

    ns = parser.parse_args(argv)
    try:
        args = json.loads(ns.args)
        kwargs = json.loads(ns.kwargs)
        if not isinstance(args, list):
            raise ValueError("--args must be a JSON array")
        if not isinstance(kwargs, dict):
            raise ValueError("--kwargs must be a JSON object")
    except json.JSONDecodeError as e:
        print(f"Invalid JSON for args/kwargs: {e}", file=sys.stderr)
        return 2

    try:
        func = _import_callable(ns.target)
    except Exception as e:
        print(f"Failed to import target: {e}", file=sys.stderr)
        return 3

    try:
        result = func(*args, **kwargs)
        # If coroutine, run it
        if hasattr(result, "__await__"):
            import asyncio

            result = asyncio.run(result)  # type: ignore[arg-type]
        # Print result for logging/debugging
        if result is not None:
            print(json.dumps({"result": result}, default=str))
        return 0
    except Exception as e:
        print(f"Error while running target: {e}", file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
