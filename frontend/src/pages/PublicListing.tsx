import { useEffect, useMemo, useState } from "react";
import { Api } from "../api";
import type { Cost, Room, TrustCheck } from "../types";
import { trustLabels } from "../types";
import { addressLine, postedAgoLabel, roomTypeLabels } from "../types";
import { goongApiKey } from "../map";
import { Brand } from "../components/Brand";
import {
  AmenityGrid,
  ContactInfo,
  CostBreakdown,
  DescriptionText,
  EmptyState,
  PosterBadge,
  PromotionBadge,
  SpecList,
  TermsBlock,
  money,
  roomTitle,
} from "../components/Shared";
import { MapView } from "../components/MapView";
import { ListingMedia } from "../components/PhotoGallery";
import { ViewingForm } from "../components/ViewingPanel";
// Trang tin công khai (đích của link chia sẻ đa kênh). Khách ẩn danh xem được;
// đã đăng nhập thì máy chủ trả thêm tên người đăng trong khối liên hệ (C1b).
// crawl.md D: bố cục hai phần — trên là media + thông số + hành động, dưới là
// mô tả, vị trí, tiện ích, điều khoản, chi phí, bản đồ. Mục tin không ghi hiện
// "Chưa có thông tin", không bao giờ 0/null; phí chưa biết vẫn null.
export function PublicListing({ roomId }: { roomId: string }) {
  const [room, setRoom] = useState<
    (Room & { cost: Cost; house_rules?: string | null }) | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // Bản đồ nạp muộn (lazy): mỗi lần mount là 1 map load của Goong — chỉ nạp
  // khi người dùng bấm xem, đỡ đốt quota 1.000 map loads/tháng.
  const [mapOpen, setMapOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  // crawl.md E-07: form đặt lịch DÙNG CHUNG (ViewingForm) thay form riêng.
  const [bookingOpen, setBookingOpen] = useState(false);
  // crawl.md E-05/E-06: báo cáo tin + nút báo cáo.
  const [reportOpen, setReportOpen] = useState(false);
  const [reportReason, setReportReason] = useState("scam_suspect");
  const [reportNote, setReportNote] = useState("");
  // D-4: gửi token nếu đã đăng nhập — người đã đăng nhập thấy tên người đăng
  // trong khối liên hệ và đặt lịch được; khách ẩn danh vẫn xem được tin.
  const signedIn = Boolean(sessionStorage.getItem("homematch.token"));
  const api = useMemo(
    () => new Api(sessionStorage.getItem("homematch.token"), () => {}),
    [],
  );
  useEffect(() => {
    api
      .get<Room & { cost: Cost }>(`/listings/${encodeURIComponent(roomId)}`)
      .then(setRoom)
      .catch((err) => setError((err as Error).message));
  }, [roomId, api]);
  const submitReport = async () => {
    if (!room) return;
    try {
      await api.post(`/listings/${encodeURIComponent(room.id)}/reports`, {
        reason: reportReason,
        note: reportNote.trim() || null,
      });
      setNotice("Đã gửi báo cáo tin. Cảm ơn bạn, chúng tôi sẽ rà lại tin này.");
      setReportOpen(false);
      setReportNote("");
    } catch (err) {
      setNotice((err as Error).message);
    }
  };
  const toggleSave = async () => {
    try {
      await api[saved ? "delete" : "post"](
        `/rooms/${encodeURIComponent(roomId)}/saved`,
      );
      setSaved(!saved);
    } catch (err) {
      setNotice((err as Error).message);
    }
  };
  const share = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setNotice("Đã sao chép liên kết tin.");
    } catch {
      setNotice("Không sao chép được liên kết; hãy copy từ thanh địa chỉ.");
    }
  };
  const directionsHref =
    room?.latitude != null && room?.longitude != null
      ? `https://www.google.com/maps/dir/?api=1&destination=${room.latitude},${room.longitude}`
      : null;
  return (
    <main className="public-listing">
      <header className="topbar">
        <Brand />
        {!signedIn && (
          <a className="button small" href="/dang-nhap">
            Đăng nhập để đặt lịch xem
          </a>
        )}
      </header>
      <section className="panel listing-detail">
        {error ? (
          <EmptyState
            title="Không tìm thấy tin"
            description="Tin có thể đã ẩn hoặc không còn cho thuê."
            icon="home"
          />
        ) : !room ? (
          <p>Đang tải tin…</p>
        ) : (
          <>
            <div className="listing-detail-top">
              <div className="listing-detail-media">
                <ListingMedia item={room} title={roomTitle(room.title)} />
              </div>
              <div className="listing-detail-facts">
                <span className="eyebrow">
                  {room.area} · {room.city} ·{" "}
                  {roomTypeLabels[room.room_type ?? "room"]}
                  {room.bedrooms ? ` · ${room.bedrooms}PN` : ""}
                </span>
                <h1>
                  {roomTitle(room.title)}{" "}
                  <PosterBadge posterKind={room.poster_kind} />
                </h1>
                <p className="listing-detail-price">
                  {money(room.quote.rent_vnd)}/tháng
                  {room.quote.deposit_vnd != null &&
                    ` · cọc ${money(room.quote.deposit_vnd)}`}
                </p>
                {addressLine(room) && (
                  <p className="listing-detail-address">{addressLine(room)}</p>
                )}
                {postedAgoLabel(room.posted_at) && (
                  <small>{postedAgoLabel(room.posted_at)}</small>
                )}
                {room.promotion && (
                  <PromotionBadge promotion={room.promotion} withText />
                )}
                <SpecList room={room} />
                <p className="input-hint">
                  Chưa chuyển tiền hay đặt cọc bất kỳ khoản nào TRƯỚC KHI trực
                  tiếp xem phòng.
                </p>
                <div className="listing-detail-actions">
                  {signedIn ? (
                    <button
                      className="button small"
                      onClick={() => setBookingOpen(true)}
                    >
                      Đặt lịch xem
                    </button>
                  ) : (
                    <a className="button small" href="/dang-nhap">
                      Đăng nhập để đặt lịch
                    </a>
                  )}
                  <button
                    className="button small outline"
                    onClick={() => setReportOpen((value) => !value)}
                  >
                    Báo cáo tin này
                  </button>
                  {signedIn && (
                    <button
                      className="button small outline"
                      aria-pressed={saved}
                      onClick={() => void toggleSave()}
                    >
                      {saved ? "Đã lưu" : "Lưu tin"}
                    </button>
                  )}
                  <a className="button small outline" href="/tim-kiem">
                    So sánh
                  </a>
                  {directionsHref && (
                    <a
                      className="button small outline"
                      href={directionsHref}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Đường đi
                    </a>
                  )}
                  <button
                    className="button small outline"
                    onClick={() => void share()}
                  >
                    Chia sẻ
                  </button>
                </div>
                {notice && <p className="notice">{notice}</p>}
                <ContactInfo contact={room.contact} />
              </div>
            </div>
            <div className="listing-detail-sections">
              <section className="listing-detail-section">
                <h2>Mô tả</h2>
                {room.features_text && <p>{room.features_text}</p>}
                <DescriptionText description={room.description} />
              </section>
              <section className="listing-detail-section">
                <h2>Tiện ích</h2>
                {/* crawl.md E-06 (lỗi 3): tiện ích chỉ đọc từ nội dung tin —
                    nhãn nguồn nói rõ, không suy mục nào ngoài tin. */}
                {!room.synthetic && <small>Theo nội dung tin</small>}
                <AmenityGrid amenities={room.amenities} />
              </section>
              <section className="listing-detail-section">
                <TermsBlock room={room} />
              </section>
              <section className="listing-detail-section">
                <h2>Chi phí ước tính</h2>
                <CostBreakdown cost={room.cost} />
              </section>
              <section className="listing-detail-section">
                <h2>Nội quy</h2>
                <p>{room.house_rules || "Chưa có thông tin"}</p>
              </section>
              <section className="listing-detail-section">
                <h2>Vị trí trên bản đồ</h2>
                {mapOpen ? (
                  <>
                    <MapView
                      pins={[
                        {
                          ...room,
                          monthly: room.cost.monthly_total_vnd,
                        },
                      ]}
                    />
                    {room.latitude != null &&
                      room.longitude != null &&
                      room.location_accuracy !== "area_only" && (
                        <p className="listing-map-links">
                          <a
                            href={`https://map.goong.io/?lat=${room.latitude}&lng=${room.longitude}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Mở trong Goong Maps ↗
                          </a>
                          {/* Xem đường đi bằng deep-link: không gọi Directions API,
                              không tốn quota. Google Maps có URL chuẩn và app di động. */}
                          <a
                            href={`https://www.google.com/maps/dir/?api=1&destination=${room.latitude},${room.longitude}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            Xem đường đi ↗
                          </a>
                          {!goongApiKey() && (
                            <small>
                              Chưa cấu hình key Goong — bản đồ dùng tile dự
                              phòng.
                            </small>
                          )}
                        </p>
                      )}
                  </>
                ) : (
                  <button
                    type="button"
                    className="button outline small"
                    onClick={() => setMapOpen(true)}
                  >
                    Xem bản đồ gần đúng
                  </button>
                )}
              </section>
            </div>
            <section className="listing-detail-section">
              <h2>Kiểm chứng tin</h2>
              {room.trust ? (
                <ul className="trust-list">
                  {Object.entries(room.trust)
                    .filter(
                      ([key, value]) =>
                        key !== "notice" &&
                        typeof value === "object" &&
                        value !== null,
                    )
                    .map(([key, value]) => (
                      <li
                        key={key}
                        className={`trust-${(value as TrustCheck).status}`}
                      >
                        <strong>{trustLabels[key] || key}:</strong>{" "}
                        {(value as TrustCheck).status === "ok"
                          ? "Đạt"
                          : (value as TrustCheck).status === "warn"
                            ? "Cần lưu ý"
                            : "Không rõ"}{" "}
                        — {(value as TrustCheck).detail}
                      </li>
                    ))}
                </ul>
              ) : null}
              <p className="input-hint">
                {room.trust?.notice ||
                  "Kiểm chứng tính tự động, không phải chứng nhận."}
              </p>
            </section>
            <section className="listing-detail-section">
              <h2>Chỗ ở tương tự</h2>
              {room.similar_rooms?.length ? (
                <ul className="similar-list">
                  {room.similar_rooms.map((other) => (
                    <li key={other.id}>
                      <a href={`/tin/${other.id}`}>{roomTitle(other.title)}</a>{" "}
                      · {money(other.rent_vnd)}/tháng
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="detail-missing">Chưa có thông tin</p>
              )}
            </section>
            <p className="input-hint">
              Vị trí công khai là gần đúng. Chi phí là ước tính cho 1 người, 1
              xe.
              {room.synthetic ? " Dữ liệu giả lập phục vụ nghiên cứu." : ""}
            </p>
            {notice && <p className="notice">{notice}</p>}
            {bookingOpen && signedIn && (
              <ViewingForm
                room={{
                  room_id: room.id,
                  title: room.title,
                  area: room.area,
                }}
                sessionId={null}
                api={api}
                onDone={() => {
                  setBookingOpen(false);
                  setNotice(
                    room.contact?.kind === "external"
                      ? "Đã gửi lịch xem mong muốn. HomeMatch sẽ liên hệ người đăng để xác nhận; đây chưa phải lịch đã chốt."
                      : "Đã gửi lịch xem mong muốn; bên phụ trách tin sẽ xác nhận hoặc đề xuất giờ khác.",
                  );
                }}
                onCancel={() => setBookingOpen(false)}
              />
            )}
            {reportOpen && (
              <form
                className="panel report-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void submitReport();
                }}
              >
                <h2>Báo cáo tin này</h2>
                <label>
                  Lý do
                  <select
                    value={reportReason}
                    onChange={(event) => setReportReason(event.target.value)}
                  >
                    <option value="scam_suspect">Nghi vấn lừa đảo</option>
                    <option value="already_rented">Phòng đã cho thuê</option>
                    <option value="wrong_info">Thông tin sai</option>
                    <option value="duplicate">Tin trùng lặp</option>
                    <option value="contact_missing">Thiếu liên hệ</option>
                    <option value="other">Lý do khác</option>
                  </select>
                </label>
                <label>
                  Ghi chú (không ghi SĐT cá nhân của bạn)
                  <textarea
                    maxLength={500}
                    value={reportNote}
                    onChange={(event) => setReportNote(event.target.value)}
                  />
                </label>
                <div className="form-actions">
                  <button
                    type="button"
                    className="button outline small"
                    onClick={() => setReportOpen(false)}
                  >
                    Đóng
                  </button>
                  <button className="button small">Gửi báo cáo</button>
                </div>
              </form>
            )}
          </>
        )}
      </section>
    </main>
  );
}
