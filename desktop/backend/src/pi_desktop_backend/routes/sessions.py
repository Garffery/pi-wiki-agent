"""Session CRUD endpoints."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _pool(request: Request):
    return request.app.state.session_pool


@router.post("/api/sessions")
async def create_session(request: Request):
    pool = _pool(request)
    cwd = None
    try:
        body = await request.json()
        cwd = body.get("cwd")
    except Exception:
        pass
    info = await pool.create_session(cwd=cwd)
    return info


@router.get("/api/sessions")
async def list_sessions(request: Request):
    pool = _pool(request)
    return await pool.list_sessions()


@router.get("/api/sessions/{session_id}")
async def get_session(session_id: str, request: Request):
    pool = _pool(request)
    info = await pool.get_session_info(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found")
    return info


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    pool = _pool(request)
    deleted = await pool.delete_session(session_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.get("/api/sessions/{session_id}/messages")
async def get_messages(session_id: str, request: Request):
    pool = _pool(request)
    messages = await pool.get_messages(session_id)
    if messages is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "messages": messages}


@router.post("/api/sessions/{session_id}/fork")
async def fork_session(session_id: str, request: Request):
    pool = _pool(request)
    entry_id = None
    try:
        body = await request.json()
        entry_id = body.get("entry_id")
    except Exception:
        pass
    return await pool.fork_session(session_id, entry_id)


@router.get("/api/sessions/{session_id}/tree")
async def get_session_tree(session_id: str, request: Request):
    pool = _pool(request)
    tree = await pool.get_session_tree(session_id)
    if tree is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "tree": tree}


@router.get("/api/sessions/{session_id}/fork-points")
async def get_fork_points(session_id: str, request: Request):
    pool = _pool(request)
    points = await pool.get_fork_points(session_id)
    if points is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "fork_points": points}
