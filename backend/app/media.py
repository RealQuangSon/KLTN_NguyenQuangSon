"""Listing and maintenance photo media.

Files are stored content-addressed on disk under HOMEMATCH_MEDIA_DIR
(`{sha256[:2]}/{sha256}.{ext}`), never under a user-supplied filename, and the
metadata rows live in the hm_media ledger. The image type is decided by magic
bytes, never by the client's content type; unknown bytes, oversized uploads
and per-owner photo limits are rejected with explicit domain errors. Deleting
a photo removes the ledger row and unlinks the file only when no other record
still references the same content hash.
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .models import DomainError

MAX_BYTES = 5 * 1024 * 1024
OWNER_LIMITS = {"room": 10, "maintenance": 5}
LIMIT_MESSAGE = {"room": "Mỗi tin tối đa 10 ảnh.", "maintenance": "Mỗi sự cố tối đa 5 ảnh."}

# (magic bytes, content type, file extension); WebP is checked separately
# because its signature carries a size placeholder in the middle.
MAGIC = (
    (b"\xff\xd8\xff", "image/jpeg", "jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", "png"),
)
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def media_dir() -> Path:
    # Read per call so tests and deployment configuration can override it.
    return Path(os.getenv("HOMEMATCH_MEDIA_DIR", ".local/media"))


def sniff(head: bytes) -> tuple[str, str]:
    for magic, content_type, ext in MAGIC:
        if head.startswith(magic):
            return content_type, ext
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise DomainError("invalid_media", "Tệp không phải ảnh JPEG, PNG hoặc WebP hợp lệ.", 422)


def file_path(record: dict) -> Path:
    return media_dir() / record["sha256"][:2] / f"{record['sha256']}.{EXTENSIONS[record['content_type']]}"


def projection(record: dict) -> dict:
    return {"id": record["id"], "url": f"/media/{record['id']}", "content_type": record["content_type"],
            "size_bytes": record["size_bytes"], "position": record["position"]}


def get(repo, media_id: str) -> dict:
    row = repo.db.execute("SELECT * FROM hm_media WHERE id=?", (media_id,)).fetchone()
    if row is None:
        raise DomainError("not_found", "Không tìm thấy ảnh.", 404)
    return dict(row)


def photos(repo, owner_kind: str, owner_id: str) -> list[dict]:
    """Photos of one listing/maintenance ticket in display order."""
    rows = repo.db.execute("SELECT id FROM hm_media WHERE owner_kind=? AND owner_id=? "
                           "ORDER BY position, created_at, id", (owner_kind, owner_id)).fetchall()
    return [{"id": row["id"], "url": f"/media/{row['id']}"} for row in rows]


def photos_by_owner(repo, owner_kind: str) -> dict[str, list[dict]]:
    """Photos of every owner of one kind in a single query, for list pages (no per-room round trip)."""
    grouped: dict[str, list[dict]] = {}
    for row in repo.db.execute("SELECT owner_id, id FROM hm_media WHERE owner_kind=? "
                               "ORDER BY owner_id, position, created_at, id", (owner_kind,)).fetchall():
        grouped.setdefault(row["owner_id"], []).append({"id": row["id"], "url": f"/media/{row['id']}"})
    return grouped


def store(repo, owner_kind: str, owner_id: str, uploader_id: str, file) -> tuple[dict, bool]:
    """Validate, persist and index one upload from a binary file object.
    Returns (record, created); a duplicate upload (same owner + content hash)
    returns the existing record."""
    if owner_kind not in OWNER_LIMITS:
        raise DomainError("invalid_request", "Loại ảnh không được hỗ trợ.", 422)
    data = file.read(MAX_BYTES + 1)  # Read at most 5 MB + 1 byte, then stop.
    if len(data) > MAX_BYTES:
        raise DomainError("media_too_large", "Ảnh vượt quá 5 MB.", 422)
    if not data:
        raise DomainError("invalid_media", "Tệp không phải ảnh JPEG, PNG hoặc WebP hợp lệ.", 422)
    content_type, ext = sniff(data[:16])
    sha256 = hashlib.sha256(data).hexdigest()
    existing = repo.db.execute("SELECT * FROM hm_media WHERE owner_kind=? AND owner_id=? AND sha256=?",
                               (owner_kind, owner_id, sha256)).fetchone()
    if existing:
        return dict(existing), False
    count = repo.db.execute("SELECT COUNT(*) AS n FROM hm_media WHERE owner_kind=? AND owner_id=?",
                            (owner_kind, owner_id)).fetchone()["n"]
    if count >= OWNER_LIMITS[owner_kind]:
        raise DomainError("media_limit", LIMIT_MESSAGE[owner_kind], 422)
    path = media_dir() / sha256[:2] / f"{sha256}.{ext}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    media_id = str(uuid4())
    with repo.db:
        try:
            repo.db.execute("INSERT INTO hm_media(id,owner_kind,owner_id,uploader_id,content_type,size_bytes,"
                            "sha256,position,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            (media_id, owner_kind, owner_id, uploader_id, content_type, len(data), sha256,
                             count, datetime.now(timezone.utc).isoformat()))
        except Exception:
            raise DomainError("media_exists", "Ảnh này đã có trong danh sách.", 409) from None
    return projection(get(repo, media_id)), True


def delete(repo, media_id: str) -> None:
    record = get(repo, media_id)
    sha256 = record["sha256"]
    with repo.db:
        repo.db.execute("DELETE FROM hm_media WHERE id=?", (media_id,))
    # The file is content-addressed and possibly shared: unlink only the last reference.
    remaining = repo.db.execute("SELECT COUNT(*) AS n FROM hm_media WHERE sha256=?", (sha256,)).fetchone()["n"]
    if remaining == 0:
        file_path(record).unlink(missing_ok=True)


def reorder(repo, owner_kind: str, owner_id: str, media_ids: list[str]) -> list[dict]:
    """Rewrite display positions to the given order; the list must match the
    current photo set exactly (no missing, no foreign, no duplicated id)."""
    current = [row["id"] for row in repo.db.execute(
        "SELECT id FROM hm_media WHERE owner_kind=? AND owner_id=?", (owner_kind, owner_id)).fetchall()]
    if len(media_ids) != len(set(media_ids)) or sorted(media_ids) != sorted(current):
        raise DomainError("invalid_request", "Danh sách thứ tự phải gồm đúng các ảnh hiện có.", 422)
    with repo.db:
        for position, media_id in enumerate(media_ids):
            repo.db.execute("UPDATE hm_media SET position=? WHERE id=?", (position, media_id))
    return [projection(get(repo, media_id)) for media_id in media_ids]
