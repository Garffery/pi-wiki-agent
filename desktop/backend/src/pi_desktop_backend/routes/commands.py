"""Slash command endpoint — forwards to extension handlers or handles built-in commands."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class CommandRequest(BaseModel):
    command: str
    args: str = ""


BUILTIN_HANDLERS = {
    "thinking": lambda pool, sid, args: pool.cycle_thinking_level(sid),
    "compact": lambda pool, sid, args: pool.compact_session(sid),
    "tools": lambda pool, sid, args: _get_tools(pool, sid),
    "session": lambda pool, sid, args: _get_session_info(pool, sid),
    "clear": lambda pool, sid, args: {"status": "ok", "action": "clear"},
    "help": lambda pool, sid, args: {"status": "ok", "action": "help"},
}


async def _get_tools(pool, session_id):
    tools = await pool.get_tools(session_id)
    return {"status": "ok", "tools": tools}


async def _get_session_info(pool, session_id):
    info = await pool.get_session_info(session_id)
    stats = await pool.get_session_stats(session_id)
    return {"status": "ok", "info": info, "stats": stats}


@router.post("/api/sessions/{session_id}/command")
async def execute_command(session_id: str, body: CommandRequest, request: Request):
    pool = request.app.state.session_pool
    cmd = body.command.lstrip("/")

    handler = BUILTIN_HANDLERS.get(cmd)
    if handler:
        result = handler(pool, session_id, body.args)
        if hasattr(result, "__await__"):
            result = await result
        return result

    # For extension commands, we'd need to forward to the extension system
    return {"status": "unknown_command", "command": cmd}
