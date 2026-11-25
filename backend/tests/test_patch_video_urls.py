"""The one-off video URL patch tool.

The rebuild snapshot r2 had video URLs PII-masked by mistake (digit runs in the
32-hex Stream id); the tool restores `source_videos` from the directly-crawled
snapshot and must change ONLY that field. Pure fixtures, no network, no DB.
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from infra.patch_video_urls import build_patch, valid_entry  # noqa: E402

GOOD = "97400dfa043909842d35f1280ee9e0a6"
GOOD_URL = f"https://videodelivery.net/{GOOD}/manifest/video.m3u8"
GOOD_THUMB = f"https://videodelivery.net/{GOOD}/thumbnails/thumbnail.jpg"
MASKED = "https://videodelivery.net/97400dfa[SĐT đã che]d35f1280ee9e0a6/manifest/video.m3u8"


def _room(room_id, videos):
    return {"id": room_id, "revision": 1, "source_videos": videos}


def _write_snapshot(path, rooms):
    path.mkdir(parents=True, exist_ok=True)
    (path / "catalog.json").write_text(
        json.dumps({"snapshot_id": path.name, "rooms": rooms}, ensure_ascii=False),
        encoding="utf-8")
    (path / "manifest.json").write_text(
        json.dumps({"snapshot_id": path.name, "catalog_sha256": "x"}, ensure_ascii=False),
        encoding="utf-8")


def test_valid_entry_accepts_only_strict_stream_shapes():
    assert valid_entry({"url": GOOD_URL, "thumbnail": GOOD_THUMB})
    assert not valid_entry({"url": MASKED, "thumbnail": GOOD_THUMB})
    assert not valid_entry({"url": GOOD_URL,
                            "thumbnail": "https://videodelivery.net.evil.com/"
                                         f"{GOOD}/thumbnails/thumbnail.jpg"})
    assert not valid_entry({"url": GOOD_URL, "thumbnail": None})


def test_build_patch_restores_from_source_and_reports(tmp_path):
    broken = _room("chotot-1", [{"url": MASKED, "thumbnail": MASKED.replace(
        "manifest/video.m3u8", "thumbnails/thumbnail.jpg")}])
    donor = _room("chotot-1", [{"url": GOOD_URL, "thumbnail": GOOD_THUMB}])
    untouched = _room("chotot-2", [{"url": GOOD_URL, "thumbnail": GOOD_THUMB}])
    _write_snapshot(tmp_path / "r2", [broken, untouched])
    _write_snapshot(tmp_path / "src", [donor])
    patches, stats = build_patch(tmp_path / "r2" / "catalog.json",
                                 tmp_path / "src" / "catalog.json")
    assert patches == {"chotot-1": [{"url": GOOD_URL, "thumbnail": GOOD_THUMB}]}
    assert stats == {"restored_from_source": 1, "emptied": 0}


def test_build_patch_empties_when_source_has_no_valid_url(tmp_path):
    broken = _room("chotot-3", [{"url": MASKED, "thumbnail": MASKED}])
    _write_snapshot(tmp_path / "r2", [broken])
    _write_snapshot(tmp_path / "src", [])  # phòng không có ở catalog nguồn
    patches, stats = build_patch(tmp_path / "r2" / "catalog.json",
                                 tmp_path / "src" / "catalog.json")
    assert patches == {"chotot-3": []}
    assert stats == {"restored_from_source": 0, "emptied": 1}


def test_local_patch_changes_only_source_videos(tmp_path, monkeypatch):
    import infra.patch_video_urls as tool
    broken = _room("chotot-4", [{"url": MASKED, "thumbnail": MASKED}])
    donor = _room("chotot-4", [{"url": GOOD_URL, "thumbnail": GOOD_THUMB}])
    healthy = _room("chotot-5", [{"url": GOOD_URL, "thumbnail": GOOD_THUMB}])
    _write_snapshot(tmp_path / "r2", [broken, healthy])
    _write_snapshot(tmp_path / "src", [donor])
    before = json.loads((tmp_path / "r2" / "catalog.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(tool, "R2_SNAPSHOT", "r2")
    monkeypatch.setattr(tool, "SOURCE_SNAPSHOT", "src")
    result = tool._patch_catalog_file(tmp_path / "r2",
                                      build_patch(tmp_path / "r2" / "catalog.json",
                                                  tmp_path / "src" / "catalog.json")[0])
    assert result["rooms_patched"] == 1
    after = json.loads((tmp_path / "r2" / "catalog.json").read_text(encoding="utf-8"))
    assert after == {"snapshot_id": "r2", "rooms": [donor, healthy]}
    manifest = json.loads((tmp_path / "r2" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["videos_restored"] == 1
    assert manifest["videos_restored_from"] == "src"
    assert manifest["catalog_sha256"] == hashlib.sha256(
        (tmp_path / "r2" / "catalog.json").read_bytes()).hexdigest()
    # Chạy lại khi không còn gì để vá không được ghi đè
    # videos_restored thành 0 (giá trị đúng của r2 là số đã vá lần đầu).
    again = tool._patch_catalog_file(tmp_path / "r2", {})
    assert again["rooms_patched"] == 0
    manifest = json.loads((tmp_path / "r2" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["videos_restored"] == 1, "re-run must not overwrite videos_restored with 0"
