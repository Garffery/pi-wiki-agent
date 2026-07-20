"""Pydantic models for API request/response."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Request models ──────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    path: str


class SyncRequest(BaseModel):
    model: str | None = None  # optional model override, e.g. "deepseek:deepseek-chat"


class ChainSyncRequest(BaseModel):
    model: str | None = None  # optional model override for chain steps


# ── Response models ──────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"


class ProjectInfo(BaseModel):
    name: str
    path: str
    vcs: str
    last_revision: str
    pending_commits: int
    has_wiki: bool = True
    has_generation_plan: bool = False


class CommitSummary(BaseModel):
    revision: str
    message: str
    author: str
    timestamp: str
    files: list[str]


class AffectInfo(BaseModel):
    file: str
    wiki_page: str
    section_id: str


class CommitDetail(BaseModel):
    revision: str
    message: str
    author: str
    timestamp: str
    files: list[str]
    diff: str
    affected: dict[str, list[AffectInfo]]


class SyncResult(BaseModel):
    revision: str
    success: bool
    wiki_pages_modified: list[str]
    error: str = ""


class SyncAllResult(BaseModel):
    processed: int
    results: list[SyncResult]


class ChainStepResult(BaseModel):
    agent: str
    step_index: int
    output: str | None = None
    exit_code: int = 0
    error: str | None = None


class ChainSyncResult(BaseModel):
    success: bool
    error: str | None = None
    steps: list[ChainStepResult] = []
    last_output: str | None = None


# ── Model configuration ───────────────────────────────────────────────────

class ModelConfigCreate(BaseModel):
    name: str           # display name, e.g. "DeepSeek V3"
    provider: str       # provider key, e.g. "deepseek", "anthropic"
    model_id: str       # model identifier, e.g. "deepseek-chat"
    base_url: str       # API endpoint, e.g. "https://api.deepseek.com/v1"
    api_key: str = ""   # optional, if empty uses env var
    is_default: bool = False


class ModelConfig(BaseModel):
    name: str
    provider: str
    model_id: str
    base_url: str
    api_key: str = ""
    is_default: bool = False


# ── Quality Check ──────────────────────────────────────────────────────────

class QualityIssueItem(BaseModel):
    page: str
    section: str | None = None
    category: str
    severity: str
    check: str
    message: str
    detail: str | None = None


class QualityReportResponse(BaseModel):
    project_path: str = ""
    checked_at: str = ""
    total_pages: int = 0
    total_issues: int = 0
    errors: int = 0
    warnings: int = 0
    issues: list[QualityIssueItem] = []


# ── Full Generation ────────────────────────────────────────────────────────

class GenerationRequest(BaseModel):
    model: str | None = None  # optional model override, e.g. "deepseek:deepseek-chat"


class GenerationResultResponse(BaseModel):
    success: bool = True
    pages_created: list[str] = []
    errors: list[str] = []
