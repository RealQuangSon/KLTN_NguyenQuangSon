import { useState } from "react";
import type {
  ListingContact,
  Affordability,
  Candidate,
  Cost,
  Promotion,
  Results,
  Room,
} from "../types";
import {
  amenities,
  bandLabels,
  fees,
  posterLabels,
  roomTypeLabels,
  statusLabels,
  verificationText,
  visibleStatuses,
} from "../types";
import { RoomIllustration } from "./RoomIllustration";
import { AdviceBox, type Advice } from "./Advice";
export const money = (amount: number | null | undefined) =>
  amount == null
    ? "Chưa xác định"
    : `${new Intl.NumberFormat("vi-VN").format(amount)} ₫`;
export const roomTitle = (title: string) => title.split(". ")[0];
// FE-06: valid_until là "YYYY-MM-DD"; hiển thị ngày/tháng không phụ thuộc múi giờ.
export const dayMonth = (isoDate: string) => {
  const parts = isoDate.split("-");
  return parts.length === 3 ? `${parts[2]}/${parts[1]}` : isoDate;
};
// Nhãn "Ưu đãi" chỉ mô tả ưu đãi của chủ nhà, không ngụ ý xếp hạng ưu tiên và
// không đổi giá hiển thị; chỉ xuất hiện khi promotion khác null.
export function PromotionBadge({
  promotion,
  withText = false,
}: {
  promotion: Promotion;
  withText?: boolean;
}) {
  return (
    <span
      className="promo-chip"
      title={`Ưu đãi của chủ nhà: ${promotion.text}`}
    >
      <span className="badge promo">Ưu đãi</span>
      <small>đến {dayMonth(promotion.valid_until)}</small>
      {withText && <span className="promo-text">{promotion.text}</span>}
    </span>
  );
}
// LF-05: nhãn người đăng tin. Chỉ hiện khi máy chủ trả giá trị; null thì
// không hiện gì (không suy ra "Chính chủ" — tin có thể do môi giới đăng).
export function PosterBadge({
  posterKind,
}: {
  posterKind?: "broker" | "individual" | null;
}) {
  if (!posterKind) return null;
  return (
    <span
      className={`badge ${posterKind === "broker" ? "broker" : "owner"}`}
      title={
        posterKind === "broker"
          ? "Tin do môi giới đăng"
          : "Tin do cá nhân chủ nhà đăng"
      }
    >
      {posterLabels[posterKind]}
    </span>
  );
}
// LF-05: khối "Điều khoản thuê". Mục tin không ghi hiện "Chưa rõ", không bao
// giờ suy ra 0 hay giá trị mặc định.
export function TermsBlock({ room }: { room: Room }) {
  const rows: [string, string | null][] = [
    ["Giá thuê", `${money(room.quote.rent_vnd)}/tháng`],
    ["Diện tích", `${room.area_m2} m²`],
    [
      "Tiền cọc",
      room.quote.deposit_vnd == null ? null : money(room.quote.deposit_vnd),
    ],
    [
      "Kỳ thanh toán",
      room.quote.payment_cycle_months == null
        ? null
        : `${room.quote.payment_cycle_months} tháng/lần`,
    ],
    [
      "Thời hạn hợp đồng tối thiểu",
      room.quote.min_lease_months == null
        ? null
        : `${room.quote.min_lease_months} tháng`,
    ],
    [
      "Trống từ",
      room.available_from == null ? null : dayMonth(room.available_from),
    ],
  ];
  return (
    <div>
      <h3>Điều khoản thuê</h3>
      <ul className="catalog-fees">
        {rows.map(([label, value]) => (
          <li key={label}>
            {label}: {value ?? "Chưa rõ"}
          </li>
        ))}
      </ul>
    </div>
  );
}
// LF-05: chip tiện ích — true hiện bình thường, false gạch ngang, null không hiện.
export function AmenityChips({
  amenities: values,
}: {
  amenities: Record<string, boolean | null>;
}) {
  const known = Object.entries(values).filter(
    ([, value]) => value === true || value === false,
  );
  if (!known.length) return null;
  return (
    <div className="chip-row" role="list" aria-label="Tiện ích của phòng">
      {known.map(([key, value]) => (
        <span role="listitem" key={key} className="choice">
          {value === true ? (
            amenities[key] || key
          ) : (
            <s title="Tin ghi rõ không có tiện ích này">
              {amenities[key] || key}
            </s>
          )}
        </span>
      ))}
    </div>
  );
}
// LF-05: nội dung tin (đã che SĐT/email ở máy chủ), thu gọn kèm "Xem thêm".
const DESCRIPTION_PREVIEW = 220;
export function DescriptionText({
  description,
}: {
  description?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!description) return null;
  const short = description.length <= DESCRIPTION_PREVIEW;
  const shown =
    expanded || short
      ? description
      : `${description.slice(0, DESCRIPTION_PREVIEW).trimEnd()}…`;
  return (
    <p className="listing-description">
      {shown}
      {!short && (
        <>
          {" "}
          <button
            type="button"
            className="text-button"
            onClick={() => setExpanded((value) => !value)}
          >
            {expanded ? "Thu gọn" : "Xem thêm"}
          </button>
        </>
      )}
    </p>
  );
}
// Liên hệ người đăng: tin cào trỏ về tin gốc (chủ nhà trong app là tài khoản
// demo); tin của chủ nhà có tài khoản hiện SĐT họ tự khai.
export function ContactInfo({ contact }: { contact?: ListingContact }) {
  if (!contact) return null;
  if (contact.kind === "external")
    return contact.original_url ? (
      <p className="contact-info">
        <a
          href={contact.original_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          Xem tin gốc trên Chợ Tốt
        </a>
        <small> · Tin tham khảo; liên hệ người đăng tại tin gốc.</small>
      </p>
    ) : null;
  if (contact.phone)
    return (
      <p className="contact-info">
        SĐT chủ nhà: <a href={`tel:${contact.phone}`}>{contact.phone}</a>
      </p>
    );
  if (contact.phone_requires_login)
    return (
      <p className="contact-info">
        <small>Đăng nhập để xem số điện thoại chủ nhà.</small>
      </p>
    );
  return null;
}
export const evidenceText = (text: string) =>
  text.replace(
    /\b(window|quiet|private_bathroom|parking|air_conditioning|washing_machine|balcony|furniture|pets_allowed|kitchen|wifi|elevator|security_24h|camera|loft|flexible_hours|no_shared_landlord|water_heater|fridge)\b/g,
    (key) => amenities[key] || key,
  );
export function Icon({
  name = "home",
  size = 20,
}: {
  name?: string;
  size?: number;
}) {
  const paths: Record<string, string> = {
    home: "M3 10L12 3l9 7v10H3V10zm6 10v-7h6v7",
    chat: "M4 4h16v12H9l-5 4V4z",
    compare: "M4 4h6v16H4V4zm10 0h6v16h-6V4z",
    calendar: "M4 6h16v14H4V6zm3-3v6m10-6v6M4 11h16",
    check: "M5 12l4 4L19 6",
    arrow: "M5 12h14m-5-5l5 5-5 5",
    logout: "M9 4H4v16h5m3-8h9m-4-4l4 4-4 4",
    shield: "M12 3l8 3v6c0 5-8 9-8 9S4 17 4 12V6l8-3z",
    sun: "M12 8a4 4 0 100 8 4 4 0 000-8m0-6v2m0 16v2M2 12h2m16 0h2M5 5l2 2m10 10l2 2M5 19l2-2M17 7l2-2",
    grid: "M3 3h7v7H3V3zm11 0h7v7h-7V3zM3 14h7v7H3v-7zm11 0h7v7h-7v-7",
    refresh: "M20 10a8 8 0 10-1 7m1-13v6h-6",
    chevron: "M9 5l7 7-7 7",
    search: "M20 20l-5-5M10 3a7 7 0 100 14 7 7 0 000-14",
    pin: "M20 10c0 6-8 11-8 11S4 16 4 10a8 8 0 1116 0zm-8-3a3 3 0 100 6 3 3 0 000-6",
    eye: "M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12zm10-3a3 3 0 100 6 3 3 0 000-6",
    eyeOff: "M3 3l18 18M9 5c7-2 13 7 13 7l-3 4M6 6l-4 6s4 7 10 7l4-2",
    close: "M6 6l12 12M6 18 18 6",
    clock: "M12 3a9 9 0 100 18 9 9 0 000-18m0 5v5l3 2",
    leaf: "M5 20l14-14M4 17C1 5 10 3 21 3c0 11-2 18-13 16",
    sparkles:
      "M12 3l2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5L12 3zm7-1v4m-2-2h4",
    cap: "M12 4l10 5-10 5L2 9l10-5zm-6 8.5V17c0 1.7 2.7 3 6 3s6-1.3 6-3v-4.5",
    work: "M4 8h16v12H4V8zm5 0V5h6v3m-11 6h16",
    sofa: "M6 11V8a2 2 0 012-2h8a2 2 0 012 2v3M4 18v-4a2 2 0 012-2h12a2 2 0 012 2v4M4 18h16M6 15v3m12-3v3",
    wallet: "M3 6h18v12H3V6zm0 4h18m-5 4h2",
    mail: "M3 5h18v14H3V5zm0 3l9 6 9-6",
    send: "M4 12l16-8-6 16-3-6-7-2zm7 2l9-10",
    mic: "M12 2a3 3 0 00-3 3v6a3 3 0 006 0V5a3 3 0 00-3-3zM19 11a7 7 0 01-14 0M12 18v4",
    heart:
      "M12 20.5C7.5 16.9 3.5 13.6 3.5 9.8A4.6 4.6 0 0112 7a4.6 4.6 0 018.5 2.8c0 3.8-4 7.1-8.5 10.7z",
    layers: "M12 3l9 5-9 5-9-5 9-5zm9 10l-9 5-9-5m18 5l-9 5-9-5",
    expand: "M4 9V4h5m11 11v5h-5m0-16h5v5M9 20H4v-5",
    user: "M12 11a4 4 0 100-8 4 4 0 000 8zm-8 9a8 8 0 0116 0",
    thumbUp:
      "M7 11v9H4a1 1 0 01-1-1v-7a1 1 0 011-1h3zm3 9h7a2 2 0 002-1.7l1-5A2 2 0 0018 11h-4l1-4.1A2 2 0 0013 5l-3 6v9z",
    thumbDown:
      "M17 13V4h3a1 1 0 011 1v7a1 1 0 01-1 1h-3zm-3-9H7a2 2 0 00-2 1.7l-1 5A2 2 0 006 13h4l-1 4.1A2 2 0 0011 19l3-6V4z",
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] || paths.home} />
    </svg>
  );
}
export function ErrorNotice({
  error,
  onClose,
}: {
  error: string | null;
  onClose?: () => void;
}) {
  return error ? (
    <div className="notice error" role="alert">
      <span>{error}</span>
      {onClose && (
        <button type="button" className="text-button" onClick={onClose}>
          Đóng
        </button>
      )}
    </div>
  ) : null;
}
export function Badge({ status }: { status: string }) {
  return (
    <span
      className={`badge ${status === "published" || status === "partially_published" || status === "confirmed" ? "success" : status === "invalidated" || status === "declined" ? "muted" : ""}`}
    >
      {statusLabels[status] || status}
    </span>
  );
}
export function EmptyState({
  title,
  description,
  icon = "home",
}: {
  title: string;
  description: string;
  icon?: string;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">
        <Icon name={icon} size={28} />
      </div>
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}
export const percent = (ratio: string | null) =>
  ratio == null
    ? null
    : `${new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 1 }).format(Number(ratio) * 100)}%`;
const bandIcon: Record<string, string> = {
  phu_hop: "check",
  can_nhac: "shield",
  vuot: "shield",
  chua_ro: "shield",
};
export function AffordabilitySummary({
  affordability,
}: {
  affordability: Affordability;
}) {
  const { loan, band } = affordability;
  const ratio = percent(affordability.housing_ratio);
  return (
    <div className={`affordability band-${band}`}>
      <span className={`badge band ${band}`}>
        <Icon name={bandIcon[band]} size={13} />
        {bandLabels[band]}
        {ratio && ` · ${ratio} thu nhập`}
      </span>
      {loan && (
        <small>
          Thiếu {money(loan.principal_vnd)} tiền vào ở → vay {loan.term_months}{" "}
          tháng, trả góp {money(loan.installment_vnd)}
          /tháng, tổng lãi {money(loan.total_interest_vnd)} (ước tính, lãi suất
          bạn nhập).
        </small>
      )}
      {affordability.renter_burden_vnd != null &&
        affordability.renter_burden_vnd !== affordability.burden_vnd && (
          <small>
            Phần của bạn khi chia đều: {money(affordability.renter_burden_vnd)}
            /tháng.
          </small>
        )}
    </div>
  );
}
export function CostBreakdown({
  cost,
  compact = false,
}: {
  cost: Cost;
  compact?: boolean;
}) {
  return (
    <div className="cost-breakdown">
      <div className="cost-totals">
        <div>
          <span>Tổng mỗi tháng</span>
          <strong>{money(cost.monthly_total_vnd)}</strong>
          {cost.monthly_total_vnd === null && (
            <small>Đã biết {money(cost.monthly_known_vnd)} · còn thiếu</small>
          )}
        </div>
        <div>
          <span>Tiền chuẩn bị vào ở</span>
          <strong>{money(cost.initial_total_vnd)}</strong>
          {cost.initial_total_vnd === null && (
            <small>Đã biết {money(cost.initial_known_vnd)} · còn thiếu</small>
          )}
        </div>
      </div>
      {cost.affordability && (
        <AffordabilitySummary affordability={cost.affordability} />
      )}
      {!compact && (
        <>
          <table className="fee-table">
            <thead>
              <tr>
                <th>Khoản phí</th>
                <th>Chu kỳ</th>
                <th>Chi phí</th>
              </tr>
            </thead>
            <tbody>
              {cost.lines.map((line, i) => (
                <tr key={`${line.name}-${i}`}>
                  <td>
                    {fees[line.name] || line.name}
                    {line.included_in_rent && (
                      <small>Đã gồm trong tiền thuê</small>
                    )}
                    <small className="source-text">{line.source}</small>
                  </td>
                  <td>
                    {line.period === "monthly" ? "Hàng tháng" : "Ban đầu"}
                  </td>
                  <td className={line.amount_vnd === null ? "unknown" : ""}>
                    {money(line.amount_vnd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="assumptions">
            Kịch bản đã xác nhận:{" "}
            {Object.entries(cost.assumptions)
              .map(
                ([key, value]) =>
                  `${({ people: "người", vehicles: "xe", electricity_kwh: "kWh điện", water_m3: "m³ nước", moving_vnd: "chuyển nhà", setup_vnd: "sắm sửa" } as Record<string, string>)[key] || key}: ${String(value)}`,
              )
              .join(" · ")}
          </div>
        </>
      )}
      {(cost.missing_monthly.length > 0 || cost.missing_initial.length > 0) && (
        <p className="notice warning">
          Chưa đủ thông tin:{" "}
          {[...cost.missing_monthly, ...cost.missing_initial]
            .map((x) => fees[x] || x)
            .join(", ")}
          . Phần đã biết chưa phải tổng đầy đủ.
        </p>
      )}
    </div>
  );
}
export function RoomCard({
  item,
  selected,
  onSelect,
  onViewing,
  onSimulate,
  onChat,
  saved,
  onToggleSave,
}: {
  item: Candidate;
  selected?: boolean;
  onSelect?: () => void;
  onViewing?: () => void;
  onSimulate?: () => void;
  onChat?: () => void;
  // "Căn đã lưu" cá nhân của người thuê (trang cá nhân, tham chiếu Tin đã lưu).
  saved?: boolean;
  onToggleSave?: () => void;
}) {
  const [details, setDetails] = useState(false);
  return (
    <article className={`room-card ${selected ? "selected" : ""}`}>
      <div className="room-visual" aria-hidden="true">
        <RoomIllustration />
        <span className="room-area">{item.area_m2} m²</span>
        <small className="room-image-label">Hình minh họa</small>
      </div>
      <div className="room-content">
        <div className="room-topline">
          <span className="eyebrow">
            <Icon name="pin" size={13} />
            {item.area} · {item.city}
            {item.room_type && ` · ${roomTypeLabels[item.room_type]}`}
            {item.bedrooms ? ` ${item.bedrooms}PN` : ""}
          </span>
          {item.synthetic && (
            <span className="badge muted">Dữ liệu giả lập</span>
          )}
        </div>
        <h3>{roomTitle(item.title)}</h3>
        {roomTitle(item.title) !== item.title && (
          <details className="room-description">
            <summary>Mô tả từ nguồn</summary>
            <p>{item.title}</p>
          </details>
        )}
        <CostBreakdown cost={item.cost} compact />
        <ul className="reasons">
          {item.reasons.map((r, i) => (
            <li key={i}>
              <Icon name="check" size={15} />
              {evidenceText(r)}
            </li>
          ))}
        </ul>
        {item.tradeoffs.length > 0 && (
          <p className="tradeoff">
            <strong>Đánh đổi:</strong>{" "}
            {evidenceText(item.tradeoffs.join(" · "))}
          </p>
        )}
        {item.verification && item.verification.length > 0 && (
          <p className="tradeoff verification">
            <strong>Cần xác minh:</strong>{" "}
            {item.verification.map(verificationText).join(" · ")}
          </p>
        )}
        <div className="evidence">
          <span>Nguồn: {item.source}</span>
          <span>
            Phiên bản {item.room_revision} · {item.algorithm}
          </span>
        </div>
        <div className="room-actions">
          <button
            className="text-button"
            onClick={() => setDetails(!details)}
            aria-expanded={details}
          >
            {details ? "Thu gọn phí" : "Xem bảng phí"}
          </button>
          {onToggleSave && (
            <button
              className={`button small outline save-room${saved ? " saved" : ""}`}
              onClick={onToggleSave}
              aria-pressed={Boolean(saved)}
              aria-label={saved ? "Bỏ lưu căn này" : "Lưu căn này"}
            >
              <Icon name="heart" size={16} />
              {saved ? "Đã lưu" : "Lưu"}
            </button>
          )}
          {onSelect && (
            <button
              className={`button small ${selected ? "secondary" : "outline"}`}
              onClick={onSelect}
              aria-pressed={Boolean(selected)}
            >
              <Icon name="compare" size={16} />
              {selected ? "Đã chọn" : "So sánh"}
            </button>
          )}
          {onChat && (
            <button className="button small outline" onClick={onChat}>
              <Icon name="chat" size={16} />
              Chat với chủ nhà
            </button>
          )}
          {onSimulate && (
            <button className="button small outline" onClick={onSimulate}>
              <Icon name="refresh" size={16} />
              Mô phỏng tài chính
            </button>
          )}
          {onViewing && (
            <button className="button small" onClick={onViewing}>
              <Icon name="calendar" size={16} />
              Yêu cầu xem
            </button>
          )}
        </div>
        {details && <CostBreakdown cost={item.cost} />}
      </div>
    </article>
  );
}
export function PublishedResults({
  result,
  selected,
  onSelect,
  onViewing,
  onSimulate,
  onChat,
  onAskFollowUp,
  savedIds,
  onToggleSave,
}: {
  result: Results | null;
  selected: string[];
  onSelect: (id: string) => void;
  onViewing: (item: Candidate) => void;
  onSimulate?: (item: Candidate) => void;
  onChat?: (item: Candidate) => void;
  // Điền câu hỏi tiếp theo vào ô chat; chỉ điền — người dùng tự quyết định gửi,
  // hệ thống không tự nới điều kiện cứng.
  onAskFollowUp?: (text: string) => void;
  // Căn đã lưu của người thuê: bộ id hiện trạng + bật/tắt lưu ngay trên thẻ.
  savedIds?: string[];
  onToggleSave?: (roomId: string) => void;
}) {
  if (!result)
    return (
      <EmptyState
        title="Bắt đầu từ nhu cầu của bạn"
        description="Trò chuyện với trợ lý, kiểm tra hồ sơ và xác nhận để tìm phòng phù hợp."
        icon="chat"
      />
    );
  if (!visibleStatuses.includes(result.status)) {
    const descriptions: Record<string, string> = {
      generating:
        "Hệ thống đang kiểm tra điều kiện và tổng chi phí theo hồ sơ đã xác nhận.",
      invalidated:
        "Nhu cầu hoặc kho phòng đã thay đổi. Xác nhận hồ sơ để tạo bản mới và tìm lại.",
      no_match:
        "Chưa có phòng đạt đầy đủ điều kiện. Bạn có thể chủ động sửa tiêu chí; hệ thống không tự nới ngân sách.",
      needs_verification:
        "Có phòng cần xác minh giá, phí hoặc điều kiện bắt buộc. Thiếu dữ liệu chưa có nghĩa là đạt yêu cầu.",
      generation_failed:
        "Tạo gợi ý bị gián đoạn. Chạy lại vòng tìm hoặc liên hệ quản trị để khôi phục an toàn.",
    };
    return (
      <>
        <EmptyState
          title={statusLabels[result.status] || "Chờ xử lý"}
          description={
            descriptions[result.status] ||
            "Kiểm tra và xác nhận hồ sơ để tiếp tục."
          }
          icon="home"
        />
        {result.suggestions && result.suggestions.length > 0 && (
          <div className="suggestion-list">
            <span className="eyebrow">BƯỚC TIẾP THEO (TỰ CHỌN)</span>
            <ul>
              {result.suggestions.map((suggestion, index) => (
                <li key={index}>{suggestion}</li>
              ))}
            </ul>
            <small>
              Hệ thống không tự nới điều kiện cứng; mọi thay đổi do bạn xác nhận
              lại trong hồ sơ.
            </small>
          </div>
        )}
        {Object.values(result.diagnostics_summary?.verification ?? {}).some(
          (count) => count > 0,
        ) &&
          onAskFollowUp && (
            <div className="suggestion-list">
              <span className="eyebrow">PHÒNG THIẾU DỮ LIỆU</span>
              <div className="relax-chips">
                <button
                  type="button"
                  className="button small outline"
                  onClick={() =>
                    onAskFollowUp(
                      "Chấp nhận dữ liệu ước tính — cho mình xem cả phòng thiếu bảng phí hoặc sức chứa, dữ liệu theo giả định chuẩn có nhãn ước tính nhé.",
                    )
                  }
                >
                  Chấp nhận dữ liệu ước tính
                </button>
              </div>
              <small>
                Dữ liệu thiếu trong tin (phí điện/nước, sức chứa…) được thay
                bằng giả định chuẩn kèm nhãn ước tính; bạn kiểm tra lại khi xem
                phòng.
              </small>
            </div>
          )}
        {result.status === "no_match" && onAskFollowUp && (
          <div className="suggestion-list">
            <span className="eyebrow">NỚI MỘT TIÊU CHÍ ĐỂ TÌM LẠI</span>
            <div className="relax-chips">
              <button
                type="button"
                className="button small outline"
                onClick={() =>
                  onAskFollowUp(
                    "Hãy nới ngân sách tổng tháng lên thêm 1 triệu và tìm lại.",
                  )
                }
              >
                Nới ngân sách
              </button>
              <button
                type="button"
                className="button small outline"
                onClick={() =>
                  onAskFollowUp(
                    "Cho mình xem căn ở khu vực lân cận, không giới hạn quận.",
                  )
                }
              >
                Nới khu vực
              </button>
              <button
                type="button"
                className="button small outline"
                onClick={() =>
                  onAskFollowUp(
                    "Nới khoảng cách tới điểm đến của mình thêm 1 km và tìm lại.",
                  )
                }
              >
                Nới khoảng cách
              </button>
            </div>
            <small>
              Nút chỉ điền câu nhắn vào ô trò chuyện; bạn kiểm tra rồi tự gửi.
            </small>
          </div>
        )}
      </>
    );
  }
  return (
    <div className="room-list">
      {/* Đếm hiển thị kiểu workspace tham chiếu: người dùng biết số căn khớp
          nhu cầu và số căn đang hiện (danh sách giới hạn 5 căn đầu). */}
      <p className="results-count">
        Kết quả phù hợp: <strong>{result.results.length}</strong> căn
        {result.results.length > 5 &&
          ` · đang hiện 5 căn đầu, dùng tìm theo bộ lọc để xem thêm`}
      </p>
      {result.results.slice(0, 5).map((item) => (
        <RoomCard
          key={item.room_id}
          item={item}
          selected={selected.includes(item.room_id)}
          onSelect={() => onSelect(item.room_id)}
          onViewing={() => onViewing(item)}
          onSimulate={onSimulate ? () => onSimulate(item) : undefined}
          onChat={onChat ? () => onChat(item) : undefined}
          saved={savedIds?.includes(item.room_id)}
          onToggleSave={
            onToggleSave ? () => onToggleSave(item.room_id) : undefined
          }
        />
      ))}
    </div>
  );
}
// Ô có giá trị tốt nhất (thấp nhất về tiền, lớn nhất về diện tích) được đánh
// dấu bằng chữ, không chỉ bằng màu; giá trị chưa rõ không bao giờ là "tốt nhất".
const bestIds = (
  items: Candidate[],
  value: (item: Candidate) => number | null | undefined,
  prefer: "low" | "high",
) => {
  const known = items.filter((item) => value(item) != null);
  if (known.length < 2) return new Set<string>();
  const values = known.map((item) => value(item) as number);
  const target = prefer === "low" ? Math.min(...values) : Math.max(...values);
  if (values.every((v) => v === target)) return new Set<string>();
  return new Set(
    known.filter((item) => value(item) === target).map((i) => i.room_id),
  );
};
function CostBars({ items }: { items: Candidate[] }) {
  const rows = [
    {
      label: "Tổng tháng",
      value: (item: Candidate) => item.cost.monthly_total_vnd,
    },
    {
      label: "Tiền vào ở",
      value: (item: Candidate) => item.cost.initial_total_vnd,
    },
  ];
  return (
    <div className="cost-bars" aria-label="Biểu đồ chi phí">
      {rows.map((row) => {
        const max = Math.max(...items.map((item) => row.value(item) ?? 0), 1);
        return (
          <div key={row.label} className="cost-bar-group">
            <strong>{row.label}</strong>
            {items.map((item) => {
              const value = row.value(item);
              return (
                <div key={item.room_id} className="cost-bar-row">
                  <span>{roomTitle(item.title)}</span>
                  <div className="cost-bar-track">
                    {value != null && (
                      <div
                        className="cost-bar-fill"
                        style={{ width: `${(value / max) * 100}%` }}
                      />
                    )}
                  </div>
                  <small>{money(value)}</small>
                </div>
              );
            })}
          </div>
        );
      })}
    </div>
  );
}
export function Comparison({
  items,
  advice,
  onClose,
}: {
  items: Candidate[];
  advice?: Advice | null;
  onClose: () => void;
}) {
  const best = {
    area: bestIds(items, (i) => i.area_m2, "high"),
    monthly: bestIds(items, (i) => i.cost.monthly_total_vnd, "low"),
    initial: bestIds(items, (i) => i.cost.initial_total_vnd, "low"),
  };
  const mark = (set: Set<string>, id: string) =>
    set.has(id) ? <span className="badge success best">Tốt nhất</span> : null;
  return (
    <section className="panel comparison">
      <div className="section-heading">
        <div>
          <span className="eyebrow">CÙNG KỊCH BẢN ĐÃ XÁC NHẬN</span>
          <h2>So sánh các lựa chọn</h2>
        </div>
        <button className="text-button" onClick={onClose}>
          Đóng so sánh
        </button>
      </div>
      {advice && <AdviceBox advice={advice} />}
      <CostBars items={items} />
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Tiêu chí</th>
              {items.map((i) => (
                <th key={i.room_id}>{roomTitle(i.title)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <th>Loại hình</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {i.room_type ? roomTypeLabels[i.room_type] : "Chưa rõ"}
                  {i.bedrooms ? ` · ${i.bedrooms} phòng ngủ` : ""}
                </td>
              ))}
            </tr>
            <tr>
              <th>Diện tích</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {i.area_m2} m² {mark(best.area, i.room_id)}
                </td>
              ))}
            </tr>
            <tr>
              <th>Tổng tháng</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {money(i.cost.monthly_total_vnd)}{" "}
                  {mark(best.monthly, i.room_id)}
                  {i.cost.monthly_total_vnd === null && (
                    <small>Đã biết {money(i.cost.monthly_known_vnd)}</small>
                  )}
                </td>
              ))}
            </tr>
            <tr>
              <th>Tiền ban đầu</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {money(i.cost.initial_total_vnd)}{" "}
                  {mark(best.initial, i.room_id)}
                </td>
              ))}
            </tr>
            <tr>
              <th>Trả góp nếu vay</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {i.cost.affordability?.loan
                    ? `${money(i.cost.affordability.loan.installment_vnd)} × ${i.cost.affordability.loan.term_months} tháng`
                    : "Không cần vay"}
                </td>
              ))}
            </tr>
            <tr>
              <th>Khả năng chi trả</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {i.cost.affordability
                    ? `${bandLabels[i.cost.affordability.band]}${
                        i.cost.affordability.housing_ratio
                          ? ` (${percent(i.cost.affordability.housing_ratio)})`
                          : ""
                      }`
                    : "Chưa rõ"}
                </td>
              ))}
            </tr>
            <tr>
              <th>Phí chưa biết</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {[...i.cost.missing_monthly, ...i.cost.missing_initial]
                    .map((x) => fees[x] || x)
                    .join(", ") || "Đã có đầy đủ theo kịch bản"}
                </td>
              ))}
            </tr>
            <tr>
              <th>Lý do phù hợp</th>
              {items.map((i) => (
                <td key={i.room_id}>{evidenceText(i.reasons.join(" · "))}</td>
              ))}
            </tr>
            <tr>
              <th>Đánh đổi</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {i.tradeoffs.join(" · ") || "Không có đánh đổi được ghi nhận"}
                </td>
              ))}
            </tr>
            <tr>
              <th>Cần xác minh</th>
              {items.map((i) => (
                <td key={i.room_id}>
                  {(i.verification || []).map(verificationText).join(", ") ||
                    "Không có mục chưa rõ"}
                </td>
              ))}
            </tr>
            <tr>
              <th>Nguồn</th>
              {items.map((i) => (
                <td key={i.room_id}>{i.source}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
