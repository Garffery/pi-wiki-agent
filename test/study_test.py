from pi_wiki_agent.core.workflow.ast_compiler.resolver import _find_top_level_comma, _resolve_bare as _resolve_var_bare


def _resolve_join(expr: str, context: dict) -> str:
    """Resolve ${join(array, template)} → Python join expression."""
    inner = expr[5:].rstrip(")").lstrip("(")
    print(inner)
    comma_idx = _find_top_level_comma(inner)
    print(comma_idx)
    if comma_idx < 0:
        return f'"<invalid join: {expr}>"'
    array_raw = inner[:comma_idx].strip()
    # Resolve array variable (e.g. changed_files → args['changed_files'])
    print(f"array_raw: {array_raw}")
    array_expr = _resolve_var_bare(array_raw, context)
    print(f"array_expr: {array_expr}")
    template = inner[comma_idx + 1:].strip().strip("'").strip('"')
    # Replace ${item} with {item} placeholder for .format()
    template = template.replace("${item}", "{item}")
    # Escape any remaining braces for .format()
    template = template.replace("{", "{{").replace("}", "}}")
    # Restore {item} placeholder
    template = template.replace("{{item}}", "{item}")
    return f"chr(10).join('{template}'.format(item=f) for f in {array_expr})"

expr = """join(changed_files, "- ${item}")"""
context = {}
res = _resolve_join(expr, context)

print(res)