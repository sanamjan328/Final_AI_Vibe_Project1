"""System / health endpoints."""

from __future__ import annotations

import os

from fastapi import APIRouter


router = APIRouter()


@router.get("/health")
async def health() -> dict:
    mode = "massive" if os.getenv("MASSIVE_API_KEY", "").strip() else "simulator"
    return {"status": "ok", "mode": mode}
