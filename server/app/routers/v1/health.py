"""
Health check router
"""
from fastapi import APIRouter

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}
