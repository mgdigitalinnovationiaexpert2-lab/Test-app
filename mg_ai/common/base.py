"""Pydantic base model shared by every DTO in the project."""
from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Reject unknown fields everywhere; strict contracts at every boundary."""

    model_config = ConfigDict(extra="forbid")
