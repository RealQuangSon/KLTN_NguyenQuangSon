"""Tenant handbook: platform FAQ plus each landlord's own house rules.

Answers are retrieved, never generated: keyword overlap on diacritic-free text
picks platform entries, and a room's `house_rules` sentences are matched the
same way. Legal topics are general reference, not legal advice; the entries say
so and point the renter to the current legal text or the landlord.
"""
from __future__ import annotations

import re

from .locations import fold

DISCLAIMER = ("Thông tin tham khảo chung, không phải tư vấn pháp lý. Hãy đối chiếu văn bản pháp luật hiện hành "
              "và hợp đồng cụ thể với chủ nhà.")

ENTRIES = [
    {"id": "deposit", "title": "Tiền cọc và hoàn cọc",
     "tags": ["coc", "hoan coc", "lay lai coc", "dat coc", "mat coc", "tra coc"],
     "answer": "Tiền cọc là khoản bảo đảm thực hiện hợp đồng. Hợp đồng nên ghi rõ số tiền, thời hạn hoàn, "
               "các trường hợp được trừ cọc (hư hỏng, nợ phí) và cách xác nhận khi bàn giao. Khi trả phòng, "
               "hai bên đối chiếu biên bản bàn giao rồi hoàn phần cọc còn lại. HomeMatch không giữ tiền cọc."},
    {"id": "contract", "title": "Hợp đồng thuê nên có gì",
     "tags": ["hop dong", "ky hop dong", "thoi han", "gia han", "cham dut", "thanh ly"],
     "answer": "Hợp đồng nên ghi: thông tin hai bên, địa chỉ phòng, thời hạn, giá thuê và kỳ thanh toán, các khoản "
               "phí và cách tính, tiền cọc, quyền và nghĩa vụ, điều kiện gia hạn, chấm dứt sớm và bàn giao. "
               "Đọc kỹ điều khoản phạt khi chấm dứt trước hạn."},
    {"id": "residence", "title": "Đăng ký tạm trú",
     "tags": ["tam tru", "dang ky tam tru", "cu tru", "giay to", "cong an"],
     "answer": "Người thuê ở lâu dài tại nơi khác nơi thường trú thường phải đăng ký tạm trú theo pháp luật về cư trú. "
               "Chủ nhà thường cung cấp giấy tờ chỗ ở hợp pháp (ví dụ hợp đồng thuê) để bạn làm thủ tục. "
               "Hỏi chủ nhà trước khi ký để chuẩn bị giấy tờ."},
    {"id": "utilities", "title": "Cách tính điện, nước",
     "tags": ["tien dien", "tien nuoc", "dien", "nuoc", "cong to", "chot so", "kwh", "khoi"],
     "answer": "Điện thường tính theo công tơ riêng (đơn giá × số kWh) hoặc khoán; nước tính theo người hoặc theo m³. "
               "Hãy hỏi đơn giá, ngày chốt số và cách xác nhận chỉ số. Trên HomeMatch, khoản chưa có đơn giá được "
               "đánh dấu \"chưa rõ\" chứ không tính là 0."},
    {"id": "costs", "title": "Tổng chi phí tháng và tiền vào ở",
     "tags": ["tong thang", "chi phi", "tien vao o", "phi dich vu", "tra truoc", "ngan sach"],
     "answer": "Tổng tháng = tiền thuê + điện, nước, internet, gửi xe, dịch vụ theo kịch bản của bạn. Tiền vào ở = cọc "
               "+ tiền thuê trả trước + phí một lần + chuyển nhà + sắm sửa (không cộng lại tháng đầu). Khi thiếu tiền "
               "vào ở, bạn có thể mô phỏng khoản vay ngắn hạn; đó chỉ là ước tính."},
    {"id": "privacy", "title": "Quyền riêng tư của người thuê",
     "tags": ["thu nhap", "rieng tu", "du lieu", "bao mat", "xoa du lieu", "ghi nho"],
     "answer": "Thu nhập bạn nhập chỉ dùng tính tỷ lệ chi phí; chủ nhà chỉ thấy mức đánh giá, không thấy con số. "
               "Bạn có thể bật hoặc tắt ghi nhớ sở thích và xóa dữ liệu ghi nhớ trong mục Tài khoản. "
               "Nội dung chat được lưu có che số điện thoại, email và giới hạn thời gian lưu."},
    {"id": "review", "title": "Vì sao danh sách gợi ý cần chủ nhà duyệt",
     "tags": ["duyet", "cho duyet", "goi y", "chu nha duyet", "danh sach"],
     "answer": "Trợ lý chỉ đề xuất; mỗi chủ nhà kiểm tra phòng của mình (còn trống, đúng giá) trước khi bạn thấy. "
               "Phòng hiện dần khi từng chủ nhà duyệt. Khi bạn đổi nhu cầu, danh sách cũ hết hiệu lực."},
    {"id": "viewing", "title": "Đặt và hủy lịch xem phòng",
     "tags": ["lich xem", "xem phong", "xem truc tuyen", "online", "huy lich", "dat lich"],
     "answer": "Bạn chọn xem trực tiếp hoặc trực tuyến. Yêu cầu chỉ thành lịch hẹn khi chủ nhà xác nhận; lịch trực "
               "tuyến có link phòng họp. Lịch xem không giữ chỗ phòng."},
    {"id": "platform", "title": "Điều khoản chung của HomeMatch",
     "tags": ["dieu khoan", "nen tang", "trach nhiem", "thanh toan", "khieu nai", "bao cao tin"],
     "answer": "HomeMatch hỗ trợ tìm phòng, ước tính chi phí và kết nối với chủ nhà; không nhận thanh toán thay và "
               "không bảo đảm tình trạng phòng thay chủ nhà. Hóa đơn, biên lai do chủ nhà phát hành trên hệ thống. "
               "Gặp tin sai hoặc ứng xử không phù hợp, hãy báo cho quản trị viên."},
    {"id": "rights", "title": "Quyền lợi cơ bản của người thuê",
     "tags": ["quyen loi", "quyen", "nghia vu", "sua chua", "hong hoc", "bao hong"],
     "answer": "Người thuê có quyền được ở đúng phòng, đúng giá đã thỏa thuận, được sửa chữa hư hỏng không do mình gây ra "
               "theo hợp đồng, và được báo trước khi thay đổi giá hay chấm dứt. Báo hỏng qua mục Sửa chữa để có "
               "lịch sử xử lý."},
]
RULE_TOPICS = {
    "gio giac": ["gio", "cong", "khoa", "ve muon", "23", "22"],
    "gui xe": ["xe", "ham", "gui xe"],
    "dien nuoc": ["dien", "nuoc", "cong to", "chot so", "m³", "kwh"],
    "thu cung": ["thu cung", "cho", "meo"],
    "khach": ["khach", "qua dem"],
    "hut thuoc": ["thuoc"],
}


def _score(question: str, entry: dict) -> int:
    text = fold(question)
    score = sum(3 for tag in entry["tags"] if tag in text)
    score += sum(1 for word in fold(entry["title"]).split() if len(word) > 2 and re.search(rf"\b{word}\b", text))
    return score


def room_rules(question: str, rules: str | None) -> list[str]:
    """Sentences of the landlord's house rules that match the question's topic."""
    if not rules:
        return []
    text = fold(question)
    keywords = {word for topic, words in RULE_TOPICS.items() if topic in text or any(w in text for w in words)
                for word in words}
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", rules) if part.strip()]
    if not keywords or any(word in text for word in ("noi quy", "quy dinh")):
        return sentences
    return [sentence for sentence in sentences if any(word in fold(sentence) for word in keywords)]


def answer(question: str, rules: str | None = None) -> dict:
    ranked = sorted(((entry, _score(question, entry)) for entry in ENTRIES), key=lambda pair: -pair[1])
    hits = [{"id": entry["id"], "title": entry["title"], "answer": entry["answer"]}
            for entry, score in ranked if score > 0][:3]
    house = room_rules(question, rules)
    return {"answers": hits, "house_rules": house, "disclaimer": DISCLAIMER,
            "found": bool(hits or house)}


def entries() -> list[dict]:
    return [{"id": entry["id"], "title": entry["title"], "answer": entry["answer"]} for entry in ENTRIES]
