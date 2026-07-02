"""Model and thinking level endpoints."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()


class SetModelRequest(BaseModel):
    provider: str
    model_id: str


class SetThinkingRequest(BaseModel):
    level: str


@router.get("/api/sessions/{session_id}/model")
async def get_model(session_id: str, request: Request):
    pool = request.app.state.session_pool
    session = await pool.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    model = session.model
    return {
        "provider": model.provider if model else None,
        "model_id": model.id if model else None,
        "thinking_level": session.thinking_level,
    }


@router.put("/api/sessions/{session_id}/model")
async def set_model(session_id: str, body: SetModelRequest, request: Request):
    pool = request.app.state.session_pool
    try:
        return await pool.set_model(session_id, body.provider, body.model_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/sessions/{session_id}/model/cycle")
async def cycle_model(session_id: str, request: Request):
    pool = request.app.state.session_pool
    try:
        return await pool.cycle_model(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/api/sessions/{session_id}/thinking")
async def set_thinking(session_id: str, body: SetThinkingRequest, request: Request):
    pool = request.app.state.session_pool
    try:
        return await pool.set_thinking_level(session_id, body.level)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/sessions/{session_id}/thinking/cycle")
async def cycle_thinking(session_id: str, request: Request):
    pool = request.app.state.session_pool
    try:
        return await pool.cycle_thinking_level(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/api/sessions/{session_id}/tools")
async def get_tools(session_id: str, request: Request):
    pool = request.app.state.session_pool
    tools = await pool.get_tools(session_id)
    if tools is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "tools": tools}


@router.get("/api/sessions/{session_id}/context")
async def get_context_usage(session_id: str, request: Request):
    pool = request.app.state.session_pool
    usage = await pool.get_context_usage(session_id)
    if usage is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, **usage}
