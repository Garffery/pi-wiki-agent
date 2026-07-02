"""Settings endpoints."""

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/api/settings")
async def get_settings(request: Request):
    pool = request.app.state.session_pool
    # Get settings from the first available session, or return defaults
    sessions = await pool.list_sessions()
    if sessions:
        session = await pool.get_session(sessions[0]["session_id"])
        if session and hasattr(session, "_settings_manager"):
            sm = session._settings_manager
            return {
                "default_model": sm.get_default_model(),
                "default_provider": sm.get_default_provider(),
                "default_thinking_level": sm.get_default_thinking_level(),
            }
    return {
        "default_model": None,
        "default_provider": "anthropic",
        "default_thinking_level": "medium",
    }


@router.put("/api/settings")
async def update_settings(request: Request):
    body = await request.json()
    # Settings persistence would go through SettingsManager
    return {"status": "ok", "settings": body}
