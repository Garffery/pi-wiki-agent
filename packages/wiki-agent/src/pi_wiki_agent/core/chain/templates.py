"""Template resolution — mirrors pi-subagents template system."""

from __future__ import annotations

import re

_VAR_TOKEN = re.compile(r"\{vars\.(\w+)\}")


def resolve_template(
    template: str,
    task: str,
    prev: str = "",
    outputs: dict[str, str] | None = None,
    chain_dir: str = "",
    vars: dict[str, str] | None = None,
) -> str:
    """Resolve template tokens in a chain step's task.

    Mirrors the token substitution in pi-subagents' executeChain:
      {task}       → original user task
      {previous}   → output from previous step
      {outputs.X}  → named output from a step with as_: "X"
      {chain_dir}  → chain working directory
      {vars.key}   → custom variable from ChainConfig.vars
    """
    result = template
    result = result.replace("{task}", task)
    result = result.replace("{previous}", prev)
    result = result.replace("{chain_dir}", chain_dir)

    if outputs:
        for name, value in outputs.items():
            result = result.replace(f"{{outputs.{name}}}", value)

    if vars:
        def _sub_var(m: re.Match) -> str:
            key = m.group(1)
            return vars.get(key, m.group(0))
        result = _VAR_TOKEN.sub(_sub_var, result)

    return result


def build_step_prompt(
    template: str,
    task: str,
    prev: str,
    outputs: dict[str, str] | None = None,
    chain_dir: str = "",
    reads: list[str] | None = None,
    output_file: str | None = None,
    vars: dict[str, str] | None = None,
) -> str:
    """Build a complete step prompt with optional instructions for reads and output.

    Appends prefix/suffix instructions similar to pi-subagents' buildChainInstructions.
    """
    resolved = resolve_template(template, task, prev, outputs, chain_dir, vars)

    prefix = ""
    suffix = ""

    if reads:
        prefix += "请先阅读以下文件：\n"
        for f in reads:
            prefix += f"- {f}\n"
        prefix += "\n"

    if output_file:
        suffix += f"\n\n完成后请将结果写入文件：{output_file}"

    return prefix + resolved + suffix
