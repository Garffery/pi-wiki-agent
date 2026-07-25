"""
YAML → Python workflow script compiler.

Converts a YAML workflow definition into a Python script string that can be
executed by run_workflow().
"""
from __future__ import annotations

import re
from typing import Any


# ============================================================================
# Schema shorthand compiler
# ============================================================================

# Map type names used in YAML to JSON Schema type strings
_TYPE_MAP = {"str": "string", "int": "integer", "float": "number", "bool": "boolean"}


def compile_schema(shorthand: Any) -> dict | None:
    """Convert YAML schema shorthand to JSON Schema dict.

    Shorthand forms::

        field: str          →  {"type": "string"}
        field: str?         →  {"type": "string"} (optional)
        field: int          →  {"type": "integer"}
        field: [str]        →  {"type": "array", "items": {"type": "string"}}
        field: {enum: [a]}  →  {"type": "string", "enum": ["a", "b"]}
        field: <dict>       →  nested object with properties
    """
    if shorthand is None:
        return None

    # str / str? / int / float / bool
    if isinstance(shorthand, str):
        optional = shorthand.endswith("?")
        base = shorthand[:-1] if optional else shorthand
        if base in _TYPE_MAP:
            return {"type": _TYPE_MAP[base]}

    # [str] — array of strings
    if isinstance(shorthand, list):
        if len(shorthand) == 1 and isinstance(shorthand[0], str) and shorthand[0] in _TYPE_MAP:
            return {"type": "array", "items": {"type": _TYPE_MAP[shorthand[0]]}}
        return {"type": "array", "items": compile_schema(shorthand[0]) if shorthand else {}}

    # {enum: [...]}
    if isinstance(shorthand, dict) and "enum" in shorthand and len(shorthand) == 1:
        return {"type": "string", "enum": shorthand["enum"]}

    # Nested object: {field1: str, field2: int, ...}
    if isinstance(shorthand, dict):
        required: list[str] = []
        properties: dict[str, dict] = {}
        for key, val in shorthand.items():
            if isinstance(key, str) and key.endswith("?"):
                real_key = key[:-1]
                properties[real_key] = compile_schema(val) or {}
            else:
                required.append(key)
                properties[key] = compile_schema(val) or {}
        schema: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            schema["required"] = required
        return schema

    return None


# ============================================================================
# Variable resolver
# ============================================================================

_VAR_RE = re.compile(r"\$\{([^}]+)\}")

# Map of variable prefixes to Python expression generators
# Each entry: (prefix) → lambda remainder, context → python_expr


def _resolve_join(expr: str, context: dict) -> str:
    """Resolve ${join(array, template)} → Python join expression."""
    inner = expr[5:].rstrip(")").lstrip("(")
    comma_idx = _find_top_level_comma(inner)
    if comma_idx < 0:
        return f'"<invalid join: {expr}>"'
    array_raw = inner[:comma_idx].strip()
    # Resolve array variable (e.g. changed_files → args['changed_files'])
    array_expr = _resolve_var_bare(array_raw, context)
    template = inner[comma_idx + 1:].strip().strip("'").strip('"')
    # Replace ${item} with {item} placeholder for .format()
    template = template.replace("${item}", "{item}")
    # Escape any remaining braces for .format()
    template = template.replace("{", "{{").replace("}", "}}")
    # Restore {item} placeholder
    template = template.replace("{{item}}", "{item}")
    return f"chr(10).join('{template}'.format(item=f) for f in {array_expr})"


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


def _resolve_var_bare(expr: str, context: dict) -> str:
    """Resolve ${...} expression to a bare Python expression (no f-string braces)."""

    if expr.startswith("join("):
        return _resolve_join(expr, context)

    if expr.startswith("outputs."):
        parts = expr[len("outputs."):].split(".")
        outputs_var = context.get("outputs_var", "_outputs")
        if len(parts) == 2:
            return (
                f"{outputs_var}.get('{parts[0]}', {{}})"
                f".get('{parts[1]}') if isinstance({outputs_var}.get('{parts[0]}'), dict) else None"
            )
        return f"{outputs_var}.get('{expr}')"

    if expr.startswith("item."):
        field = expr[len("item."):]
        item_var = context.get("item_var", "item")
        return f"{item_var}['{field}']"
    if expr == "item":
        return context.get("item_var", "item")

    if expr == "previous":
        return context.get("prev_var", "_prev")

    if expr.startswith("self."):
        field = expr[len("self."):]
        return f"{context.get('self_var', '_self')}.get('{field}', '')"

    return f"args['{expr}']"


def resolve_var(expr: str, context: dict) -> str:
    """Resolve ${...} to an f-string expression (wrapped in {braces})."""
    bare = _resolve_var_bare(expr, context)
    return f"{{{bare}}}"


def _split_vars(text: str) -> list[tuple[bool, str]]:
    """Split text into (is_var, value) tuples. Handles nested ${...}."""
    parts = []
    i = 0
    buf = []
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


def resolve_expr(expr_text: str, context: dict) -> str:
    """Resolve ${...} in a text to a valid Python expression.

    If the entire text is a single ${...}, return the bare expression.
    Otherwise, resolve all ${...} and wrap in an f-string.
    """
    parts = _split_vars(expr_text)
    if len(parts) == 1 and parts[0][0]:
        return _resolve_var_bare(parts[0][1], context)
    if all(not is_var for is_var, _ in parts):
        return repr(expr_text)

    # Mixed: build f-string
    result_parts = []
    for is_var, val in parts:
        if is_var:
            result_parts.append("{" + _resolve_var_bare(val, context) + "}")
        else:
            result_parts.append(val)
    return "f'" + "".join(result_parts) + "'"


def _find_var_end(text: str, start: int) -> int:
    """Find the closing } for a ${...} expression starting at 'start'.
    Handles nested ${...} by counting brace depth.
    """
    depth = 1
    i = start + 2  # skip ${
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return i  # index after closing }


def resolve_prompt(prompt: str, context: dict) -> str:
    """Replace all ${...} patterns in a prompt string with Python f-string expressions."""
    result = []
    i = 0
    while i < len(prompt):
        if prompt[i:i + 2] == "${":
            end = _find_var_end(prompt, i)
            expr = prompt[i + 2:end - 1]  # content between ${ and }
            result.append(resolve_var(expr, context))
            i = end
        else:
            result.append(prompt[i])
            i += 1
    return "".join(result)


# ============================================================================
# Prompt to Python code (handles multi-line prompts)
# ============================================================================


def _format_prompt(prompt: str, indent: str = "        ") -> str:
    """Format a multi-line prompt as a Python f-string with proper indentation.

    The prompt may contain {...} Python expressions resolved from ${...} patterns.
    """
    lines = prompt.split("\n")
    if len(lines) == 1:
        return f"f'{lines[0]}'"

    # Multi-line: use f'''...'''
    return f"f'''{prompt}'''"


# ============================================================================
# Phase compiler
# ============================================================================


def compile_phases(phases: list[dict], variables: dict | None, context: dict) -> list[str]:
    """Compile all phases into Python code lines."""
    lines: list[str] = []
    outputs_var = context.get("outputs_var", "_outputs")
    step_counter = [0]  # mutable counter for unique variable names

    def _next_var():
        step_counter[0] += 1
        return f"_s{step_counter[0]}"

    # Variable definitions from YAML "variables:" section
    if variables:
        lines.append("# ── Variables ──")
        for vname, vprompt in variables.items():
            resolved = resolve_prompt(str(vprompt), context)
            lines.append(f"_self_{vname} = {resolved}")
        lines.append("")

    for i, phase in enumerate(phases):
        title = phase.get("title", f"Phase{i}")
        mode = phase.get("mode", "serial")
        for_each = phase.get("for_each")
        steps = phase.get("steps", [])

        if not steps:
            lines.append(f"# Phase '{title}': no steps, skipping")
            continue

        lines.append(f"# ─── Phase: {title} ───")
        lines.append(f"phase('{title}')")
        phase_var = f"_p{i}"

        # Resolve for_each expression (bare Python, not f-string)
        resolved_for_each = None
        if for_each:
            resolved_for_each = resolve_expr(for_each, context)

        # ── Mode: serial (default) ──
        if mode == "serial":
            if for_each:
                lines.append(f"{phase_var}_items = {resolved_for_each}")
                lines.append(f"{phase_var}_results = []")
                lines.append(f"if {phase_var}_items:")
                lines.append(f"    for _item in {phase_var}_items:")
                item_context = {**context, "item_var": "_item"}
                _compile_steps(steps, lines, item_context, "        ")
                lines.append(f"        {phase_var}_results.append(_r)")
                lines.append(f"else:")
                lines.append(f"    {phase_var}_results = []")
            else:
                _compile_serial_steps(steps, lines, context, _next_var)
                # Set phase_var to last step's var for prev chaining
                phase_var = f"_s{step_counter[0]}"
                lines.append(f"{phase_var}_results = {phase_var}")

        # ── Mode: parallel ──
        elif mode == "parallel":
            if for_each:
                lines.append(f"{phase_var}_items = {resolved_for_each}")
                lines.append(f"if {phase_var}_items:")
                lines.append(f"    {phase_var}_results = await parallel([")
                for step in steps:
                    # Use 'it' in lambda body, '_item' as loop var with default binding
                    item_context = {**context, "item_var": "it"}
                    step_agent = step["agent"]
                    step_label = resolve_expr(step.get("label", step_agent), item_context)
                    step_prompt = resolve_prompt(step.get("prompt", ""), item_context)
                    step_schema = compile_schema(step.get("output_schema"))
                    # Emit lambda with 'it=_item' default to capture value
                    lines.append("      (lambda it=_item: agent(")
                    lines.append(f"          {_format_prompt(step_prompt)},")
                    _emit_opts(lines, step_agent, step_label, step_schema, "          ")
                    lines.append("      ))")
                lines.append(f"      for _item in {phase_var}_items")
                lines.append(f"    ])")
                lines.append(f"else:")
                lines.append(f"    {phase_var}_results = []")
            else:
                lines.append(f"{phase_var}_results = await parallel([")
                for step in steps:
                    step_agent = step["agent"]
                    step_label = resolve_expr(step.get("label", step_agent), context)
                    step_prompt = resolve_prompt(step.get("prompt", ""), context)
                    step_schema = compile_schema(step.get("output_schema"))
                    _emit_agent(lines, step_agent, step_label, step_prompt, step_schema,
                                "    ", context)
                lines.append(f"])")

        # ── Mode: pipeline ──
        elif mode == "pipeline":
            lines.append(f"{phase_var}_items = {resolved_for_each}")
            lines.append(f"if {phase_var}_items:")
            lines.append(f"    {phase_var}_results = await pipeline(")
            lines.append(f"        {phase_var}_items,")
            for j, step in enumerate(steps):
                step_agent = step["agent"]
                step_label_tpl = resolve_expr(step.get("label", step_agent), {**context, "item_var": "_orig"})
                step_prompt_tpl = resolve_prompt(step.get("prompt", ""), {**context, "item_var": "_orig", "prev_var": "_prev"})
                lines.append(f"        lambda _prev, _orig, _idx: agent(")
                lines.append(f"            {_format_prompt(step_prompt_tpl, '                ')}, {{")
                lines.append(f"                'label': {step_label_tpl},")
                lines.append(f"                'agent': '{step_agent}',")
                lines.append(f"            }})),")
            lines.append(f"    )")
            lines.append(f"else:")
            lines.append(f"    {phase_var}_results = []")

        # ── Store output ──
        output_name = title.replace(" ", "_")
        lines.append(f"{outputs_var}['{output_name}'] = {phase_var}_results")

        # Update prev for next serial phase
        if mode == "serial" and not for_each:
            context["prev_var"] = phase_var

        lines.append("")

    return lines


def _compile_serial_steps(steps: list[dict], lines: list[str], context: dict, _next_var):
    """Compile serial steps with ${previous} chaining."""
    for step in steps:
        step_agent = step["agent"]
        step_label = resolve_expr(step.get("label", step_agent), context)
        step_prompt = resolve_prompt(step.get("prompt", ""), context)
        step_schema = compile_schema(step.get("output_schema"))

        var_name = _next_var()
        lines.append(f"{var_name} = await agent(")
        lines.append(f"    {_format_prompt(step_prompt)},")
        _emit_opts(lines, step_agent, step_label, step_schema, "    ")
        lines.append(f")")
        context["prev_var"] = var_name


def _emit_agent(lines: list[str], agent_name: str, label_expr: str,
                prompt_expr: str, schema: dict | None,
                indent: str, context: dict | None = None,
                item_var: str | None = None):
    """Emit a single agent() call as a lambda for parallel()."""
    lines.append(f"{indent}(lambda: agent(")
    lines.append(f"{indent}    {_format_prompt(prompt_expr)},")
    _emit_opts(lines, agent_name, label_expr, schema, f"{indent}    ")
    if item_var:
        lines.append(f"{indent}))")  # no trailing comma before for-in
    else:
        lines.append(f"{indent})),")


def _emit_opts(lines: list[str], agent_name: str, label_expr: str,
               schema: dict | None, indent: str):
    """Emit the opts dict for an agent() call."""
    lines.append(f"{indent}{{")
    lines.append(f"{indent}    'label': {label_expr},")
    lines.append(f"{indent}    'agent': '{agent_name}',")
    if schema:
        import json
        schema_str = json.dumps(schema)
        lines.append(f"{indent}    'schema': {schema_str},")
    lines.append(f"{indent}}}")


# ============================================================================
# Main entry point
# ============================================================================


def compile_workflow_yaml(yaml_text: str, agent_defs: dict | None = None) -> str:
    """Compile a YAML workflow definition into a Python script string.

    Args:
        yaml_text: Raw YAML content.
        agent_defs: Optional agent definitions dict (for validation).

    Returns:
        A Python script string ready for run_workflow().
    """
    import yaml as _yaml

    doc = _yaml.safe_load(yaml_text)
    if not isinstance(doc, dict):
        raise ValueError("YAML must be a dict at top level")

    name = doc.get("name", "unnamed")
    description = doc.get("description", "")
    phases = doc.get("phases", [])
    variables = doc.get("variables")
    concurrency = doc.get("concurrency")

    if not phases:
        raise ValueError("workflow YAML must have at least one phase")

    # Build meta
    meta_phases = []
    for p in phases:
        meta_phases.append({"title": p.get("title", "?")})

    lines: list[str] = []
    lines.append("meta = {")
    lines.append(f"    'name': '{name}',")
    lines.append(f"    'description': '{description}',")
    lines.append(f"    'phases': {meta_phases},")
    lines.append("}")
    lines.append("")

    # Context for variable resolution
    context = {
        "prev_var": "_prev",
        "outputs_var": "_outputs",
        "output_key": "phase",
    }

    lines.append("_outputs = {}")
    lines.append("_prev = None")
    lines.append("")

    # Compile phases
    phase_lines = compile_phases(phases, variables, context)
    lines.extend(phase_lines)

    # Return statement
    lines.append("return dict(_outputs)")

    return "\n".join(lines)
