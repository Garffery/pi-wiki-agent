"""
Interactive TUI mode using Rich/Textual.

Mirrors packages/coding-agent/src/modes/interactive/interactive-mode.ts
"""
from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pi_coding_agent.core.agent_session import AgentSession


async def run_interactive_mode(
    session: "AgentSession",
    initial_messages: list[str] | None = None,
    extensions_result: Any = None,
) -> None:
    """
    Run the agent in interactive mode with a TUI.

    This is a simplified implementation that falls back to a readline-based
    REPL when Textual is not available. Full TUI support requires the Textual
    library.
    """
    try:
        from pi_coding_agent.modes.interactive.tui import run_tui
        await run_tui(session, initial_messages, extensions_result)
    except ImportError:
        await _run_readline_fallback(session, initial_messages)


async def _run_readline_fallback(session: "AgentSession", initial_messages: list[str] | None = None, extensions_result: Any = None) -> None:
    """Fallback readline-based interactive loop."""
    from rich.console import Console
    from rich.markdown import Markdown

    console = Console()
    console.print("[bold green]Pi Coding Agent[/bold green] (interactive mode)")
    console.print("Type your message and press Enter. Ctrl+C to exit.\n")

    # Process initial messages if provided
    if initial_messages:
        for msg in initial_messages:
            console.print(f"[dim]> {msg}[/dim]")
            await _send_and_wait(session, msg, console)

    loop = asyncio.get_event_loop()

    while True:
        try:
            # Use input() instead of sys.stdin.readline() for better Windows compatibility
            user_input = await loop.run_in_executor(None, input, "> ")
            if not user_input:
                continue
            user_input = user_input.strip()
            if not user_input:
                continue
            if user_input.lower() in ("/exit", "/quit", "exit", "quit"):
                break

            await _send_and_wait(session, user_input, console)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Exiting...[/dim]")
            break


async def _send_and_wait(session: "AgentSession", message: str, console: Any) -> None:
    """Send a message to the session and stream the response."""
    from rich.console import Console

    events: list[Any] = []
    done = asyncio.Event()

    def on_event(event: Any) -> None:
        events.append(event)
        # Handle both dict and object formats
        if isinstance(event, dict):
            event_type = event.get("type", "")
        else:
            event_type = getattr(event, "type", "")

        # Handle message_update events (contains assistant_message_event)
        if event_type == "message_update":
            if isinstance(event, dict):
                assistant_event = event.get("assistant_message_event")
            else:
                assistant_event = getattr(event, "assistant_message_event", None)

            if assistant_event:
                if isinstance(assistant_event, dict):
                    sub_type = assistant_event.get("type", "")
                    delta = assistant_event.get("delta", "")
                else:
                    sub_type = getattr(assistant_event, "type", "")
                    delta = getattr(assistant_event, "delta", "")

                if sub_type == "text_delta" and delta:
                    console.print(delta, end="", highlight=False)

        elif event_type == "agent_end":
            done.set()

        elif event_type == "error":
            if isinstance(event, dict):
                error = event.get("error", "Unknown error")
            else:
                error = getattr(event, "error", "Unknown error")
            console.print(f"\n[red]Error: {error}[/red]")
            done.set()

    unsubscribe = session.subscribe(on_event)
    try:
        await session.prompt(message, source="interactive")
        await asyncio.wait_for(done.wait(), timeout=300.0)
        console.print()
    except asyncio.TimeoutError:
        console.print("\n[yellow]Response timeout[/yellow]")
    finally:
        unsubscribe()
