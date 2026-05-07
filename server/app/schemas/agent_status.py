"""
Agent status Pydantic schemas
"""
from pydantic import BaseModel


class AgentStatusResponse(BaseModel):
    user_id: int
    status: str
    current_count: int
    max_concurrent: int


class AgentStatusUpdate(BaseModel):
    status: str


class AgentStatsResponse(BaseModel):
    current_count: int
    max_concurrent: int
