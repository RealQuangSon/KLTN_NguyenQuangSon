// Bốn vai trò đích theo contract v1 (docs/api-san-pham-v1.md). Máy chủ hiện tại
// 0.3.0 chỉ cấp renter/manager; owner/admin phải do server cấp, client không tự gán.
export type Role = "renter" | "owner" | "manager" | "admin";
export const roleNames: Record<Role, string> = {
  renter: "Người thuê",
  owner: "Chủ nhà",
  manager: "Nhân viên (cũ)",
  admin: "Quản trị viên",
};
// Statuses where approved rooms are visible to the renter (some or all landlords approved).
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
  max_monthly_cost_vnd: number;
  max_rent_vnd?: number | null;
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
  area_m2: number;
  room_type?: RoomType;
  bedrooms?: number | null;
  landlord_id?: string | null;
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
}
export interface Results {
  session_id: string;
  run_id?: string;
  status: string;
  profile_version?: number;
  results: Candidate[];
  suggestions?: string[];
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
export interface ListingContact {
  kind: "external" | "landlord";
  original_url: string | null;
  phone: string | null;
  phone_requires_login: boolean;
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
  area_m2: number;
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
  // FE-05/FE-06: chỉ có ở chi tiết tin (/landlord/rooms/{id}); danh sách có
  // thể không kèm. photos trống nghĩa là tin chưa có ảnh thật.
  photos?: Photo[];
  promotion?: Promotion | null;
  contact?: ListingContact;
}
export interface Viewing {
  id: string;
  session_id: string | null;
  run_id: string | null;
  room_id: string;
  requested_at: string;
  status: "requested" | "confirmed" | "declined";
  landlord_id?: string | null;
  mode?: "offline" | "online";
  meeting_url?: string | null;
}
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
  furniture: "Nội thất cơ bản",
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
    return `Phí theo giả định chuẩn: ${names.join(", ")} — xác minh lại khi xem`;
  }
  if (code === "capacity_unknown") {
    return "Sức chứa chưa ghi trong tin — coi như vừa số người bạn nêu, xác minh khi xem";
  }
  if (code.startsWith("location_uncertainty_")) {
    return `Sai số vị trí ${code.slice("location_uncertainty_".length)}`;
  }
  return verificationLabels[code] || code;
};
export const fees: Record<string, string> = {
  rent: "Tiền thuê",
  electricity: "Điện",
  water: "Nước",
  internet: "Internet",
  parking: "Giữ xe",
  service: "Dịch vụ",
  deposit: "Tiền cọc",
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
};
