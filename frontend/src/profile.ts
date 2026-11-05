import type { Draft, Profile } from "./types";
// Dựng hồ sơ xác nhận từ nháp của trợ lý (kiểu tham chiếu: không có form chặn
// luồng — chat xong là tìm ngay theo những gì trợ lý hiểu, giá trị kịch bản
// dùng bộ mặc định giống ProfileForm). Chưa đủ dữ liệu tối thiểu (thành phố +
// ngân sách) thì trả null — trợ lý sẽ hỏi thêm trong hội thoại.
export function profileFromDraft(draft: Draft | null): Profile | null {
  if (!draft?.city || draft.budget_hint_vnd == null) return null;
  return {
    city: draft.city,
    area: draft.area ?? null,
    room_type: draft.room_type ?? "room",
    min_bedrooms: null,
    max_monthly_cost_vnd: draft.budget_hint_vnd,
    max_initial_cash_vnd: null,
    monthly_income_vnd: null,
    cost_split: "none",
    loan: null,
    must_amenities: [],
    preferences: draft.preferences ?? [],
    accept_estimated_data: draft.accept_estimated_data ?? false,
    soft_description: draft.soft_description ?? null,
    scenario: {
      people: draft.people ?? 1,
      vehicles: 1,
      electricity_kwh: "140",
      water_m3: "3",
      moving_vnd: 300000,
      setup_vnd: 200000,
    },
    // AG-01: điểm đến do trợ lý suy ra từ chat (places.json) hoặc nhập form.
    destination: draft.destination ?? null,
  };
}
// Sau lần xác nhận đầu, lượt chat đổi nhu cầu (vd. "chấp nhận dữ liệu ước
// tính", đổi quận) cũng phải chạy vòng tìm mới — nếu không trợ lý báo "kết quả
// sẽ tự hiện" mà khung phải vẫn giữ run cũ. Chỉ áp trường mà lượt chat vừa đổi
// (evidence "chat:") lên hồ sơ đã xác nhận, nên giá trị nhập ở form (điểm đến,
// vay, tiền vào ở…) được giữ. Ngân sách KHÔNG tự áp: tiền nhắc trong chat chỉ
// là gợi ý ("nới thêm 1 triệu" đọc ra mức 1 triệu), người thuê nâng trần qua
// "Nhu cầu của tôi". Không có gì đổi thì trả null.
export function profileUpdateFromChat(
  confirmed: Profile,
  before: Draft,
  after: Draft,
): Profile | null {
  const changed = (key: keyof Draft) =>
    Boolean(after.evidence_ref?.[key]?.startsWith("chat:")) &&
    JSON.stringify(before[key]) !== JSON.stringify(after[key]);
  const next: Profile = { ...confirmed, scenario: { ...confirmed.scenario } };
  if (changed("city") && after.city) next.city = after.city;
  if (changed("area")) next.area = after.area ?? null;
  if (changed("room_type") && after.room_type) next.room_type = after.room_type;
  if (next.room_type !== "apartment") {
    if (next.min_bedrooms != null) next.min_bedrooms = null;
  } else if (changed("bedrooms")) next.min_bedrooms = after.bedrooms ?? null;
  if (changed("people") && after.people != null)
    next.scenario.people = after.people;
  if (changed("preferences"))
    next.preferences = (after.preferences ?? []).filter(
      (id) => !next.must_amenities.includes(id),
    );
  if (changed("accept_estimated_data") && after.accept_estimated_data)
    next.accept_estimated_data = true;
  if (changed("destination")) next.destination = after.destination ?? null;
  if (changed("soft_description"))
    next.soft_description = after.soft_description ?? null;
  return JSON.stringify(next) === JSON.stringify(confirmed) ? null : next;
}
