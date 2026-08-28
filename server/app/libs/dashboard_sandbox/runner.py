"""Isolated child process for a deliberately small, read-only Python subset."""

from __future__ import annotations

import ast
import io
import json
import sys
import traceback
from types import SimpleNamespace


_BANNED_NODES = (
    ast.AsyncFor,
    ast.AsyncFunctionDef,
    ast.AsyncWith,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Import,
    ast.Lambda,
    ast.Match,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    ast.With,
    ast.Yield,
    ast.YieldFrom,
)
_BANNED_CALLS = {
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "memoryview",
    "object",
    "open",
    "setattr",
    "super",
    "type",
    "vars",
    "__import__",
}
# Method names whose format-string syntax resolves attributes at runtime and
# would bypass the AST attribute checks below; f-strings stay available.
_BANNED_METHOD_CALLS = {
    "format",
    "format_map",
}
_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


class CodeValidationError(Exception):
    """Static safety validation failure."""

    def __init__(self, message: str, *, line: int | None = None):
        super().__init__(message)
        self.message = message
        self.line = line


class _SafetyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.run_definitions = 0

    def generic_visit(self, node: ast.AST) -> None:
        if isinstance(node, _BANNED_NODES):
            raise CodeValidationError(
                f"{type(node).__name__} is not allowed",
                line=getattr(node, "lineno", None),
            )
        super().generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module != "opendesk" or node.level != 0:
            raise CodeValidationError(
                "Only imports from opendesk are allowed",
                line=node.lineno,
            )
        allowed = {"context", "filters", "query"}
        if any(alias.name not in allowed or alias.asname for alias in node.names):
            raise CodeValidationError(
                "Only opendesk context, filters, and query can be imported",
                line=node.lineno,
            )

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node.name != "run":
            raise CodeValidationError(
                "Only the run function can be defined",
                line=node.lineno,
            )
        if node.decorator_list or node.args.args or node.args.posonlyargs or node.args.kwonlyargs:
            raise CodeValidationError(
                "run() must not define arguments or decorators",
                line=node.lineno,
            )
        if node.args.vararg or node.args.kwarg:
            raise CodeValidationError("run() must not define arguments", line=node.lineno)
        self.run_definitions += 1
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise CodeValidationError(
                "Private attributes are not allowed",
                line=node.lineno,
            )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id.startswith("__"):
            raise CodeValidationError("Private names are not allowed", line=node.lineno)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _BANNED_CALLS:
            raise CodeValidationError(
                f"{node.func.id}() is not allowed",
                line=node.lineno,
            )
        if isinstance(node.func, ast.Attribute) and node.func.attr in _BANNED_METHOD_CALLS:
            raise CodeValidationError(
                f"{node.func.attr}() is not allowed; use f-strings instead",
                line=node.lineno,
            )
        self.generic_visit(node)


def validate_code(code: str) -> ast.Module:
    """Parse and validate component source without executing it."""
    try:
        tree = ast.parse(code, filename="<dashboard-component>", mode="exec")
    except SyntaxError as exc:
        raise CodeValidationError("Invalid Python syntax", line=exc.lineno) from exc
    visitor = _SafetyVisitor()
    visitor.visit(tree)
    if visitor.run_definitions != 1:
        raise CodeValidationError("Component code must define exactly one run() function")
    return tree


class _ReadOnlyMapping(dict):
    """Dictionary with convenient attribute reads for product context."""

    def __getattr__(self, name: str) -> object:
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("Context is read-only")


class _QueryProxy:
    def __init__(self) -> None:
        self._next_id = 1

    def _call(self, method: str, params: dict) -> object:
        request_id = self._next_id
        self._next_id += 1
        _write_protocol(
            {
                "type": "query",
                "id": request_id,
                "method": method,
                "params": params,
            }
        )
        line = sys.stdin.readline()
        if not line:
            raise RuntimeError("Query channel closed")
        response = json.loads(line)
        if response.get("id") != request_id:
            raise RuntimeError("Invalid query response")
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error") or "Query failed"))
        return response.get("result")

    def count(self, **kwargs: object) -> object:
        return self._call("count", kwargs)

    def group_by(self, **kwargs: object) -> object:
        return self._call("group_by", kwargs)

    def timeseries(self, **kwargs: object) -> object:
        return self._call("timeseries", kwargs)

    def list(self, **kwargs: object) -> object:
        return self._call("list", kwargs)


def _write_protocol(payload: dict) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def _safe_import(
    name: str,
    globals_: dict | None = None,
    locals_: dict | None = None,
    fromlist: tuple | list = (),
    level: int = 0,
) -> object:
    del globals_, locals_, fromlist
    if name != "opendesk" or level != 0:
        raise ImportError("Only opendesk can be imported")
    return _OPEN_DESK_MODULE


def _safe_error(exc: BaseException) -> tuple[str, int | None]:
    extracted = traceback.extract_tb(exc.__traceback__)
    line = next(
        (frame.lineno for frame in reversed(extracted) if frame.filename == "<dashboard-component>"),
        None,
    )
    message = str(exc).replace("\n", " ")[:500] or type(exc).__name__
    return message, line


def _run(payload: dict) -> None:
    global _OPEN_DESK_MODULE
    tree = validate_code(str(payload.get("code") or ""))
    context = _ReadOnlyMapping(payload.get("context") or {})
    filters = _ReadOnlyMapping(payload.get("filters") or {})
    query = _QueryProxy()
    _OPEN_DESK_MODULE = SimpleNamespace(
        context=context,
        filters=filters,
        query=SimpleNamespace(tickets=query),
    )
    log_buffer = io.StringIO()

    def safe_print(*values: object, sep: str = " ", end: str = "\n") -> None:
        print(*values, sep=sep, end=end, file=log_buffer)

    builtins = {**_SAFE_BUILTINS, "__import__": _safe_import, "print": safe_print}
    namespace = {"__builtins__": builtins}
    compiled = compile(tree, "<dashboard-component>", "exec")
    exec(compiled, namespace, namespace)
    output = namespace["run"]()
    json.dumps(output, ensure_ascii=False, allow_nan=False)
    _write_protocol({"type": "result", "result": output, "logs": log_buffer.getvalue()})


_OPEN_DESK_MODULE: object = None


def main() -> None:
    """Read one invocation and serve query RPC until run() completes."""
    try:
        line = sys.stdin.readline()
        if not line:
            raise RuntimeError("Missing sandbox input")
        _run(json.loads(line))
    except CodeValidationError as exc:
        _write_protocol(
            {
                "type": "error",
                "code": "unsafe_code",
                "message": exc.message,
                "line": exc.line,
            }
        )
    except BaseException as exc:
        message, line = _safe_error(exc)
        _write_protocol(
            {
                "type": "error",
                "code": "runtime_error",
                "message": message,
                "line": line,
            }
        )


if __name__ == "__main__":
    main()
