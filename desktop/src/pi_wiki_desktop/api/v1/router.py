"""API v1 router — aggregates all endpoint modules."""

from fastapi import APIRouter

from .endpoints import (
    health,
    projects,
    commits,
    model_management,
    filters,
    sync,
    chain,
    quality,
    generation,
)

router = APIRouter(prefix="/api")

router.include_router(health.router)
router.include_router(projects.router)
router.include_router(commits.router)
router.include_router(model_management.router)
router.include_router(filters.router)
router.include_router(sync.router)
router.include_router(chain.router)
router.include_router(quality.router)
router.include_router(generation.router)
