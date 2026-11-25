import { useCallback, useEffect, useState } from "react";
import { Api } from "../api";
import type { Actor, Session, Viewing } from "../types";
import { roomTypeLabels } from "../types";
import { ErrorNotice, Icon, money, roomTitle } from "../components/Shared";
import { LoadingState } from "../components/LoadingState";
import { Link } from "../router";
// Tổng quan không gian người thuê (bố cục dashboard): thống kê cá
// nhân, nhu cầu trợ lý đang ghi nhớ, lịch xem sắp tới và căn đã xem gần đây.
// Chỉ gom dữ liệu từ endpoint cá nhân có sẵn — không có số minh họa nào được
// bịa ra; mục "phòng đang thuê" chưa kích hoạt thì nói rõ, không giả lập.
type Card = {
  id: string;
  room_id?: string;
  title: string;
  area: string;
  city: string;
  room_type?: string | null;
  cost?: { monthly_total_vnd: number | null } | null;
};
const upcomingStatuses = new Set<Viewing["status"]>([
  "requested",
  "confirmed",
  "reschedule_proposed",
]);
const viewingStatusLabels: Record<string, string> = {
  requested: "Chờ xác nhận",
  confirmed: "Đã xác nhận",
  declined: "Không nhận",
  cancelled: "Đã huỷ",
  reschedule_proposed: "Đề xuất giờ khác",
  completed: "Đã xem",
  no_show: "Vắng mặt",
};
function needSummary(session: Session): string {
  const d = session.draft;
  const bits: string[] = [];
  if (d.room_type) bits.push(roomTypeLabels[d.room_type]);
  if (d.bedrooms != null) bits.push(`${d.bedrooms} phòng ngủ`);
  const place = [d.area, d.city].filter(Boolean).join(", ");
  if (place) bits.push(`tại ${place}`);
  if (d.budget_hint_vnd != null)
    bits.push(`ngân sách tối đa ${money(d.budget_hint_vnd)}/tháng`);
  return bits.length
    ? `Tìm ${bits.join(", ")}.`
    : "Trợ lý đã mở phiên tư vấn — chi tiết nhu cầu nằm trong màn trợ lý.";
}
const viewTime = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});
export function RenterOverview({ api, actor }: { api: Api; actor: Actor }) {
  const [data, setData] = useState<{
    saved: Card[];
    viewed: Card[];
    views: Viewing[];
    conversations: { id: string }[];
    activeLease: boolean;
    session: Session | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Phiên trợ lý nằm riêng theo tài khoản trên trình duyệt này (cơ chế
      // khôi phục của màn trợ lý); hết hạn thì im lặng, không lỗi cả trang.
      const sid = sessionStorage.getItem(`homematch.session.${actor.id}`);
      const [saved, viewed, views, conversations, leases, session] =
        await Promise.all([
          api.get<Card[]>("/rooms/saved"),
          api.get<Card[]>("/rooms/viewed"),
          api.get<Viewing[]>("/viewings"),
          api.get<{ id: string }[]>("/conversations"),
          api.get<{ status: string }[]>("/leases"),
          sid
            ? api
                .get<Session>(`/sessions/${encodeURIComponent(sid)}`)
                .catch(() => null)
            : Promise.resolve(null),
        ]);
      setData({
        saved,
        viewed,
        views,
        conversations,
        activeLease: leases.some((lease) => lease.status === "active"),
        session,
      });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [api, actor.id]);
  useEffect(() => {
    void load();
  }, [load]);
  const upcoming = (data?.views ?? [])
    .filter((view) => upcomingStatuses.has(view.status))
    .sort((a, b) => a.requested_at.localeCompare(b.requested_at));
  const recentViewed = (data?.viewed ?? []).slice(0, 3);
  return (
    <>
      <div className="overview-greeting">
        <h1>Xin chào, {actor.id}</h1>
        <p>Đây là tình hình tìm phòng của bạn hôm nay.</p>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {loading ? (
        <section className="panel">
          <LoadingState label="Đang tổng hợp tình hình của bạn…" />
        </section>
      ) : data ? (
        <>
          <div className="stat-grid overview-stats">
            {[
              ["Phòng đã xem", String(data.viewed.length), "eye"],
              ["Tin đã lưu", String(data.saved.length), "heart"],
              ["Lịch xem sắp tới", String(upcoming.length), "calendar"],
              ["Phiên trò chuyện", String(data.conversations.length), "chat"],
            ].map(([label, value, icon]) => (
              <div className="stat-card" key={label}>
                <span className="stat-icon">
                  <Icon name={icon} size={20} />
                </span>
                <div>
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              </div>
            ))}
          </div>
          <div className="overview-cols">
            <div className="overview-main">
              <section className="panel overview-need">
                <div className="section-heading">
                  <h2>
                    <Icon name="target" size={17} /> Nhu cầu trợ lý đang ghi nhớ
                  </h2>
                  <Link to="/tro-ly-ai" className="overview-more">
                    Chi tiết <Icon name="arrow" size={14} />
                  </Link>
                </div>
                {data.session ? (
                  <>
                    <p className="overview-need-text">
                      {needSummary(data.session)}
                    </p>
                    <small className="subtle">
                      Trợ lý tự rút ra từ cuộc trò chuyện — bạn sửa lại bất cứ
                      lúc nào trong màn trợ lý.
                    </small>
                  </>
                ) : (
                  <p className="subtle">
                    Chưa có nhu cầu nào. Mở trợ lý AI và mô tả chỗ ở bạn cần để
                    bắt đầu.
                  </p>
                )}
              </section>
              <section className="panel">
                <div className="section-heading">
                  <h2>
                    <Icon name="calendar" size={17} /> Lịch xem sắp tới
                  </h2>
                  <Link to="/nguoi-thue/lich-xem" className="overview-more">
                    Xem tất cả <Icon name="arrow" size={14} />
                  </Link>
                </div>
                {upcoming.length === 0 ? (
                  <p className="subtle">
                    Chưa có lịch xem nào. Trợ lý có thể đặt lịch giúp bạn ngay
                    trong lúc trò chuyện.
                  </p>
                ) : (
                  <div className="personal-list">
                    {upcoming.slice(0, 3).map((view) => (
                      <div className="personal-row" key={view.id}>
                        <div className="personal-row-main">
                          <Link
                            to={`/tin/${encodeURIComponent(view.room_id)}`}
                            className="personal-title"
                          >
                            {roomTitle(view.room_title ?? view.room_id)}
                          </Link>
                          <small>
                            {viewTime.format(new Date(view.requested_at))}
                            {view.time_slot &&
                              ` · ${
                                {
                                  morning: "Sáng",
                                  afternoon: "Chiều",
                                  evening: "Tối",
                                }[view.time_slot]
                              }`}
                            {view.mode === "online" && " · Xem trực tuyến"} ·{" "}
                            {viewingStatusLabels[view.status] ?? view.status}
                          </small>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
              <section className="panel">
                <div className="section-heading">
                  <h2>
                    <Icon name="eye" size={17} /> Phòng bạn đã xem gần đây
                  </h2>
                  <Link to="/nguoi-thue/phong-da-xem" className="overview-more">
                    Xem tất cả <Icon name="arrow" size={14} />
                  </Link>
                </div>
                {recentViewed.length === 0 ? (
                  <p className="subtle">
                    Chưa mở chi tiết căn nào. Lịch sử xem chỉ ghi khi bạn đăng
                    nhập.
                  </p>
                ) : (
                  <div className="personal-list">
                    {recentViewed.map((item) => (
                      <div
                        className="personal-row"
                        key={item.room_id ?? item.id}
                      >
                        <div className="personal-row-main">
                          <Link
                            to={`/tin/${encodeURIComponent(
                              item.room_id ?? item.id,
                            )}`}
                            className="personal-title"
                          >
                            {roomTitle(item.title)}
                          </Link>
                          <small>
                            {item.area} · {item.city}
                            {item.cost?.monthly_total_vnd != null &&
                              ` · tổng tháng ${money(item.cost.monthly_total_vnd)}`}
                          </small>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
            </div>
            <div className="overview-side">
              <section className="panel">
                <div className="section-heading">
                  <h2>
                    <Icon name="heart" size={17} /> Tin đã lưu
                  </h2>
                  <Link to="/nguoi-thue/da-luu" className="overview-more">
                    Tất cả <Icon name="arrow" size={14} />
                  </Link>
                </div>
                {data.saved.length === 0 ? (
                  <p className="subtle">
                    Chưa lưu tin nào. Bấm trái tim trên thẻ chỗ ở để giữ lại.
                  </p>
                ) : (
                  <div className="personal-list">
                    {data.saved.slice(0, 3).map((item) => (
                      <div
                        className="personal-row"
                        key={item.room_id ?? item.id}
                      >
                        <div className="personal-row-main">
                          <Link
                            to={`/tin/${encodeURIComponent(
                              item.room_id ?? item.id,
                            )}`}
                            className="personal-title"
                          >
                            {roomTitle(item.title)}
                          </Link>
                          <small>
                            {item.area} · {item.city}
                            {item.cost?.monthly_total_vnd != null &&
                              ` · tổng tháng ${money(item.cost.monthly_total_vnd)}`}
                          </small>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </section>
              {!data.activeLease && (
                <section className="panel overview-inactive">
                  <h2>Chưa kích hoạt</h2>
                  <p>
                    Hợp đồng, hóa đơn, chi phí sử dụng và yêu cầu sửa chữa sẽ
                    bật khi bạn thuê qua HomeMatch. Hiện chưa có dữ liệu thật
                    nên các trang đó đang để trống thay vì hiện số minh họa.
                  </p>
                  <ul>
                    <li>
                      <Icon name="contract" size={15} /> Hợp đồng — điều khoản,
                      thời hạn, cọc
                    </li>
                    <li>
                      <Icon name="wallet" size={15} /> Hóa đơn &amp; thanh toán
                      — sổ ghi hai phía
                    </li>
                    <li>
                      <Icon name="wrench" size={15} /> Yêu cầu sửa chữa — theo
                      dõi tiến độ
                    </li>
                  </ul>
                </section>
              )}
            </div>
          </div>
        </>
      ) : null}
    </>
  );
}
