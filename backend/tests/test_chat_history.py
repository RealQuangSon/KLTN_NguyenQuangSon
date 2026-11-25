from datetime import datetime, timedelta, timezone

import pytest

from backend.app.models import Actor, DomainError
from backend.app.service import CHAT_RETENTION_DAYS


def chat(service, renter, text, extra=()):
    sid = service.create_session(renter)["session_id"]
    for message in (text, *extra):
        service.message(sid, renter, message)
    return sid


def test_history_lists_newest_first_with_titles_and_turns(service, renter):
    first = chat(service, renter, "Tìm phòng TP.HCM Quận 7", extra=("Ngân sách 5 triệu",))
    second = chat(service, renter, "Cần studio ở Cầu Giấy")
    service.create_session(renter)  # created but never messaged
    result = service.chat_history(renter)
    assert result["retention_days"] == CHAT_RETENTION_DAYS
    assert [item["session_id"] for item in result["items"]] == [second, first]
    by_id = {item["session_id"]: item for item in result["items"]}
    assert by_id[first]["title"] == "Tìm phòng TP.HCM Quận 7" and by_id[first]["turns"] == 2
    assert by_id[second]["title"] == "Cần studio ở Cầu Giấy" and by_id[second]["turns"] == 1
    assert by_id[first]["started_at"] <= by_id[first]["last_at"]


def test_title_is_masked_and_truncated(service, renter):
    sid = chat(service, renter, "Gọi tôi 0901234567 để tìm phòng " + "rất " * 40)
    title = service.chat_history(renter)["items"][0]["title"]
    assert "0901234567" not in title and len(title) <= 81 and title.endswith("…")
    assert service.chat_history(renter, limit=1)["items"][0]["session_id"] == sid


def test_other_renter_and_roles_are_refused(service, renter, owner, admin):
    sid = chat(service, renter, "Tìm phòng Quận 7")
    other = Actor(id="renter-b", role="renter")
    assert service.chat_history(other)["items"] == []
    with pytest.raises(DomainError) as denied:
        service.chat_transcript(other, sid)
    assert denied.value.http_status == 403
    for actor in (owner, admin):
        with pytest.raises(DomainError) as error:
            service.chat_history(actor)
        assert error.value.http_status == 403


def test_transcript_order_and_no_internal_fields(service, renter):
    sid = chat(service, renter, "Tìm phòng Quận 7", extra=("Cảm ơn",))
    transcript = service.chat_transcript(renter, sid)
    assert transcript["session_id"] == sid
    assert [m["role"] for m in transcript["messages"]] == ["user", "assistant", "user", "assistant"]
    assert transcript["messages"][0]["text"] == "Tìm phòng Quận 7"
    assert all(set(m) == {"role", "text", "created_at"} for m in transcript["messages"])
    empty = service.create_session(renter)["session_id"]
    assert service.chat_transcript(renter, empty)["messages"] == []


def test_rows_older_than_retention_are_excluded(service, renter):
    sid = service.create_session(renter)["session_id"]
    old = (datetime.now(timezone.utc) - timedelta(days=CHAT_RETENTION_DAYS + 5)).isoformat()
    with service.repo.db:
        for speaker in ("user", "assistant"):
            service.repo.db.execute("INSERT INTO hm_chat_transcripts VALUES(?,?,?,?,?,?,?,?)",
                                    (f"old-{speaker}", sid, renter.id, speaker, "tin cũ", None, None, old))
    assert service.chat_history(renter)["items"] == []
    assert service.chat_transcript(renter, sid)["messages"] == []
