"""Consent-gated cross-session preference memory (FR-22).

Only confirmed, non-financial preferences are remembered, and only while the
renter has the `remember_sessions` consent on. A new session gets them as
`inferred` draft fields with `memory:<session>` evidence, so the renter must
confirm again; memory never becomes a confirmed profile by itself. Money,
income, loan terms, destinations and raw chat are never stored.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import DraftProfile, Profile

REMEMBERED_FIELDS = ("city", "area", "room_type", "bedrooms", "preferences", "soft_description")


def consented(repo, user_id: str) -> bool:
    row = repo.db.execute("SELECT consents_json FROM hm_account_profiles WHERE user_id=?", (user_id,)).fetchone()
    return bool(row and json.loads(row["consents_json"]).get("remember_sessions"))


def remember(repo, user_id: str, session_id: str, profile: Profile) -> bool:
    if not consented(repo, user_id):
        return False
    payload = {"city": profile.city, "area": profile.area, "room_type": profile.room_type,
               "bedrooms": profile.min_bedrooms,
               "preferences": sorted(set(profile.preferences) | set(profile.must_amenities)),
               "soft_description": profile.soft_description}
    with repo.db:
        repo.db.execute("INSERT INTO hm_preference_memory(user_id,payload_json,source_session,updated_at) "
                        "VALUES(?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET payload_json=excluded.payload_json,"
                        "source_session=excluded.source_session,updated_at=excluded.updated_at",
                        (user_id, json.dumps(payload, ensure_ascii=False), session_id,
                         datetime.now(timezone.utc).isoformat()))
    return True


def recall(repo, user_id: str) -> dict | None:
    """Stored memory, or None when absent or the consent has been withdrawn."""
    if not consented(repo, user_id):
        return None
    row = repo.db.execute("SELECT payload_json,source_session,updated_at FROM hm_preference_memory WHERE user_id=?",
                          (user_id,)).fetchone()
    if row is None:
        return None
    return {"fields": json.loads(row["payload_json"]), "source_session": row["source_session"],
            "updated_at": row["updated_at"]}


def forget(repo, user_id: str, field: str | None = None) -> dict:
    with repo.db:
        if field is None:
            repo.db.execute("DELETE FROM hm_preference_memory WHERE user_id=?", (user_id,))
            return {"status": "forgotten"}
        row = repo.db.execute("SELECT payload_json FROM hm_preference_memory WHERE user_id=?", (user_id,)).fetchone()
        if row is not None:
            payload = json.loads(row["payload_json"])
            payload[field] = [] if field == "preferences" else None
            repo.db.execute("UPDATE hm_preference_memory SET payload_json=? WHERE user_id=?",
                            (json.dumps(payload, ensure_ascii=False), user_id))
    return {"status": "forgotten", "field": field}


def prefill(draft: DraftProfile, memory: dict) -> DraftProfile:
    evidence = f"memory:{memory['source_session']}"
    for field in REMEMBERED_FIELDS:
        value = memory["fields"].get(field)
        if value in (None, [], ""):
            continue
        setattr(draft, field, value)
        draft.field_status[field] = "inferred"
        draft.evidence_ref[field] = evidence
    return DraftProfile.model_validate(draft.model_dump())
