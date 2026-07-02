"""Chat / prompt endpoints."""

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)


class PromptRequest(BaseModel):
    message: str
    images: list[dict] | None = None


@router.post("/api/sessions/{session_id}/prompt")
async def send_prompt(session_id: str, body: PromptRequest, request: Request):
    pool = request.app.state.session_pool
    try:
        result = await pool.send_prompt(session_id, body.message, body.images)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/sessions/{session_id}/abort")
async def abort_session(session_id: str, request: Request):
    pool = request.app.state.session_pool
    try:
        return await pool.abort_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/api/sessions/{session_id}/compact")
async def compact_session(session_id: str, request: Request):
    pool = request.app.state.session_pool
    try:
        return await pool.compact_session(session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
