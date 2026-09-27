"""CRUD routes for notes."""

from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pymongo import ReturnDocument

from app.db import get_notes_collection, require_database
from app.models.note import NoteCreate, NoteOut, NoteUpdate

router = APIRouter(
    prefix="/notes",
    tags=["notes"],
    dependencies=[Depends(require_database)],
)


def _serialize(doc: dict) -> NoteOut:
    """Convert a MongoDB document into a NoteOut schema."""
    return NoteOut(
        _id=str(doc["_id"]),
        userId=doc["userId"],
        title=doc["title"],
        body=doc.get("body", ""),
        tags=doc.get("tags", []),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _parse_object_id(note_id: str) -> ObjectId:
    """Parse a path id into ObjectId or raise 422."""
    try:
        return ObjectId(note_id)
    except (InvalidId, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid note id: {note_id}",
        ) from exc


@router.get("", response_model=list[NoteOut])
async def list_notes(
    userId: str = Query(..., min_length=1),
    tag: str | None = Query(default=None),
) -> list[NoteOut]:
    """List notes for a user, optionally filtered by tag."""
    collection = get_notes_collection()
    query: dict = {"userId": userId}
    if tag is not None:
        query["tags"] = tag
    cursor = collection.find(query).sort("created_at", -1)
    return [_serialize(doc) async for doc in cursor]


@router.get("/{note_id}", response_model=NoteOut)
async def get_note(
    note_id: str,
    userId: str = Query(..., min_length=1),
) -> NoteOut:
    """Fetch a single note by id for a user."""
    collection = get_notes_collection()
    oid = _parse_object_id(note_id)
    doc = await collection.find_one({"_id": oid, "userId": userId})
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return _serialize(doc)


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED)
async def create_note(payload: NoteCreate) -> NoteOut:
    """Create a new note owned by the given userId."""
    collection = get_notes_collection()
    now = datetime.now(timezone.utc)
    doc = {
        "userId": payload.userId,
        "title": payload.title,
        "body": payload.body,
        "tags": payload.tags,
        "created_at": now,
        "updated_at": now,
    }
    result = await collection.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _serialize(doc)


@router.put("/{note_id}", response_model=NoteOut)
async def replace_note(
    note_id: str,
    payload: NoteCreate,
    userId: str = Query(..., min_length=1),
) -> NoteOut:
    """Replace an existing note (full update). Ownership (userId) is immutable."""
    collection = get_notes_collection()
    oid = _parse_object_id(note_id)
    # Match both _id and userId; do not overwrite ownership from the body.
    update = {
        "title": payload.title,
        "body": payload.body,
        "tags": payload.tags,
        "updated_at": datetime.now(timezone.utc),
    }
    result = await collection.find_one_and_update(
        {"_id": oid, "userId": userId},
        {"$set": update},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return _serialize(result)


@router.patch("/{note_id}", response_model=NoteOut)
async def update_note(
    note_id: str,
    payload: NoteUpdate,
    userId: str = Query(..., min_length=1),
) -> NoteOut:
    """Partially update an existing note. Ownership (userId) is immutable."""
    collection = get_notes_collection()
    oid = _parse_object_id(note_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No fields provided for update",
        )
    changes["updated_at"] = datetime.now(timezone.utc)
    result = await collection.find_one_and_update(
        {"_id": oid, "userId": userId},
        {"$set": changes},
        return_document=ReturnDocument.AFTER,
    )
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
    return _serialize(result)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: str,
    userId: str = Query(..., min_length=1),
) -> None:
    """Delete a note by id for a user."""
    collection = get_notes_collection()
    oid = _parse_object_id(note_id)
    result = await collection.delete_one({"_id": oid, "userId": userId})
    if result.deleted_count == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")
