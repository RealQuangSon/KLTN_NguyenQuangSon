"""Consent-gated cross-session preference memory (FR-22).

Only confirmed, non-financial preferences are remembered, and only while the
renter has the `remember_sessions` consent on. A new session gets them as
`inferred` draft fields with `memory:<session>` evidence, so the renter must
confirm again; memory never becomes a confirmed profile by itself. Money,
income, loan terms, destinations and raw chat are never stored.

Preferences accumulate; location and room type keep the latest confirmed value:
- a preference confirmed in a session gains one session of evidence;
- one the draft offered and the renter removed is dropped and muted, so saved
  rooms cannot suggest it again until the renter confirms it themselves;
- one absent from `MAX_MISSES` confirmed sessions in a row decays away;
- an amenity shared by the saved rooms, and rarer in the catalog, is suggested
  with no session evidence, and leaves when those rooms are unsaved.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from .models import AMENITY_KEYS, DraftProfile, Profile

AMENITIES = frozenset(AMENITY_KEYS)
REMEMBERED_FIELDS = ("city", "area", "room_type", "bedrooms", "preferences", "soft_description")
MAX_MISSES = 2
MAX_PREFILLED_PREFERENCES = 6
# An amenity counts as a saved-room signal only with all three.
SAVED_MIN_ROOMS = 2
SAVED_MIN_SHARE = 0.6
SAVED_MIN_LIFT = 1.5


def consented(repo, user_id: str) -> bool:
    row = repo.db.execute("SELECT consents_json FROM hm_account_profiles WHERE user_id=?", (user_id,)).fetchone()
    return bool(row and json.loads(row["consents_json"]).get("remember_sessions"))


def saved_signals(saved_rooms: list, catalog_rooms: list) -> list[str]:
    """Amenities the saved rooms share more often than the catalog does. Unknown is not `True`."""
    published = [room for room in catalog_rooms if room.published]
    if len(saved_rooms) < SAVED_MIN_ROOMS or not published:
        return []
    signals = []
    for key in sorted(AMENITIES):
        count = sum(room.amenities.get(key) is True for room in saved_rooms)
        share = count / len(saved_rooms)
        base = sum(room.amenities.get(key) is True for room in published) / len(published)
        if count >= SAVED_MIN_ROOMS and share >= SAVED_MIN_SHARE and share >= SAVED_MIN_LIFT * base:
            signals.append(key)
    return signals


def _stats(payload: dict, source_session: str | None) -> dict[str, dict]:
    """Per-preference evidence; rows written before accumulation count as one session."""
    if "preference_stats" in payload:
        return payload["preference_stats"]
    return {key: {"sessions": 1, "misses": 0, "saved": False, "last_session": source_session}
            for key in payload.get("preferences") or []}


def _ordered(stats: dict[str, dict]) -> list[str]:
    """Strongest evidence first; the key breaks ties so the order is deterministic."""
    return sorted(stats, key=lambda key: (-stats[key]["sessions"], key))


def _merge(stats: dict[str, dict], muted: set[str], session_id: str, kept: set[str],
           offered: set[str], saved: set[str]) -> tuple[dict[str, dict], set[str]]:
    stats, muted = {key: dict(value) for key, value in stats.items()}, set(muted)
    muted |= offered - kept
    muted -= kept
    for key in kept:
        entry = stats.setdefault(key, {"sessions": 0, "misses": 0, "saved": False, "last_session": None})
        if entry["last_session"] != session_id:
            entry["sessions"] += 1
        entry.update(misses=0, last_session=session_id)
    for key, entry in stats.items():
        if key not in kept and entry["sessions"] and entry["last_session"] != session_id:
            entry.update(misses=entry["misses"] + 1, last_session=session_id)
    for key in saved - muted:
        stats.setdefault(key, {"sessions": 0, "misses": 0, "saved": False, "last_session": None})
    merged = {}
    for key, entry in stats.items():
        entry["saved"] = key in saved
        if key in muted or entry["misses"] >= MAX_MISSES or not (entry["sessions"] or entry["saved"]):
            continue
        merged[key] = entry
    return merged, muted


def remember(repo, user_id: str, session_id: str, profile: Profile, offered: list[str] | None = None,
             saved: list[str] | None = None) -> bool:
    """`offered` is what the draft held at confirmation; `saved` comes from `saved_signals`."""
    if not consented(repo, user_id):
        return False
    row = repo.db.execute("SELECT payload_json,source_session FROM hm_preference_memory WHERE user_id=?",
                          (user_id,)).fetchone()
    previous = json.loads(row["payload_json"]) if row else {}
    stats, muted = _merge(_stats(previous, row["source_session"] if row else None), set(previous.get("muted") or []),
                          session_id, set(profile.preferences) | set(profile.must_amenities),
                          set(offered or []), set(saved or []))
    payload = {"city": profile.city, "area": profile.area, "room_type": profile.room_type,
               "bedrooms": profile.min_bedrooms, "preferences": _ordered(stats),
               "soft_description": profile.soft_description,
               "preference_stats": stats, "muted": sorted(muted)}
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
    payload = json.loads(row["payload_json"])
    stats = _stats(payload, row["source_session"])
    fields = {field: payload.get(field) for field in REMEMBERED_FIELDS}
    fields["preferences"] = _ordered(stats)
    return {"fields": fields, "source_session": row["source_session"], "updated_at": row["updated_at"],
            "preference_details": [{"key": key, "sessions": stats[key]["sessions"], "from_saved": stats[key]["saved"]}
                                   for key in fields["preferences"]]}


def forget(repo, user_id: str, field: str | None = None) -> dict:
    with repo.db:
        if field is None:
            repo.db.execute("DELETE FROM hm_preference_memory WHERE user_id=?", (user_id,))
            return {"status": "forgotten"}
        row = repo.db.execute("SELECT payload_json,source_session FROM hm_preference_memory WHERE user_id=?",
                              (user_id,)).fetchone()
        if row is not None:
            payload = json.loads(row["payload_json"])
            if field == "preferences":
                _write_preferences(repo, user_id, payload, row["source_session"], set(_stats(payload, None)))
            else:
                payload[field] = None
                repo.db.execute("UPDATE hm_preference_memory SET payload_json=? WHERE user_id=?",
                                (json.dumps(payload, ensure_ascii=False), user_id))
    return {"status": "forgotten", "field": field}


def forget_preference(repo, user_id: str, key: str) -> dict:
    """Remove one preference and keep saved rooms from suggesting it again."""
    with repo.db:
        row = repo.db.execute("SELECT payload_json,source_session FROM hm_preference_memory WHERE user_id=?",
                              (user_id,)).fetchone()
        if row is not None:
            _write_preferences(repo, user_id, json.loads(row["payload_json"]), row["source_session"], {key})
    return {"status": "forgotten", "field": key}


def _write_preferences(repo, user_id: str, payload: dict, source_session: str, removed: set[str]) -> None:
    stats = {key: value for key, value in _stats(payload, source_session).items() if key not in removed}
    payload.update(preference_stats=stats, preferences=_ordered(stats),
                   muted=sorted(set(payload.get("muted") or []) | removed))
    repo.db.execute("UPDATE hm_preference_memory SET payload_json=? WHERE user_id=?",
                    (json.dumps(payload, ensure_ascii=False), user_id))


def prefill(draft: DraftProfile, memory: dict) -> DraftProfile:
    evidence = f"memory:{memory['source_session']}"
    for field in REMEMBERED_FIELDS:
        value = memory["fields"].get(field)
        if value in (None, [], ""):
            continue
        if field == "preferences":
            value = value[:MAX_PREFILLED_PREFERENCES]
        setattr(draft, field, value)
        draft.field_status[field] = "inferred"
        draft.evidence_ref[field] = evidence
    return DraftProfile.model_validate(draft.model_dump())
