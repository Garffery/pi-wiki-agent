"""Model management endpoints (CRUD for ~/.pi/agent/models.json)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger

from ....models import ModelConfigCreate
from ....sessions.factory import get_model_registry

router = APIRouter()


@router.get("/models", response_model=list[dict])
async def list_models(registry = Depends(get_model_registry)):
    return await registry.get_available_summaries()


@router.post("/models", response_model=dict)
async def create_model(body: ModelConfigCreate, registry = Depends(get_model_registry)):
    registry.add_custom_model(
        name=body.name, provider=body.provider,
        model_id=body.model_id, base_url=body.base_url,
        api_key=body.api_key,
    )
    return {"status": "ok", "name": body.name}


@router.delete("/models/{provider}/{model_id}", response_model=dict)
async def delete_model(provider: str, model_id: str, registry = Depends(get_model_registry)):
    if not registry.remove_custom_model(provider, model_id):
        raise HTTPException(404, f"模型不存在: {provider}:{model_id}")
    return {"deleted": f"{provider}:{model_id}"}
