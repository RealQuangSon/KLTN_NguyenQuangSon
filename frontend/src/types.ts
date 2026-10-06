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
export const visibleStatuses = ["published", "partially_published"];
export interface Actor {
  id: string;
  role: Role;
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
}
export interface Results {
  session_id: string;
  run_id?: string;
  status: string;
  profile_version?: number;
  results: Candidate[];
  suggestions?: string[];
}
export interface Recommendation {
  run_id: string;
  session_id: string;
  status: string;
  profile_version: number;
  catalog_version: string;
  profile: Profile;
  items: Candidate[];
  diagnostics: {
    rejected?: Record<string, number>;
    verification?: Record<string, number>;
  };
  decision: {
    keep_room_ids: string[];
    agent_order?: string[] | null;
    overridden?: boolean | null;
    payload?: { reason: string; override_reason?: string | null };
  } | null;
  review_progress?: { landlords: number; decided: number } | null;
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
  one_time_vnd?: number | null;
  fees: Fee[];
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
  pending_review: "Chờ chủ nhà duyệt",
  partially_published: "Đã có chủ nhà duyệt một phần",
  reviewed: "Đang hoàn tất quyết định",
  published: "Đã duyệt",
  invalidated: "Gợi ý đã hết hiệu lực",
  no_match: "Chưa có phòng đáp ứng",
  needs_verification: "Cần xác minh thông tin",
  rejected: "Danh sách chưa được chấp thuận",
  needs_revision: "Cần điều chỉnh nhu cầu",
  generation_failed: "Tạo gợi ý chưa thành công",
  generating_failed: "Tạo gợi ý chưa thành công",
  ai_unavailable: "Trợ lý tạm thời không khả dụng",
  requested: "Chờ xác nhận lịch",
  confirmed: "Lịch đã xác nhận",
  declined: "Lịch chưa được chấp nhận",
};
