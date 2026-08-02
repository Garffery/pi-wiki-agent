"""
Variable resolver: YAML ``${...}`` template syntax → AST expression nodes.

Replaces the string-concatenation resolver in the old compiler. Every
``${...}`` pattern is resolved to a proper ``ast.expr`` node.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass

from . import ast_helpers as H

# ============================================================================
# Resolve context
# ============================================================================


@dataclass
class ResolveContext:
    """Variable name bindings for the current scope."""
    prev_var: str = "_prev"
    # ^ ${previous} 引用的变量名。
    #   初始为 _prev（值为 None），每个 serial step 执行后更新为 _sN。
    #   例如: Phase 1 的 ${previous} → _prev (None)
    #         Phase 2 的 ${previous} → _s1  (Phase 1 最后一步的结果)

    item_var: str = "_item"
    # ^ ${item} / ${item.field} 引用的变量名。
    #   serial+for_each 时为 "_item"，parallel+for_each 时为 "it"，
    #   dag+for_each 时为 "it2"（避免与外层 for 循环变量冲突）

    outputs_var: str = "_outputs"
    # ^ ${outputs.Phase.field} 引用的字典名。
    #   存储所有已执行阶段的输出，key 为阶段标题（空格替换为 _）。
    #   例如: ${outputs.Plan.file_tasks} → _outputs.get('Plan').get('file_tasks')


# ============================================================================
# Text splitter
# ============================================================================


def _split_vars(text: str) -> list[tuple[bool, str]]:
    """Split text into *(is_var, value)* tuples, handling nested ``${...}``."""
    parts: list[tuple[bool, str]] = []
    i = 0
    buf: list[str] = []
    while i < len(text):
        if text[i:i + 2] == "${":
            if buf:
                parts.append((False, "".join(buf)))
                buf = []
            end = _find_var_end(text, i)
            parts.append((True, text[i + 2:end - 1]))
            i = end
        else:
            buf.append(text[i])
            i += 1
    if buf:
        parts.append((False, "".join(buf)))
    return parts


def _find_var_end(text: str, start: int) -> int:
    """Find the closing ``}`` for a ``${...}`` expression, respecting nested braces."""
    depth = 1
    i = start + 2
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i


def _is_single_var(text: str) -> bool:
    """Check whether *text* is a single ``${...}`` expression with no surrounding text."""
    parts = _split_vars(text)
    return len(parts) == 1 and parts[0][0]


# ============================================================================
# Bare expression resolver: ${...} body → ast.expr
# ============================================================================


def _resolve_bare(expr: str, ctx: ResolveContext) -> ast.expr:
    """Resolve the content inside ``${...}`` to a bare AST expression node.

    The returned node is NOT wrapped in an f-string — it is the raw expression
    (a subscript, a call, a name reference, etc.).
    """
    expr = expr.strip()

    # ── ${join(array, template)} ──
    if expr.startswith("join("):
        return _resolve_join(expr, ctx)

    # ── ${outputs.Phase.field} — guarded .get() chain ──
    if expr.startswith("outputs."):
        return _resolve_outputs(expr[len("outputs."):], ctx)

    # ── ${item.field} ──
    if expr.startswith("item."):
        field = expr[len("item."):]
        return H.get(H.name(ctx.item_var), field)

    # ── ${item} ──
    if expr == "item":
        return H.name(ctx.item_var)

    # ── ${previous} ──
    if expr == "previous":
        return H.name(ctx.prev_var)

    # ── ${self.name} — variable from the YAML ``variables:`` section ──
    if expr.startswith("self."):
        field = expr[len("self."):]
        return H.name(f"_self_{field}")

    # ── ${a.b.c} — dotted access chain on args ──
    if "." in expr:
        return _resolve_dotted(expr, ctx)

    # ── ${name} — simple args subscript ──
    return H.subscript(H.name("args"), H.constant(expr))


def _resolve_dotted(expr: str, ctx: ResolveContext) -> ast.expr:
    """Resolve ``a.b.c`` → ``args.get('a', {}).get('b').get('c')``."""
    parts = expr.split(".")
    empty_dict = H.dict_literal()
    result: ast.expr = H.get(H.name("args"), parts[0], empty_dict)
    for p in parts[1:]:
        result = H.get(result, p)
    return result


# ============================================================================
# ${outputs.Phase.field} — guarded access
# ============================================================================


def _resolve_outputs(rest: str, ctx: ResolveContext) -> ast.expr:
    """Resolve ``${outputs.Phase.field}`` with isinstance guards.

    Generates::

        ((_outputs.get('Phase') or {}).get('field')
         if isinstance(_outputs.get('Phase'), dict)
            and isinstance((_outputs.get('Phase') or {}).get('field'), list)
         else [])
    """
    parts = rest.split(".")
    if len(parts) < 2:
        # ${outputs.Phase} — simpler: _outputs.get('Phase')
        return H.get(H.name(ctx.outputs_var), parts[0])

    phase_key = parts[0]
    field_key = parts[1]
    empty = H.dict_literal()

    phase_get = H.get(H.name(ctx.outputs_var), phase_key)
    phase_or = H.or_expr(phase_get, empty)
    field_get = H.get(phase_or, field_key)

    # isinstance(_outputs.get('Phase'), dict)
    phase_is_dict = H.isinstance_expr(phase_get, "dict")
    # isinstance((_outputs.get('Phase') or {}).get('field'), list)
    field_is_list = H.isinstance_expr(field_get, "list")

    condition = ast.BoolOp(op=ast.And(), values=[phase_is_dict, field_is_list])

    return H.ternary(condition, field_get, H.list_literal())


# ============================================================================
# ${join(array, template)}
# ============================================================================


def _resolve_join(expr: str, ctx: ResolveContext) -> ast.expr:
    """Resolve ``${join(array, template)}`` → ``chr(10).join(f'...' for f in arr)``.

    The template is a string literal with ``${item}`` / ``${item.field}``
    placeholders that become ``{f}`` / ``{f["field"]}`` in the f-string.
    """
    inner = expr[5:].rstrip(")").lstrip("(")  # strip "join(" and ")"
    comma_idx = _find_top_level_comma(inner)
    if comma_idx < 0:
        return H.constant("<invalid join: " + expr + ">")

    array_raw = inner[:comma_idx].strip()
    array_expr = _resolve_bare(array_raw, ctx)

    template = inner[comma_idx + 1:].strip()
    # Strip surrounding quotes if present
    if (template.startswith("'") and template.endswith("'")) or \
       (template.startswith('"') and template.endswith('"')):
        template = template[1:-1]

    # Build the f-string body for the generator: replace ${item} / ${item.xxx}
    fstring_parts = _build_join_fstring(template)

    # chr(10).join(f'...' for f in array)
    chr_call = H.call_fn("chr", [H.constant(10)])
    # Generator expression: (fstring for f in array_expr)
    gen = ast.GeneratorExp(
        elt=ast.JoinedStr(values=fstring_parts),
        generators=[ast.comprehension(
            target=H.name("f"), iter=array_expr, ifs=[], is_async=False,
        )],
    )
    return H.call(H.attribute(chr_call, "join"), [gen])


# Regex patterns for ${item} and ${item.field} inside join templates
_JOIN_ITEM_RE = re.compile(r"\$\{item\}")
_JOIN_ITEM_FIELD_RE = re.compile(r"\$\{item\.(\w+)\}")


def _build_join_fstring(template: str) -> list[ast.expr]:
    """Alternate implementation: split by regex, then interleave."""
    parts: list[ast.expr] = []

    # Find all matches, sorted by start position
    matches: list[tuple[int, int, str | None]] = []  # (start, end, field_or_None)
    for m in _JOIN_ITEM_FIELD_RE.finditer(template):
        matches.append((m.start(), m.end(), m.group(1)))
    for m in _JOIN_ITEM_RE.finditer(template):
        # Avoid overlap: ${item} is a substring of ${item.field}, so skip if
        # already covered by a field match
        if not any(s <= m.start() < e for s, e, _ in matches):
            matches.append((m.start(), m.end(), None))
    matches.sort(key=lambda x: x[0])

    pos = 0
    for start, end, field in matches:
        # Literal text before this match
        if pos < start:
            parts.append(H.constant(template[pos:start]))
        # Build the FormattedValue
        if field is not None:
            f_expr: ast.expr = H.subscript(H.name("f"), H.constant(field))
        else:
            f_expr = H.name("f")
        parts.append(ast.FormattedValue(value=f_expr, conversion=-1))
        pos = end

    # Trailing literal text
    if pos < len(template):
        parts.append(H.constant(template[pos:]))

    return parts


# ============================================================================
# Public API
# ============================================================================


def resolve_expr(raw: str, ctx: ResolveContext | None = None) -> ast.expr:
    """Resolve a YAML value that may contain a ``${...}`` expression.

    - A single ``${...}`` covering the whole text → bare expression node
      (e.g. ``${outputs.Plan.tasks}`` → subscript AST, not an f-string).
    - Pure text with no ``${...}`` → ``ast.Constant(str)``.
    - Mixed text + variables → ``ast.JoinedStr`` (f-string).

    Used for: step labels, step ids, for_each expressions.
    """
    ctx = ctx or ResolveContext()

    raw = raw.strip() if raw else ""
    if not raw:
        return H.constant("")

    parts = _split_vars(raw)

    # Single ${...} → bare expression
    if len(parts) == 1 and parts[0][0]:
        return _resolve_bare(parts[0][1], ctx)

    # No variables → plain string constant
    if all(not is_var for is_var, _ in parts):
        return H.constant(raw)

    # Mixed → f-string
    f_parts: list[ast.expr] = []
    for is_var, val in parts:
        if is_var:
            f_parts.append(ast.FormattedValue(value=_resolve_bare(val, ctx), conversion=-1))
        else:
            f_parts.append(H.constant(val))
    return ast.JoinedStr(values=f_parts)


def resolve_prompt(raw: str, ctx: ResolveContext | None = None) -> ast.expr:
    """Resolve a prompt string — always returns a string expression.

    All ``${...}`` patterns are replaced with f-string interpolations.
    Multi-line text is preserved as-is.
    """
    ctx = ctx or ResolveContext()

    if not raw:
        return H.constant("")

    parts = _split_vars(raw)

    # Pure text (no variables)
    if all(not is_var for is_var, _ in parts):
        return H.constant(raw)

    # Build f-string
    f_parts: list[ast.expr] = []
    for is_var, val in parts:
        if is_var:
            f_parts.append(ast.FormattedValue(value=_resolve_bare(val, ctx), conversion=-1))
        else:
            f_parts.append(H.constant(val))
    return ast.JoinedStr(values=f_parts)


def _find_top_level_comma(s: str) -> int:
    """Find the first comma not inside nested brackets."""
    depth = 0
    for i, ch in enumerate(s):
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            return i
    return -1
