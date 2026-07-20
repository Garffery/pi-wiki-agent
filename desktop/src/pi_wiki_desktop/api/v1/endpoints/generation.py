"""Full generation endpoints."""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ....config import load_projects
from ....models import GenerationRequest, GenerationResultResponse
from ....sessions.factory import get_model_registry, make_chain_session_factory

router = APIRouter()


@router.post("/projects/{name}/generate", response_model=GenerationResultResponse)
async def generate_wiki(name: str, body: GenerationRequest | None = None,
                        registry = Depends(get_model_registry)):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")

    from pi_wiki_agent.core.wiki_generator import WikiGenerator
    from pi_wiki_agent.core.chain.generation_plan import GenerationPlan

    plan = GenerationPlan.load(cfg["path"])
    if plan is None:
        raise HTTPException(400, "未找到 .wiki/generation-plan.json，请先创建生成方案")

    generator = WikiGenerator(cfg["path"])
    default_model = body.model if body else None
    result = await generator.generate(plan=plan, session_factory=make_chain_session_factory(registry, default_model))
    return GenerationResultResponse(success=result.success, pages_created=result.pages_created, errors=result.errors)


@router.post("/projects/{name}/generate/stream")
async def generate_wiki_stream(name: str, body: GenerationRequest | None = None,
                               registry = Depends(get_model_registry)):
    cfg = load_projects().get(name)
    if not cfg:
        raise HTTPException(404, f"项目不存在: {name}")

    from pi_wiki_agent.core.wiki_generator import WikiGenerator
    from pi_wiki_agent.core.chain.generation_plan import GenerationPlan

    plan = GenerationPlan.load(cfg["path"])
    if plan is None:
        raise HTTPException(400, "未找到 .wiki/generation-plan.json")

    queue: asyncio.Queue[dict] = asyncio.Queue()

    def on_gen_progress(page_index: int, page_path: str, event_type: str, data: dict):
        queue.put_nowait({
            "type": f"gen_{event_type}", "page_index": page_index,
            "page_path": page_path, "data": data,
        })

    async def _run_generate():
        generator = WikiGenerator(cfg["path"])
        default_model = body.model if body else None
        try:
            result = await generator.generate(
                plan=plan, session_factory=make_chain_session_factory(registry, default_model),
                on_progress=on_gen_progress,
            )
            await queue.put({
                "type": "gen_done", "success": result.success,
                "pages_created": result.pages_created, "errors": result.errors,
            })
        except Exception as exc:
            await queue.put({"type": "gen_done", "success": False, "error": str(exc)})

    task = asyncio.create_task(_run_generate())

    async def _event_stream():
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=600)
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                if data.get("type") in ("gen_done",):
                    await task; return
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'type': 'timeout'})}\n\n"; return

    return StreamingResponse(
        _event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
