// Bốn vai trò đích theo contract v1 (docs/api-san-pham-v1.md). Máy chủ hiện tại
// 0.3.0 chỉ cấp renter/manager; owner/admin phải do server cấp, client không tự gán.
export type Role = "renter" | "owner" | "manager" | "admin";
export const roleNames: Record<Role, string> = {
  renter: "Người thuê",
  owner: "Chủ nhà",
  manager: "Nhân viên (cũ)",
  admin: "Quản trị viên",
};
// Statuses where recommended rooms are visible to the renter.
export const visibleStatuses = ["published"];
export interface Actor {
  id: string;
  role: Role;
  // FE-02: chỉ vai trò owner mang trạng thái duyệt chủ nhà; vai trò khác là null.
  landlord_status?: LandlordStatus | null;
}
// Trạng thái duyệt của tài khoản chủ nhà (README §7.1): hồ sơ mới là "pending",
// quản trị viên duyệt thành "approved" hoặc từ chối với lý do thành "rejected".
export type LandlordStatus = "pending" | "approved" | "rejected";
export const landlordPendingNote =
  "Tài khoản đang chờ quản trị viên duyệt — bạn có thể soạn tin nhưng chưa công khai được.";
// Hồ sơ chủ nhà chờ duyệt mà admin thấy ở /quan-tri/tai-khoan (README §7.1).
export interface LandlordApplication {
  user_id: string;
  email: string;
  display_name: string | null;
  landlord_status: LandlordStatus;
  created_at: string;
  verified: boolean;
}
// Ticket hỗ trợ (README §7.2): khách yêu cầu gặp người thật từ hội thoại AI.
export type TicketStatus = "requested" | "in_progress" | "resolved";
export const ticketStatusLabels: Record<TicketStatus, string> = {
  requested: "Chờ xử lý",
  in_progress: "Đang xử lý",
  resolved: "Đã giải quyết",
};
export interface SupportTicket {
  id: string;
  session_id: string;
  status: TicketStatus;
  assignee: string | null;
  note: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
}
// Chi phí AI quy ra VND (README §7.3): khoản chưa biết là null, không bao giờ 0.
export interface CostMetrics {
  estimated_cost_vnd: number | null;
  price_effective_date: string | null;
  missing: string[];
  basis: Record<string, unknown>;
}
export interface LoginResult {
  access_token: string;
  token_type: string;
  expires_at: string;
  actor: Actor;
}
export interface Scenario {
  people: number;
  vehicles: number;
  electricity_kwh: number | string;
  water_m3: number | string;
  moving_vnd: number;
  setup_vnd: number;
}
export interface Destination {
  label: string;
  latitude: number;
  longitude: number;
  uncertainty_m: number;
  max_distance_m: number;
}
export type RoomType = "room" | "studio" | "apartment";
export const roomTypeLabels: Record<RoomType, string> = {
  room: "Phòng trọ",
  studio: "Studio",
  apartment: "Căn hộ",
};
export interface LoanTerms {
  annual_rate: number | string;
  term_months: number;
  max_principal_vnd?: number | null;
}
export interface Profile {
  city: string;
  area: string | null;
  room_type: RoomType;
  min_bedrooms?: number | null;
  // UX-01: khách chỉ nêu tiền thuê thì trần tổng tháng trống (null).
  max_monthly_cost_vnd: number | null;
  max_rent_vnd?: number | null;
  min_rent_vnd?: number | null;
  min_area_m2?: number | null;
  min_area_hard?: boolean;
  prefer_cheapest?: boolean;
  budget_approx?: boolean;
  max_initial_cash_vnd: number | null;
  monthly_income_vnd?: number | null;
  cost_split?: "none" | "equal";
  loan?: LoanTerms | null;
  must_amenities: string[];
  preferences: string[];
  accept_estimated_data?: boolean;
  scenario: Scenario;
  destination: Destination | null;
  soft_description?: string | null;
}
export type FieldStatus = "unknown" | "inferred" | "confirmed";
export interface Draft {
  city: string | null;
  area: string | null;
  people: number | null;
  preferences: string[];
  budget_hint_vnd: number | null;
  budget_scope?: "rent" | "total" | null;
  budget_min_vnd?: number | null;
  min_area_m2?: number | null;
  min_area_hard?: boolean;
  prefer_cheapest?: boolean;
  budget_approx?: boolean;
  destination?: Destination | null;
  needs_destination: boolean;
  accept_estimated_data?: boolean;
  room_type?: RoomType | null;
  bedrooms?: number | null;
  soft_description?: string | null;
  field_status?: Record<string, FieldStatus>;
  evidence_ref?: Record<string, string>;
}
export interface Session {
  session_id: string;
  draft_revision: number;
  draft: Draft;
  profile_version: number;
  confirmed_profile: Profile | null;
  active_run_id: string | null;
  questions?: string[];
  status?: string;
  message?: string;
  // FE-07: phần mở rộng của MessageResult cho intent simulate_finance; các
  // giá trị status "simulation" | "needs_results" đi qua trường status chung.
  intent?: string;
  simulation?: ChatSimulation | null;
  interpreter_mode?: string;
  answers?: { id: string; title: string; answer: string }[];
  house_rules?: string[];
  disclaimer?: string;
}
export interface CostLine {
  name: string;
  period: "monthly" | "initial";
  amount_vnd: number | null;
  source: string;
  included_in_rent: boolean;
}
export interface Cost {
  monthly_known_vnd: number;
  monthly_total_vnd: number | null;
  initial_known_vnd: number;
  initial_total_vnd: number | null;
  missing_monthly: string[];
  missing_initial: string[];
  lines: CostLine[];
  assumptions: Record<string, unknown>;
  affordability?: Affordability | null;
}
export type AffordabilityBand = "phu_hop" | "can_nhac" | "vuot" | "chua_ro";
export interface LoanEstimate {
  principal_vnd: number;
  installment_vnd: number;
  total_interest_vnd: number;
  term_months: number;
  annual_rate: string;
  exceeds_max_principal: boolean;
}
export interface Affordability {
  shortfall_vnd: number | null;
  loan: LoanEstimate | null;
  burden_vnd: number | null;
  renter_burden_vnd: number | null;
  // Null for the sale/manager projection so income cannot be inferred.
  housing_ratio: string | null;
  band: AffordabilityBand;
  thresholds: Record<string, string>;
}
export const bandLabels: Record<AffordabilityBand, string> = {
  phu_hop: "Trong mức khuyến nghị",
  can_nhac: "Cần cân nhắc",
  vuot: "Vượt mức khuyến nghị",
  chua_ro: "Chưa đủ dữ liệu thu nhập",
};
// Thẻ mô phỏng vay trong chat (README §7.4, AG-02 ↔ FE-07). `result` giống một
// phần tử của POST /sessions/{id}/simulate (một kịch bản {label, cost}); mọi
// con số do máy chủ tính, giao diện chỉ hiển thị.
export interface ChatSimulation {
  room_id: string;
  room_title: string;
  scenario: {
    // Đơn vị phần trăm/năm theo hợp đồng (10 = 10%/năm); null khi không parse được.
    annual_rate: number | string | null;
    term_months: number;
    principal_vnd: number | null;
  };
  result: { label: string; cost: Cost };
}
export interface LocationCity {
  name: string;
  aliases: string[];
  areas: { name: string; aliases: string[] }[];
}
export interface Candidate {
  room_id: string;
  room_revision: number;
  title: string;
  city: string;
  area: string;
  room_type?: RoomType;
  bedrooms?: number | null;
  landlord_id?: string | null;
  // Tin cào có thể không rõ diện tích: null, không bao giờ 0 hay số giả.
  area_m2: number | null;
  cost: Cost;
  score: number;
  components: Record<string, number>;
  reasons: string[];
  tradeoffs: string[];
  source: string;
  synthetic: boolean;
  algorithm: string;
  verification?: string[];
  // Public projection of the listing coordinates (approximate at most).
  latitude?: number | null;
  longitude?: number | null;
  location_accuracy?: "exact" | "approximate" | "area_only";
  uncertainty_m?: number | null;
  // CA-05: URL ảnh CDN Chợ Tốt gắn theo room_id lúc trả response (không nằm
  // trong payload run đã xếp hạng); chỉ để hiển thị.
  source_images?: string[];
}
export interface Results {
  session_id: string;
  run_id?: string;
  status: string;
  profile_version?: number;
  results: Candidate[];
  // D-12: run giữ top 5; tổng số căn khớp, số căn đủ dữ liệu chi phí / ước tính và
  // đường dẫn tìm theo bộ lọc cùng điều kiện (null với run lịch sử).
  total_matches?: number | null;
  exact_cost_matches?: number | null;
  estimated_matches?: number | null;
  search_path?: string | null;
  suggestions?: string[];
  // Câu trả lời gợi ý cho khung chat, máy chủ chọn theo trạng thái phiên.
  suggested_prompts?: string[];
  // Tổng hợp lọc cứng cho ca kho rỗng (chỉ số liệu, không có danh tính phòng).
  diagnostics_summary?: {
    scanned: number;
    kept: number;
    rejected?: Record<string, number>;
    verification?: Record<string, number>;
  };
  // Các bước pipeline deterministic đã chạy thật của run.
  steps?: string[];
}
export interface Fee {
  name: string;
  amount_vnd: number | string | null;
  mode: string;
  included_in_rent: boolean;
  source: string;
}
export type Occupancy = "vacant" | "deposited" | "rented";
export const occupancyLabels: Record<Occupancy, string> = {
  vacant: "Còn trống",
  deposited: "Đã cọc",
  rented: "Đã thuê",
};
export interface Quote {
  rent_vnd: number;
  deposit_vnd: number | null;
  advance_months?: number | null;
  // LF-05: kỳ thanh toán và thời hạn hợp đồng tối thiểu theo tin; chưa rõ là null.
  payment_cycle_months?: number | null;
  min_lease_months?: number | null;
  one_time_vnd?: number | null;
  fees: Fee[];
}
// Ảnh media (README §7.5): máy chủ trả {id, url}; url là đường dẫn gốc
// "/media/{id}", giao diện ghép tiền tố API khi hiển thị.
export interface Photo {
  id: string;
  url: string;
}
// Ưu đãi của chủ nhà (README §7.6): chỉ hiện khi còn hạn (máy chủ quyết định);
// ưu đãi không đổi giá hiển thị và không ngụ ý thứ tự xếp hạng.
export interface Promotion {
  text: string;
  valid_until: string;
}
// Chỉ có ở chi tiết tin (/listings/{id}). external: tin cào, liên hệ ở tin gốc;
// landlord: SĐT chủ nhà tự khai, máy chủ chỉ trả khi đã đăng nhập.
// CA-04/C1b: poster_name (tên người đăng trên tin gốc) chỉ có với tin cào và
// chỉ trả khi đã đăng nhập; khách ẩn danh nhận null.
export interface ListingContact {
  kind: "external" | "landlord";
  original_url: string | null;
  phone: string | null;
  phone_requires_login: boolean;
  poster_name?: string | null;
}
export interface Room {
  id: string;
  revision: number;
  title: string;
  city: string;
  area: string;
  room_type?: RoomType;
  bedrooms?: number | null;
  capacity?: number | null;
  published: boolean;
  available: boolean | null;
  occupancy?: Occupancy | null;
  area_m2: number | null;
  source: string;
  synthetic: boolean;
  amenities: Record<string, boolean | null>;
  quote: Quote;
  latitude?: number | null;
  longitude?: number | null;
  location_accuracy?: "exact" | "approximate" | "area_only";
  uncertainty_m?: number | null;
  features_text?: string | null;
  house_rules?: string | null;
  landlord_id?: string | null;
  // LF-05: trường tin đăng mới (crawler 2.2). Chỗ nào tin không ghi thì null —
  // không bao giờ 0/false; description là bản đã che SĐT/email ở máy chủ.
  description?: string | null;
  posted_at?: string | null;
  poster_kind?: "broker" | "individual" | null;
  ward?: string | null;
  ward_2025?: string | null;
  street?: string | null;
  available_from?: string | null;
  // CA-04/crawl.md B-2,C-1: ảnh, video Cloudflare Stream, nhà vệ sinh, tên dự
  // án, tầng, hướng, loại hình theo tin gốc; tin không ghi thì null/rỗng —
  // poster_name KHÔNG bao giờ có ở đây (chỉ trả qua contact khi đã đăng nhập).
  source_images?: string[];
  source_videos?: { url: string; thumbnail: string | null }[];
  toilets?: number | null;
  project_name?: string | null;
  floor?: string | null;
  direction?: string | null;
  balcony_direction?: string | null;
  property_subtype?: string | null;
  // crawl.md E-04/E-06: kiểm chứng tin + chỗ ở tương tự (chỉ ở /listings/{id}).
  trust?: TrustPayload | null;
  similar_rooms?: SimilarRoom[];
  photos?: Photo[];
  // FE-05/FE-06: chỉ có ở chi tiết tin (/landlord/rooms/{id}); danh sách có
  // thể không kèm. photos trống nghĩa là tin chưa có ảnh thật.
  promotion?: Promotion | null;
  contact?: ListingContact;
}
export interface TrustCheck {
  status: "ok" | "warn" | "unknown";
  detail: string;
}
export interface TrustPayload extends Record<string, unknown> {
  completeness?: TrustCheck;
  price_vs_area?: TrustCheck;
  duplicate?: TrustCheck;
  image_reuse?: TrustCheck;
  prepay_request?: TrustCheck;
  title_consistency?: TrustCheck;
  freshness?: TrustCheck;
  reports?: TrustCheck;
  ownership?: TrustCheck;
  price_per_m2?: number | null;
  group_median_per_m2?: number | null;
  position?: "ok" | "high" | "low" | null;
  notice?: string;
}
export interface SimilarRoom {
  id: string;
  title: string;
  area: string;
  city: string;
  rent_vnd: number;
  area_m2: number | null;
  source: string;
}
export const trustLabels: Record<string, string> = {
  completeness: "Đủ thông tin",
  price_vs_area: "Giá so với khu",
  duplicate: "Trùng tin",
  image_reuse: "Ảnh trùng",
  prepay_request: "Yêu cầu cọc trước",
  title_consistency: "Tiêu đề nhất quán",
  freshness: "Độ mới của tin",
  reports: "Báo cáo từ người dùng",
  ownership: "Quyền sở hữu",
};
export interface Viewing {
  id: string;
  session_id: string | null;
  run_id: string | null;
  room_id: string;
  requested_at: string;
  // crawl.md E-01: vòng đời mở rộng.
  status:
    | "requested"
    | "confirmed"
    | "declined"
    | "cancelled"
    | "reschedule_proposed"
    | "completed"
    | "no_show";
  landlord_id?: string | null;
  mode?: "offline" | "online";
  meeting_url?: string | null;
  handler?: "landlord" | "concierge" | null;
  time_slot?: "morning" | "afternoon" | "evening" | null;
  note?: string | null;
  proposed_at?: string | null;
  feedback_rating?: number | null;
  feedback_note?: string | null;
  lease_id?: string | null;
  lease_status?: string | null;
  lease_visible?: boolean | null;
  created_at?: string | null;
  updated_at?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_shared?: boolean;
}
export const timeSlotLabels: Record<string, string> = {
  morning: "Sáng (8:00–12:00)",
  afternoon: "Chiều (12:00–17:00)",
  evening: "Tối (17:00–20:00)",
};
export const viewingStatusLabels: Record<string, string> = {
  requested: "Chờ xác nhận",
  confirmed: "Đã xác nhận",
  declined: "Không nhận lịch",
  cancelled: "Đã hủy",
  reschedule_proposed: "Có đề xuất giờ mới",
  completed: "Đã xem xong",
  no_show: "Không diễn ra",
};
export interface DraftPatch {
  expected_draft_revision: number;
  set: Partial<
    Pick<
      Draft,
      | "city"
      | "area"
      | "people"
      | "preferences"
      | "needs_destination"
      | "room_type"
      | "bedrooms"
      | "soft_description"
    >
  >;
  clear_fields: string[];
  remove_preferences: string[];
}
export const amenities: Record<string, string> = {
  window: "Cửa sổ, thoáng sáng",
  quiet: "Yên tĩnh",
  private_bathroom: "WC riêng",
  parking: "Chỗ để xe",
  air_conditioning: "Máy lạnh",
  washing_machine: "Máy giặt",
  balcony: "Ban công",
  // AMENITY_KEYS chỉ có một khóa nội thất; tin ghi "nội thất đầy đủ" cũng map
  // vào khóa này nên nhãn trung tính, không nói sai nội dung tin (crawl.md C-2).
  furniture: "Có nội thất",
  pets_allowed: "Nuôi thú cưng",
  // LF-05: 10 tiện ích mới — nhãn phải khớp AMENITY_KEYS của backend (test đồng bộ).
  kitchen: "Bếp",
  wifi: "Wifi",
  elevator: "Thang máy",
  security_24h: "An ninh 24/7",
  camera: "Camera",
  loft: "Gác lửng",
  flexible_hours: "Giờ giấc tự do",
  no_shared_landlord: "Không chung chủ",
  water_heater: "Nóng lạnh",
  fridge: "Tủ lạnh",
};
// LF-05: người đăng tin — chỉ hiện nhãn khi máy chủ trả giá trị; null thì
// không hiện gì, không suy ra "Chính chủ".
export const posterLabels: Record<"broker" | "individual", string> = {
  broker: "Môi giới",
  individual: "Chính chủ",
};
// Địa chỉ chi tiết theo mẫu plan: "Đường Hồ Văn Huê, Phường 9 (nay là Phường
// Đức Nhuận), Quận Phú Nhuận" — thành phố hiển thị riêng, thiếu phần thì bỏ.
export const addressLine = (
  room: Pick<Room, "street" | "ward" | "ward_2025" | "area">,
): string => {
  const ward =
    room.ward && room.ward_2025
      ? `${room.ward} (nay là ${room.ward_2025})`
      : room.ward || room.ward_2025 || "";
  return [room.street, ward, room.area]
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .join(", ");
};
// "Đăng 2 ngày trước"; chưa có ngày đăng (hoặc không đọc được) thì null.
export const postedAgoLabel = (
  postedAt: string | null | undefined,
  now: number = Date.now(),
): string | null => {
  if (!postedAt) return null;
  const moment = Date.parse(postedAt);
  if (Number.isNaN(moment)) return null;
  const days = Math.floor((now - moment) / 86_400_000);
  return days <= 0 ? "Đăng hôm nay" : `Đăng ${days} ngày trước`;
};
export const verificationLabels: Record<string, string> = {
  location_approximate: "Vị trí gần đúng",
  location_area_only: "Chỉ biết tới khu vực",
  // UX-04: nhãn đọc từ tiêu đề/mô tả tin, không suy đoán về người thuê.
  shared_listing: "Tin ghi ở ghép",
  roommate_wanted: "Tin ghi tìm bạn ở ghép",
  gender_female_only: "Tin ghi: chỉ cho nữ thuê",
  gender_male_only: "Tin ghi: chỉ cho nam thuê",
  area_unknown: "Chưa rõ diện tích",
};
export const verificationText = (code: string): string => {
  if (code.startsWith("amenity_unknown:")) {
    const name = code.slice("amenity_unknown:".length);
    return `Tiện ích chưa rõ: ${amenities[name] || name}`;
  }
  if (code.startsWith("fee_rate_unknown:")) {
    const name = code.slice("fee_rate_unknown:".length);
    return `Đơn giá chưa rõ: ${fees[name] || name}`;
  }
  if (code.startsWith("fee_assumed:")) {
    const names = code
      .slice("fee_assumed:".length)
      .split(",")
      .map((n) => fees[n.trim()] || n.trim());
    return `Phí tạm tính vì tin không ghi: ${names.join(", ").toLowerCase()} — xác minh lại khi xem`;
  }
  if (code === "capacity_unknown") {
    return "Sức chứa: chưa rõ (tin không ghi) — xác minh khi xem";
  }
  if (code.startsWith("location_uncertainty_")) {
    return `Sai số vị trí ${code.slice("location_uncertainty_".length)}`;
  }
  return verificationLabels[code] || code;
};
// UX-08: gộp các tiện ích "chưa rõ" thành một dòng thay vì liệt kê từng cái.
export const verificationSummary = (codes: string[]): string[] => {
  const unknownAmenities = codes.filter((c) =>
    c.startsWith("amenity_unknown:"),
  );
  const rest = codes
    .filter((c) => !c.startsWith("amenity_unknown:"))
    .map(verificationText);
  return unknownAmenities.length
    ? [...rest, `Tin chưa ghi ${unknownAmenities.length} tiện ích`]
    : rest;
};
export const fees: Record<string, string> = {
  rent: "Tiền thuê",
  electricity: "Điện",
  water: "Nước",
  internet: "Internet",
  parking: "Giữ xe",
  service: "Dịch vụ",
  deposit: "Tiền cọc",
  first_rent: "Tiền thuê trả trước",
  advance_rent: "Thuê trả trước",
  one_time: "Phí một lần",
  moving: "Chuyển nhà",
  setup: "Sắm sửa ban đầu",
};
export const statusLabels: Record<string, string> = {
  awaiting_confirmation: "Chờ xác nhận nhu cầu",
  needs_clarification: "Cần làm rõ nhu cầu",
  generating: "Đang tìm phòng",
  published: "Đã xếp hạng",
  invalidated: "Gợi ý đã hết hiệu lực",
  no_match: "Chưa có phòng đáp ứng",
  needs_verification: "Cần xác minh thông tin",
  generation_failed: "Tạo gợi ý chưa thành công",
  ai_unavailable: "Trợ lý tạm thời không khả dụng",
  requested: "Chờ xác nhận lịch",
  confirmed: "Lịch đã xác nhận",
  declined: "Lịch chưa được chấp nhận",
  cancelled: "Lịch đã hủy",
  reschedule_proposed: "Có đề xuất giờ mới",
  completed: "Đã xem xong",
  no_show: "Không diễn ra",
};
