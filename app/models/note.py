"""Pydantic schemas for note documents."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class NoteCreate(BaseModel):
    """Payload for creating a note."""

    userId: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    body: str = ""
    tags: list[str] = Field(default_factory=list)


class NoteUpdate(BaseModel):
    """Payload for partial or full note updates."""

    title: str | None = Field(default=None, min_length=1)
    body: str | None = None
    tags: list[str] | None = None


class NoteOut(BaseModel):
    """Note representation returned by the API."""

    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(..., alias="_id")
    userId: str
    title: str
    body: str = ""
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
