"""Bổ sung phí và thông tin còn thiếu cho snapshot Chợ Tốt bằng LLM, có kiểm chứng tất định.

Regex của crawler chỉ đọc được đủ 5 loại phí ở 14/2.779 tin. Module này gửi nội
dung tin (đã che SĐT/email trong raw/) cho LLM để đề xuất phí, điều khoản thuê
(kỳ thanh toán, thời hạn tối thiểu, ngày trống), tiện ích — nhưng **không tin
LLM**: một giá trị chỉ được nhận khi qua hết các kiểm tra của `verify`:

- `evidence` là đoạn trích nguyên văn có trong tin (so trên bản bỏ dấu);
- phí: đoạn trích nhắc đúng loại phí, số tiền đọc lại được bằng `parse_vnd`,
  cách tính hợp với loại phí và số nằm trong khoảng hợp lý của `FEE_RULES`;
- điều khoản: chính regex của crawler phải đọc lại được cùng số tháng/ngày
  trong chính đoạn trích;
- tiện ích: `detect_amenities` của crawler chạy trên riêng đoạn trích phải cho
  cùng giá trị (false phải có phủ định trong đoạn trích).

LLM chỉ **điền chỗ còn null**; giá trị regex/API đã có thì không ghi đè. Chỗ
nào không qua kiểm tra vẫn `null` (không bao giờ 0). Kết quả là snapshot mới
(snapshot cũ bất biến), có `derived_from`, thống kê nhận/loại theo lý do và
`review.csv` để gán nhãn tay đo độ chính xác.

Chạy thật tốn tiền API nên cần `--allow-live`; nên thử `--limit 50` trước.
Mỗi tin đã gọi được lưu vào `llm_cache.jsonl` theo `EXTRACTOR_VERSION` — đổi
prompt là đổi version, cache cũ tự hết hiệu lực.
Chợ Tốt ghi `ai-train=no`: đây là trích xuất, không dùng để huấn luyện mô hình.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator

from backend.app.costs import REQUIRED_FEES
from backend.app.models import AMENITY_KEYS
from data.crawl_chotot import (AMOUNT, AVAILABLE_FROM, FEE_RULES, ROOT, detect_amenities, feature_text, fold,
                               keep_order, parse_available_from, parse_min_lease, parse_payment_cycle,
                               parse_vnd)

EXTRACTOR_VERSION = "2.0"
INCLUDED_WORDS = re.compile(r"\b(?:free|mien phi|bao gom|da gom)\b")
# Cùng từ khóa với FEE_RULES của crawler.
FEE_KEYWORDS = {name: re.compile(rf"\b(?:{keywords})\b") for name, keywords in {
    "electricity": "dien", "water": "nuoc", "internet": "wifi|internet|mang",
    "parking": "xe|giu xe|gui xe", "service": "dich vu|phi quan ly|phi dv|dv"}.items()}
RULES = {(rule.name, rule.mode): rule for rule in FEE_RULES}
DATE_CANDIDATE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2,4}))?$")

SYSTEM_PROMPT = f"""Bạn đọc một tin cho thuê phòng tiếng Việt và liệt kê thông tin được ghi RÕ trong tin,
theo ba nhóm. Không đoán; thông tin không ghi rõ thì bỏ qua.
1) Phí hằng tháng. Chỉ các loại: electricity (điện, mode kwh), water (nước, mode person hoặc m3),
internet (wifi/mạng, mode fixed), parking (giữ xe, mode vehicle), service (phí dịch vụ/quản lý, mode fixed).
Với mỗi phí: amount_vnd là số đồng (ví dụ "3k5/số" → 3500, "100k/người" → 100000); evidence là đoạn trích
NGUYÊN VĂN ngắn từ tin chứa cả tên phí và con số. Tin ghi miễn phí hoặc đã bao gồm thì included_in_rent=true,
amount_vnd=0. Không có phí nào thì trả danh sách rỗng.
2) Điều khoản thuê: payment_cycle_months (trả tiền mỗi mấy tháng: "đóng 3 tháng/lần" → 3),
min_lease_months (thời hạn hợp đồng tối thiểu: "HĐ tối thiểu 6 tháng" → 6, "HĐ 1 năm" → 12),
available_from (ngày trống, dạng D/M hoặc D/M/YYYY: "trống từ 1/12" → "1/12").
Mỗi mục kèm evidence là đoạn trích NGUYÊN VĂN chứa cả từ khóa và con số/ngày.
3) Tiện ích: chỉ dùng các khóa sau: {", ".join(AMENITY_KEYS)}.
value là true hoặc false; evidence là đoạn trích NGUYÊN VĂN chứa từ khóa của khóa đó
(value=false chỉ khi đoạn trích có chữ "không/cấm"). Không có thì bỏ qua."""


class FeeCandidate(BaseModel):
    name: Literal["electricity", "water", "internet", "parking", "service"]
    amount_vnd: int | None = Field(default=None, ge=0)
    mode: Literal["fixed", "person", "vehicle", "kwh", "m3"]
    included_in_rent: bool = False
    evidence: str = Field(max_length=300)


class AmenityCandidate(BaseModel):
    key: Literal[tuple(AMENITY_KEYS)]  # type: ignore[arg-type]
    value: bool
    evidence: str = Field(max_length=300)


class ListingExtraction(BaseModel):
    fees: list[FeeCandidate] = Field(default_factory=list)
    payment_cycle_months: int | None = Field(default=None, ge=1, le=12)
    payment_cycle_evidence: str | None = Field(default=None, max_length=300)
    min_lease_months: int | None = Field(default=None, ge=1, le=60)
    min_lease_evidence: str | None = Field(default=None, max_length=300)
    available_from: str | None = Field(default=None, max_length=20)
    available_from_evidence: str | None = Field(default=None, max_length=300)
    amenities: list[AmenityCandidate] = Field(default_factory=list)

    @field_validator("available_from")
    @classmethod
    def date_shape(cls, value):
        if value is not None and DATE_CANDIDATE.match(value.replace(" ", "")) is None:
            raise ValueError("available_from phải là D/M hoặc D/M/YYYY")
        return value


# Tên cũ còn dùng trong test hiện có.
FeeExtraction = ListingExtraction


class FeeExtractor(Protocol):
    model: str

    def extract(self, text: str) -> tuple[ListingExtraction, int | None]: ...


class OpenAIFeeExtractor:
    """Cùng cấu hình với interpreter.py: OPENAI_API_KEY, OPENAI_BASE_URL, HOMEMATCH_LLM_API."""

    def __init__(self, model: str | None = None, client=None):
        from openai import OpenAI

        from backend.app.interpreter import llm_api, reported_tokens
        self.client = client if client is not None else OpenAI(timeout=30, max_retries=2)
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-2024-08-06")
        self.api = llm_api()
        self._tokens = reported_tokens

    def extract(self, text: str) -> tuple[ListingExtraction, int | None]:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]
        if self.api == "chat_completions":
            response = self.client.chat.completions.parse(
                model=self.model, messages=messages, response_format=ListingExtraction, max_completion_tokens=800)
            parsed = response.choices[0].message.parsed
        else:
            response = self.client.responses.parse(
                model=self.model, store=False, max_output_tokens=800, input=messages, text_format=ListingExtraction)
            parsed = response.output_parsed
        return ListingExtraction.model_validate(parsed or {"fees": []}), self._tokens(getattr(response, "usage", None))


def verify(candidate: FeeCandidate, text: str) -> str | None:
    """None nếu phí được nhận; ngược lại là lý do loại."""
    evidence = " ".join(fold(candidate.evidence).split())
    if not evidence or evidence not in " ".join(fold(text).split()):
        return "evidence_not_in_post"
    if not FEE_KEYWORDS[candidate.name].search(evidence):
        return "evidence_wrong_fee"
    if candidate.included_in_rent:
        return None if INCLUDED_WORDS.search(evidence) and not candidate.amount_vnd else "included_not_stated"
    rule = RULES.get((candidate.name, candidate.mode))
    if rule is None:
        return "mode_not_allowed"
    if candidate.amount_vnd is None:
        return "amount_missing"
    amounts = {parse_vnd(m.group(1), m.group(2)) for m in re.finditer(AMOUNT, evidence)}
    if candidate.amount_vnd not in amounts:
        return "amount_not_in_evidence"
    if not rule.low <= candidate.amount_vnd <= rule.high:
        return "amount_out_of_range"
    return None


def _evidence_in_post(evidence: str, text: str) -> str | None:
    folded = " ".join(fold(evidence).split())
    if not folded or folded not in " ".join(fold(text).split()):
        return "evidence_not_in_post"
    return None


def verify_term(name: Literal["payment_cycle_months", "min_lease_months"], value: int,
                evidence: str, text: str) -> str | None:
    """Số tháng phải do chính regex của crawler đọc lại được từ đoạn trích."""
    if reason := _evidence_in_post(evidence, text):
        return reason
    haystack = fold(evidence)
    parsed = (parse_payment_cycle(haystack) if name == "payment_cycle_months"
              else parse_min_lease(haystack))
    return None if parsed == value else "months_not_in_evidence"


def verify_date(candidate: str, evidence: str, text: str, posted_at: datetime | None) -> str | None:
    """Ngày trống: đoạn trích phải chứa đúng ngày dạng D/M(/YYYY) và đọc lại được bằng
    quy tắc "gần nhất sau ngày đăng" của crawler."""
    if reason := _evidence_in_post(evidence, text):
        return reason
    if posted_at is None:
        return "posted_time_unknown"
    haystack = fold(evidence)
    iso = parse_available_from(haystack, posted_at)
    if iso is None:
        return "date_not_in_evidence"
    # Same regex as the crawler: a proposal is only accepted when the crawler
    # itself re-reads the claimed day/month from the evidence.
    match = AVAILABLE_FROM.search(haystack)
    claimed = DATE_CANDIDATE.match(candidate.replace(" ", ""))
    if claimed is None or match is None:
        return "date_not_in_evidence"
    year = claimed.group(3)
    same = (int(claimed.group(1)), int(claimed.group(2))) == (int(match.group(1)), int(match.group(2)))
    same_year = year is None or match.group(3) is None or int(year) == (int(match.group(3)) if len(match.group(3)) == 4 else 2000 + int(match.group(3)))
    return None if same and same_year else "date_not_in_evidence"


def verify_amenity(key: str, value: bool, evidence: str, text: str) -> str | None:
    """Tiện ích: `detect_amenities` chạy trên riêng đoạn trích phải ra đúng giá trị
    (tự phủ định, không cần quy tắc riêng cho khóa "không chung chủ")."""
    if reason := _evidence_in_post(evidence, text):
        return reason
    derived = detect_amenities(evidence).get(key)
    return None if derived is value else "value_not_in_evidence"


def post_texts(snapshot_dir: Path) -> dict[str, str]:
    """Nội dung tin theo room id, dựng từ raw/ (đã che SĐT/email khi cào)."""
    texts = {}
    for page in sorted((snapshot_dir / "raw").glob("page-*.json")):
        for ad in json.loads(page.read_text(encoding="utf-8")):
            if isinstance(ad.get("ad_id"), int):
                texts[f"chotot-{ad['ad_id']}"] = f"{ad.get('subject') or ''}\n{ad.get('body') or ''}\n{feature_text(ad)}"
    return texts


def input_token_estimate(texts: dict[str, str]) -> int:
    """FC-05: ước tính token đầu vào trước khi gọi (chars / 3, thô nhưng an toàn về dư)."""
    return sum(len(text or "") for text in texts.values()) // 3


def live_call_allowed(estimate_tokens: int, confirmed: bool) -> bool:
    """Ước tính trên 1 triệu token đầu vào phải có --yes mới được gọi thật."""
    return confirmed or estimate_tokens <= 1_000_000


def budget_order(rooms: list[dict]) -> list[dict]:
    """FC-05: thứ tự xử lý khi ngân sách có hạn — hai thành phố xen kẽ nhau để
    lượt bị cắt vẫn cân bằng; trong mỗi thành phố individual trước, mới trước cũ
    (cùng mốc ưu tiên với hạn mức cào, keep_order)."""
    by_city: dict[str, list[dict]] = {}
    for room in rooms:
        by_city.setdefault(room.get("city") or "", []).append(room)
    for rows in by_city.values():
        rows.sort(key=keep_order)
    cities = sorted(by_city)
    order: list[dict] = []
    index = 0
    while True:
        added = False
        for city in cities:
            if index < len(by_city[city]):
                order.append(by_city[city][index])
                added = True
        if not added:
            return order
        index += 1


def enrich(rooms: list[dict], texts: dict[str, str], extractor: FeeExtractor, cache: dict[str, dict],
           limit: int | None = None, max_tokens: int | None = None, on_call=None) -> tuple[list[dict], dict]:
    """Trả (review rows, stats); sửa `rooms` tại chỗ. `cache` theo room id, gồm cả lượt gọi mới.
    LLM chỉ điền chỗ còn null: phí thiếu, điều khoản/ngày trống chưa có, tiện ích chưa biết.
    Ngân sách (FC-05): dừng khi đủ `limit` lượt gọi mới hoặc số token của các lượt
    gọi mới chạm `max_tokens` (token của cache không tốn tiền, không tính); khi
    dừng sớm, stats["budget_exhausted"] = True và phần còn lại để lượt sau."""
    stats: dict = {"rooms_missing_fees": 0, "rooms_missing_terms_or_amenities": 0, "llm_calls": 0,
                   "cached": 0, "tokens": 0, "new_tokens": 0, "proposed": 0, "accepted": {},
                   "rejected": {}, "errors": 0, "budget_exhausted": False}
    review: list[dict] = []
    for room in rooms:
        text = texts.get(room["id"])
        if text is None:
            continue
        have = {fee["name"] for fee in room["quote"]["fees"]}
        missing = [name for name in REQUIRED_FEES if name not in have]
        quote = room["quote"]
        null_terms = [name for name in ("payment_cycle_months", "min_lease_months")
                      if quote.get(name) is None]
        null_amenities = [key for key in AMENITY_KEYS if (room.get("amenities") or {}).get(key) is None]
        need_date = room.get("available_from") is None
        if missing:
            stats["rooms_missing_fees"] += 1
        if null_terms or null_amenities or need_date:
            stats["rooms_missing_terms_or_amenities"] += 1
        if not (missing or null_terms or null_amenities or need_date):
            continue
        if room["id"] in cache:
            stats["cached"] += 1
        elif limit is not None and stats["llm_calls"] >= limit:
            stats["budget_exhausted"] = True
            break
        elif max_tokens is not None and stats["new_tokens"] >= max_tokens:
            stats["budget_exhausted"] = True
            break
        else:
            try:
                extraction, tokens = extractor.extract(text)
            except Exception:  # noqa: BLE001 - một tin lỗi không dừng cả lượt; ghi nhận rồi đi tiếp
                stats["errors"] += 1
                continue
            stats["llm_calls"] += 1
            stats["new_tokens"] += tokens or 0
            cache[room["id"]] = {"extractor_version": EXTRACTOR_VERSION,
                                 **extraction.model_dump(), "tokens": tokens}
            if on_call:
                on_call(room["id"], cache[room["id"]])
        entry = cache[room["id"]]
        stats["tokens"] += entry.get("tokens") or 0
        ad_id = room["id"].removeprefix("chotot-")

        def record(kind: str, key: str, reason: str | None, evidence: str, value) -> bool:
            stats["proposed"] += 1
            bucket = stats["rejected"] if reason else stats["accepted"]
            name = key if kind == "fee" else f"{kind}:{key}"
            bucket[reason or name] = bucket.get(reason or name, 0) + 1
            if reason:
                return False
            review.append({"room_id": room["id"], "kind": kind, "key": key, "value": value,
                           "evidence": evidence, "correct": ""})
            return True

        for raw in entry.get("fees") or []:
            candidate = FeeCandidate.model_validate(raw)
            if candidate.name not in missing:
                continue  # phí regex/API đã có thì không ghi đè
            if record("fee", candidate.name, verify(candidate, text), candidate.evidence,
                      candidate.amount_vnd or 0):
                missing.remove(candidate.name)
                room["quote"]["fees"].append({
                    "name": candidate.name, "amount_vnd": str(candidate.amount_vnd or 0), "mode": candidate.mode,
                    "included_in_rent": candidate.included_in_rent,
                    "source": f"chotot://ad/{ad_id}/body#{candidate.name}-llm"})
        for name in ("payment_cycle_months", "min_lease_months"):
            value = entry.get(name)
            evidence = entry.get(f"{name.replace('_months', '')}_evidence") or ""
            if value is None or quote.get(name) is not None:
                continue  # chỉ điền chỗ null, không ghi đè giá trị regex
            if record("term", name, verify_term(name, value, evidence, text), evidence, value):
                quote[name] = value
        if need_date:
            value = entry.get("available_from")
            evidence = entry.get("available_from_evidence") or ""
            if value is not None:
                posted_at = _posted_time(room)
                reason = verify_date(value, evidence, text, posted_at)
                if record("term", "available_from", reason, evidence, value):
                    room["available_from"] = parse_available_from(fold(evidence), posted_at)
        amenities = room.setdefault("amenities", {})
        for raw in entry.get("amenities") or []:
            candidate = AmenityCandidate.model_validate(raw)
            if candidate.key not in null_amenities:
                continue  # khóa đã có giá trị true/false thì không ghi đè
            if record("amenity", candidate.key, verify_amenity(candidate.key, candidate.value,
                                                               candidate.evidence, text),
                      candidate.evidence, candidate.value):
                amenities[candidate.key] = candidate.value
    return review, stats


def _posted_time(room: dict) -> datetime | None:
    value = room.get("posted_at")
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def full_fee_rooms(rooms: list[dict]) -> int:
    return sum(1 for room in rooms if set(REQUIRED_FEES) <= {fee["name"] for fee in room["quote"]["fees"]})


def run(source_dir: Path, target_dir: Path, snapshot_id: str, extractor: FeeExtractor,
        limit: int | None = None, max_tokens: int | None = None, log=print) -> dict:
    manifest = json.loads((source_dir / "manifest.json").read_text(encoding="utf-8"))
    catalog = json.loads((source_dir / "catalog.json").read_text(encoding="utf-8"))
    before = full_fee_rooms(catalog["rooms"])
    target_dir.mkdir(parents=True, exist_ok=True)
    cache_path = target_dir / "llm_cache.jsonl"
    cache: dict[str, dict] = {}
    if cache_path.exists():
        for line in cache_path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            room_id = entry.pop("room_id")
            # Cache của EXTRACTOR_VERSION cũ không còn hiệu lực; entry lạ thì bỏ.
            if entry.pop("extractor_version", None) == EXTRACTOR_VERSION:
                cache[room_id] = entry
    with cache_path.open("a", encoding="utf-8") as cache_file:
        def on_call(room_id: str, entry: dict) -> None:
            cache_file.write(json.dumps({"room_id": room_id, **entry}, ensure_ascii=False) + "\n")
            cache_file.flush()
            if len(cache) % 50 == 0:
                log(f"  llm calls cached={len(cache)}")
        # FC-05: hai thành phố xen kẽ, trong mỗi thành phố individual trước, mới
        # trước cũ — ngân sách dừng giữa chừng thì catalog vẫn cân bằng hai bên.
        review, stats = enrich(budget_order(catalog["rooms"]), post_texts(source_dir), extractor, cache,
                               limit, max_tokens, on_call)

    catalog["snapshot_id"] = snapshot_id
    raw_link = target_dir / "raw"
    if not raw_link.exists():
        raw_link.symlink_to((source_dir / "raw").resolve(), target_is_directory=True)
    catalog_path = target_dir / "catalog.json"
    catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (target_dir / "review.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["room_id", "kind", "key", "value", "evidence", "correct"])
        writer.writeheader()
        writer.writerows(review)
    after = full_fee_rooms(catalog["rooms"])
    summary = dict(manifest["summary"], with_all_required_fees=after)
    result = {"model": extractor.model, "extractor_version": EXTRACTOR_VERSION, "limit": limit,
              "max_tokens": max_tokens, "with_all_required_fees_before": before,
              "with_all_required_fees_after": after, **stats}
    manifest = {**manifest, "snapshot_id": snapshot_id, "summary": summary,
                "derived_from": {"snapshot_id": manifest["snapshot_id"], "catalog_sha256": manifest["catalog_sha256"],
                                 "change": "bổ sung phí/điều khoản/tiện ích bằng LLM, kiểm chứng tất định (data/llm_fees.py)"},
                "llm_fees": result,
                "catalog_sha256": hashlib.sha256(catalog_path.read_bytes()).hexdigest()}
    (target_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8")
    return {"snapshot": str(target_dir), **result}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from-snapshot", required=True, help="Snapshot nguồn trong --out-dir.")
    parser.add_argument("--snapshot-id", required=True, help="Snapshot mới (thư mục đã có thì dùng lại cache).")
    parser.add_argument("--out-dir", type=Path, default=ROOT / ".local" / "chotot")
    parser.add_argument("--limit", type=int, help="Tối đa số lượt gọi LLM mới, ví dụ 50 để chạy thử.")
    parser.add_argument("--max-calls", type=int, default=300, help="Ngân sách lượt gọi mới (FC-05, như CR-03).")
    parser.add_argument("--max-tokens", type=int, default=300_000,
                        help="Ngân sách token thật của các lượt gọi mới (đọc từ usage).")
    parser.add_argument("--model", help="Mặc định OPENAI_MODEL.")
    parser.add_argument("--allow-live", action="store_true", help="Bắt buộc: lượt chạy gọi API trả phí.")
    parser.add_argument("--yes", action="store_true",
                        help="Xác nhận gọi thật khi ước tính token đầu vào vượt 1 triệu (FC-05).")
    arguments = parser.parse_args()
    if not arguments.allow_live:
        parser.error("Gọi LLM tốn tiền; thêm --allow-live (nên thử --limit 50 trước).")
    if not os.getenv("OPENAI_API_KEY"):
        parser.error("Thiếu OPENAI_API_KEY.")
    source_dir = arguments.out_dir / arguments.from_snapshot
    texts = post_texts(source_dir)
    estimate = input_token_estimate(texts)
    if not live_call_allowed(estimate, arguments.yes):
        parser.error(f"Ước tính ~{estimate:,} token đầu vào (>1 triệu); thêm --yes nếu chắc chắn gọi thật.")
    extractor = OpenAIFeeExtractor(arguments.model)
    result = run(source_dir, arguments.out_dir / arguments.snapshot_id, arguments.snapshot_id,
                 extractor, arguments.limit or arguments.max_calls, arguments.max_tokens, log=print)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
