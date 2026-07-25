"""
Dynamic workflow orchestration extension for pi-coding-agent.

Lets the AI model write Python scripts that orchestrate multiple isolated
subagents with agent(), parallel(), and pipeline() primitives.

Usage:
    Pi auto-discovers this extension from the extensions/ directory.
    On session start, the `workflow` tool is activated automatically.
"""


def extension_factory(api):
    """Register the workflow tool and activate it on session start."""
    from .workflow_tool import create_workflow_tool

    tool = create_workflow_tool()

    api.register_tool(
        name=tool["name"],
        label=tool["label"],
        description=tool["description"],
        parameters=tool["parameters"],
        execute=tool["execute"],
        prompt_snippet=tool.get("prompt_snippet"),
        prompt_guidelines=tool.get("prompt_guidelines"),
    )

    def on_session_start(_event):
        pass

    api.on("session_start", on_session_start)
