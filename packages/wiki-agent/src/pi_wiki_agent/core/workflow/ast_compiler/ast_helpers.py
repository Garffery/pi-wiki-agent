"""
AST node factory functions.

Thin, composable helpers for building Python AST nodes. Every function
returns a fresh node — never reuse nodes across different positions in the tree.
"""
from __future__ import annotations

import ast
from typing import Any

# ============================================================================
# Names & Constants
# ============================================================================


def name(id: str) -> ast.Name:
    """Build a name reference (Load context): ``foo`` (reading)."""
    return ast.Name(id=id, ctx=ast.Load())


def constant(value: Any) -> ast.Constant:
    """Build a constant: ``'str'``, ``42``, ``True``."""
    # ast.Constant handles str/int/float/bool/None/bytes/complex/ellipsis
    return ast.Constant(value=value)


def none() -> ast.Constant:
    """Build ``None``."""
    return ast.Constant(value=None)


# ============================================================================
# Expressions
# ============================================================================


def call(func: ast.expr, args: list[ast.expr] | None = None,
         keywords: list[ast.keyword] | None = None) -> ast.Call:
    """Build a function call: ``func(arg1, arg2, kw=val)``."""
    return ast.Call(func=func, args=args or [], keywords=keywords or [])


def call_fn(fn_name: str, args: list[ast.expr] | None = None,
            keywords: list[ast.keyword] | None = None) -> ast.Call:
    """Build a named function call: ``fn_name(arg1, arg2)``."""
    return ast.Call(func=name(fn_name), args=args or [], keywords=keywords or [])


def method(obj: ast.expr, method_name: str,
           args: list[ast.expr] | None = None) -> ast.Call:
    """Build a method call: ``obj.method(arg1, arg2)``."""
    return ast.Call(
        func=ast.Attribute(value=obj, attr=method_name),
        args=args or [],
        keywords=[],
    )


def get(obj: ast.expr, key: str | ast.expr,
        default: ast.expr | None = None) -> ast.Call:
    """Build a ``.get(key)`` call: ``d.get('key')`` or ``d.get('key', default)``."""
    key_expr = constant(key) if isinstance(key, str) else key
    args = [key_expr] if default is None else [key_expr, default]
    return method(obj, "get", args)


def await_expr(expr: ast.expr) -> ast.Await:
    """Build an await expression: ``await expr``."""
    return ast.Await(value=expr)


def subscript(obj: ast.expr, key: ast.expr) -> ast.Subscript:
    """Build a subscript: ``obj[key]`` (Load context)."""
    return ast.Subscript(value=obj, slice=key, ctx=ast.Load())


def attribute(obj: ast.expr, attr: str) -> ast.Attribute:
    """Build an attribute access: ``obj.attr`` (Load context)."""
    return ast.Attribute(value=obj, attr=attr, ctx=ast.Load())


def or_expr(left: ast.expr, right: ast.expr) -> ast.BoolOp:
    """Build a boolean OR: ``left or right``."""
    return ast.BoolOp(op=ast.Or(), values=[left, right])


def is_not_none(expr: ast.expr) -> ast.Compare:
    """Build comparison: ``expr is not None``."""
    return ast.Compare(
        left=expr,
        ops=[ast.IsNot()],
        comparators=[constant(None)],
    )


def is_none(expr: ast.expr) -> ast.Compare:
    """Build comparison: ``expr is None``."""
    return ast.Compare(
        left=expr,
        ops=[ast.Is()],
        comparators=[constant(None)],
    )


def ternary(cond: ast.expr, true_val: ast.expr, false_val: ast.expr) -> ast.IfExp:
    """Build a ternary expression: ``true_val if cond else false_val``."""
    return ast.IfExp(test=cond, body=true_val, orelse=false_val)


def equals(left: ast.expr, right: ast.expr) -> ast.Compare:
    """Build comparison: ``left == right``."""
    return ast.Compare(left=left, ops=[ast.Eq()], comparators=[right])


def not_equals(left: ast.expr, right: ast.expr) -> ast.Compare:
    """Build comparison: ``left != right``."""
    return ast.Compare(left=left, ops=[ast.NotEq()], comparators=[right])


def isinstance_expr(obj: ast.expr, type_name: str) -> ast.Call:
    """Build: ``isinstance(obj, type_name)``."""
    return call_fn("isinstance", [obj, name(type_name)])


# ============================================================================
# Statements
# ============================================================================


def assign(target: str | ast.expr, value: ast.expr) -> ast.Assign:
    """Build an assignment: ``target = value``.

    ``target`` can be a string (variable name) or an AST expression (subscript, attribute, etc.).
    """
    if isinstance(target, str):
        tgt = ast.Name(id=target, ctx=ast.Store())
    else:
        tgt = target
    return ast.Assign(targets=[tgt], value=value)


def if_stmt(test: ast.expr, body: list[ast.stmt],
            orelse: list[ast.stmt] | None = None) -> ast.If:
    """Build an if statement::

        if test:
            body
        else:
            orelse
    """
    return ast.If(test=test, body=body, orelse=orelse or [])


def for_loop(target: str | ast.expr, iter: ast.expr,
             body: list[ast.stmt]) -> ast.For:
    """Build a for loop: ``for target in iter: body``."""
    if isinstance(target, str):
        target = ast.Name(id=target, ctx=ast.Store())
    else:
        _set_store_ctx(target)
    return ast.For(target=target, iter=iter, body=body, orelse=[])


def return_stmt(value: ast.expr | None = None) -> ast.Return:
    """Build a return statement: ``return value``."""
    return ast.Return(value=value)


def expr_stmt(value: ast.expr) -> ast.Expr:
    """Wrap an expression as a statement: ``expr``."""
    return ast.Expr(value=value)


def aug_assign(target: ast.expr, value: ast.expr) -> ast.AugAssign:
    """Build augmented assignment: ``target += value``."""
    return ast.AugAssign(target=target, op=ast.Add(), value=value)


# ============================================================================
# Data Structures
# ============================================================================


def dict_literal(pairs: dict[str, ast.expr] | None = None) -> ast.Dict:
    """Build a dict literal: ``{'key': value, ...}``.

    All keys are string constants.
    """
    if not pairs:
        return ast.Dict(keys=[], values=[])
    return ast.Dict(
        keys=[constant(k) for k in pairs],
        values=list(pairs.values()),
    )


def list_literal(items: list[ast.expr] | None = None) -> ast.List:
    """Build a list literal: ``[item, ...]``."""
    return ast.List(elts=items or [], ctx=ast.Load())


# ============================================================================
# Functions
# ============================================================================


def lambda_expr(args: list[str], body: ast.expr,
                defaults: dict[str, ast.expr] | None = None) -> ast.Lambda:
    """Build a lambda: ``lambda a, b=val: body``.

    Args with defaults must come after args without defaults.
    """
    defaults = defaults or {}
    all_args = []
    default_nodes = []
    for arg_name in args:
        all_args.append(ast.arg(arg=arg_name))
        if arg_name in defaults:
            default_nodes.append(defaults[arg_name])

    return ast.Lambda(
        args=ast.arguments(
            posonlyargs=[],
            args=all_args,
            kwonlyargs=[],
            kw_defaults=[],
            defaults=default_nodes or [],
        ),
        body=body,
    )


# ============================================================================
# Comprehensions
# ============================================================================


def _comprehension(target: ast.expr, iter: ast.expr,
                   ifs: list[ast.expr] | None = None) -> ast.comprehension:
    """Build a single comprehension clause: ``for target in iter [if ifs]``."""
    # Set Store context on Name nodes inside the target
    _set_store_ctx(target)
    return ast.comprehension(target=target, iter=iter, ifs=ifs or [], is_async=False)


def _set_store_ctx(node: ast.expr) -> None:
    """Recursively set Store context on Name nodes (for assignment/loop targets)."""
    if isinstance(node, ast.Name):
        node.ctx = ast.Store()
    elif isinstance(node, ast.Tuple):
        for elt in node.elts:
            _set_store_ctx(elt)
    elif isinstance(node, ast.List):
        for elt in node.elts:
            _set_store_ctx(elt)


def list_comp(elt: ast.expr, target: ast.expr, iter: ast.expr,
              ifs: list[ast.expr] | None = None) -> ast.ListComp:
    """Build a list comprehension: ``[elt for target in iter]``."""
    return ast.ListComp(elt=elt, generators=[_comprehension(target, iter, ifs)])


def dict_comp(key: ast.expr, value: ast.expr, target: ast.expr,
              iter: ast.expr, ifs: list[ast.expr] | None = None) -> ast.DictComp:
    """Build a dict comprehension: ``{key: value for target in iter}``."""
    return ast.DictComp(
        key=key, value=value,
        generators=[_comprehension(target, iter, ifs)],
    )


# ============================================================================
# F-strings
# ============================================================================


def formatted_value(expr: ast.expr, conversion: int = -1) -> ast.FormattedValue:
    """Build an f-string interpolation: ``{expr}`` inside an f-string.

    conversion: -1 (none), 115 (str via !s), 114 (repr via !r), 97 (ascii via !a)
    """
    return ast.FormattedValue(value=expr, conversion=conversion)


def fstring(parts: list[ast.expr]) -> ast.JoinedStr:
    """Build an f-string from parts (constants and formatted values)."""
    return ast.JoinedStr(values=parts)
