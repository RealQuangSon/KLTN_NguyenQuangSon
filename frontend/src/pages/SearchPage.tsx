import { useCallback, useEffect, useMemo, useState } from "react";
import type { Api } from "../api";
import type { Cost, Room, RoomType } from "../types";
import { amenities, fees, occupancyLabels, roomTypeLabels } from "../types";
import { cityAreas } from "../locations";
import {
  CostBreakdown,
  EmptyState,
  ErrorNotice,
  Icon,
  money,
  roomTitle,
} from "../components/Shared";
import { MapView } from "../components/MapView";
import { AdviceBox, type Advice } from "../components/Advice";
import { ViewingForm } from "../components/ViewingPanel";
import { LoadingState } from "../components/LoadingState";
import { openConversation } from "./Inbox";
// Tìm theo bộ lọc (Filter-based Search): tin đã được chủ nhà công khai, không
// cần chờ duyệt danh sách. Danh sách và bản đồ dùng cùng kết quả; khung xem
// nhanh bên cạnh cho chi tiết, nội quy và hỏi đáp cẩm nang của từng phòng.
type Listing = Room & { cost: Cost };
type Detail = Listing & { house_rules?: string | null };
interface Filters {
  city: string;
  area: string;
  room_type: "" | RoomType;
  min_rent: string;
  max_rent: string;
  max_monthly: string;
  min_area_m2: string;
  min_bedrooms: string;
  people: string;
  amenities: string[];
  sort: string;
}
const initial: Filters = {
  city: "TP.HCM",
  area: "",
  room_type: "",
  min_rent: "",
  max_rent: "",
  max_monthly: "",
  min_area_m2: "",
  min_bedrooms: "",
  people: "1",
  amenities: [],
  sort: "monthly_asc",
};
const query = (filters: Filters, page: number) => {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (key === "amenities")
      (value as string[]).forEach((item) => params.append("amenities", item));
    else if (value !== "") params.set(key, String(value));
  }
  params.set("page", String(page));
  params.set("page_size", "12");
  return params.toString();
};
export function SearchPage({ api }: { api: Api }) {
  const [filters, setFilters] = useState<Filters>(initial);
  const [applied, setApplied] = useState<Filters>(initial);
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<{
    total: number;
    items: Listing[];
  } | null>(null);
  const [view, setView] = useState<"list" | "map">("list");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<{
    items: Listing[];
    advice: Advice;
  } | null>(null);
  const [booking, setBooking] = useState<Listing | null>(null);
  const [question, setQuestion] = useState("");
  const [handbook, setHandbook] = useState<{
    answers: { id: string; title: string; answer: string }[];
    house_rules: string[];
    disclaimer: string;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setResult(await api.get(`/listings?${query(applied, page)}`));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [api, applied, page]);
  useEffect(() => {
    void load();
  }, [load]);
  const set = <K extends keyof Filters>(key: K, value: Filters[K]) =>
    setFilters((f) => ({ ...f, [key]: value }));
  const open = async (id: string) => {
    setError(null);
    setHandbook(null);
    setQuestion("");
    try {
      setDetail(
        await api.get<Detail>(`/listings/${id}?people=${applied.people || 1}`),
      );
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const toggle = (id: string) =>
    setSelected((ids) =>
      ids.includes(id)
        ? ids.filter((x) => x !== id)
        : ids.length >= 3
          ? ids
          : [...ids, id],
    );
  const compare = async () => {
    setError(null);
    try {
      setComparison(
        await api.post("/listings/compare", {
          room_ids: selected,
          people: Number(applied.people) || 1,
          budget: applied.max_monthly ? Number(applied.max_monthly) : null,
          preferences: applied.amenities,
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const ask = async () => {
    if (!detail || !question.trim()) return;
    try {
      setHandbook(
        await api.post("/handbook/ask", { question, room_id: detail.id }),
      );
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const pins = useMemo(
    () =>
      (result?.items ?? []).map((item) => ({
        ...item,
        monthly: item.cost.monthly_total_vnd,
      })),
    [result],
  );
  const pages = result ? Math.max(1, Math.ceil(result.total / 12)) : 1;
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">TÌM THEO BỘ LỌC</span>
          <h1>Tìm phòng, studio, căn hộ</h1>
          <p>
            Tin do chủ nhà công khai. Chi phí là ước tính theo số người bạn
            chọn; khoản chưa rõ không tính là 0.
          </p>
        </div>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {notice && (
        <div className="notice success" role="status">
          {notice}
        </div>
      )}
      <form
        className="panel search-filters"
        aria-label="Bộ lọc tìm kiếm"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          setSelected([]);
          setComparison(null);
          setApplied(filters);
        }}
      >
        <div className="form-grid four">
          <label>
            Thành phố
            <select
              value={filters.city}
              onChange={(e) => set("city", e.target.value)}
            >
              <option value="">Tất cả</option>
              {Object.keys(cityAreas).map((city) => (
                <option key={city}>{city}</option>
              ))}
            </select>
          </label>
          <label>
            Khu vực
            <input
              list="search-area-options"
              value={filters.area}
              placeholder="Ví dụ: Q7, Cầu Giấy"
              onChange={(e) => set("area", e.target.value)}
            />
            <datalist id="search-area-options">
              {(cityAreas[filters.city] || []).map((area) => (
                <option key={area} value={area} />
              ))}
            </datalist>
          </label>
          <label>
            Loại
            <select
              value={filters.room_type}
              onChange={(e) => set("room_type", e.target.value as RoomType)}
            >
              <option value="">Tất cả</option>
              {Object.entries(roomTypeLabels).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Số người
            <input
              type="number"
              min={1}
              max={20}
              value={filters.people}
              onChange={(e) => set("people", e.target.value)}
            />
          </label>
          <label>
            Giá thuê từ (đ)
            <input
              type="number"
              min={0}
              value={filters.min_rent}
              onChange={(e) => set("min_rent", e.target.value)}
            />
          </label>
          <label>
            Giá thuê đến (đ)
            <input
              type="number"
              min={0}
              value={filters.max_rent}
              onChange={(e) => set("max_rent", e.target.value)}
            />
          </label>
          <label>
            Tổng tháng tối đa (đ)
            <input
              type="number"
              min={0}
              value={filters.max_monthly}
              onChange={(e) => set("max_monthly", e.target.value)}
            />
          </label>
          <label>
            Diện tích từ (m²)
            <input
              type="number"
              min={0}
              value={filters.min_area_m2}
              onChange={(e) => set("min_area_m2", e.target.value)}
            />
          </label>
          {filters.room_type === "apartment" && (
            <label>
              Phòng ngủ từ
              <input
                type="number"
                min={1}
                max={5}
                value={filters.min_bedrooms}
                onChange={(e) => set("min_bedrooms", e.target.value)}
              />
            </label>
          )}
          <label>
            Sắp xếp
            <select
              value={filters.sort}
              onChange={(e) => set("sort", e.target.value)}
            >
              <option value="monthly_asc">Tổng tháng thấp → cao</option>
              <option value="monthly_desc">Tổng tháng cao → thấp</option>
              <option value="rent_asc">Giá thuê thấp → cao</option>
              <option value="area_desc">Diện tích lớn → nhỏ</option>
            </select>
          </label>
        </div>
        <div className="chip-row" role="group" aria-label="Tiện nghi bắt buộc">
          {Object.entries(amenities).map(([id, label]) => (
            <button
              type="button"
              key={id}
              className={
                filters.amenities.includes(id) ? "choice active" : "choice"
              }
              aria-pressed={filters.amenities.includes(id)}
              onClick={() =>
                set(
                  "amenities",
                  filters.amenities.includes(id)
                    ? filters.amenities.filter((x) => x !== id)
                    : [...filters.amenities, id],
                )
              }
            >
              {label}
            </button>
          ))}
        </div>
        <div className="form-actions">
          <button
            type="button"
            className="button outline"
            onClick={() => {
              setFilters(initial);
              setApplied(initial);
              setPage(1);
            }}
          >
            Xóa bộ lọc
          </button>
          <button className="button">
            <Icon name="search" size={16} /> Tìm
          </button>
        </div>
      </form>
      <div className="search-layout">
        <section className="panel">
          <div className="section-heading">
            <h2>
              Kết quả <span className="count">{result?.total ?? 0}</span>
            </h2>
            <div className="segmented" role="group" aria-label="Chế độ xem">
              <button
                className={view === "list" ? "choice active" : "choice"}
                aria-pressed={view === "list"}
                onClick={() => setView("list")}
              >
                Danh sách
              </button>
              <button
                className={view === "map" ? "choice active" : "choice"}
                aria-pressed={view === "map"}
                onClick={() => setView("map")}
              >
                Bản đồ
              </button>
            </div>
          </div>
          {loading && !result ? (
            <LoadingState label="Đang tìm phòng…" />
          ) : !result?.items.length ? (
            <EmptyState
              title="Chưa có tin phù hợp"
              description="Thử bỏ bớt tiện nghi bắt buộc, mở rộng khu vực hoặc tăng ngân sách."
              icon="search"
            />
          ) : view === "map" ? (
            <MapView
              pins={pins}
              selectedId={detail?.id}
              onSelect={(id) => void open(id)}
            />
          ) : (
            <div className="listing-grid">
              {result.items.map((item) => (
                <article
                  className={`listing-card ${detail?.id === item.id ? "selected" : ""}`}
                  key={item.id}
                >
                  <span className="eyebrow">
                    {item.area} · {item.city} ·{" "}
                    {roomTypeLabels[item.room_type ?? "room"]}
                    {item.bedrooms ? ` ${item.bedrooms}PN` : ""}
                  </span>
                  <h3>{roomTitle(item.title)}</h3>
                  <p>
                    <strong>{money(item.cost.monthly_total_vnd)}</strong>
                    /tháng (ước tính) · thuê {money(item.quote.rent_vnd)} ·{" "}
                    {item.area_m2} m²
                  </p>
                  <small>
                    {item.occupancy
                      ? occupancyLabels[item.occupancy]
                      : item.available
                        ? "Còn trống"
                        : "Chưa xác minh tình trạng"}
                    {item.synthetic ? " · dữ liệu giả lập" : ""}
                  </small>
                  <div className="room-actions">
                    <button
                      className="text-button"
                      onClick={() => void open(item.id)}
                    >
                      Xem nhanh
                    </button>
                    <button
                      className={`button small ${selected.includes(item.id) ? "secondary" : "outline"}`}
                      aria-pressed={selected.includes(item.id)}
                      onClick={() => toggle(item.id)}
                      disabled={
                        !selected.includes(item.id) && selected.length >= 3
                      }
                    >
                      {selected.includes(item.id) ? "Đã chọn" : "So sánh"}
                    </button>
                    <button
                      className="button small"
                      onClick={() => setBooking(item)}
                    >
                      Đặt lịch xem
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
          {result && result.total > 12 && (
            <div className="form-actions">
              <button
                className="button outline small"
                disabled={page <= 1}
                onClick={() => setPage(page - 1)}
              >
                Trang trước
              </button>
              <span>
                Trang {page}/{pages}
              </span>
              <button
                className="button outline small"
                disabled={page >= pages}
                onClick={() => setPage(page + 1)}
              >
                Trang sau
              </button>
            </div>
          )}
          {selected.length > 0 && (
            <div className="compare-bar">
              <span>
                Đã chọn <strong>{selected.length}/3</strong> phòng
              </span>
              <button
                className="button"
                disabled={selected.length < 2}
                onClick={() => void compare()}
              >
                <Icon name="compare" size={17} /> So sánh & tư vấn
              </button>
            </div>
          )}
        </section>
        <aside className="panel quick-preview" aria-label="Xem nhanh">
          {!detail ? (
            <EmptyState
              title="Chọn một tin để xem nhanh"
              description="Chi tiết phí, nội quy của chủ nhà và hỏi đáp cẩm nang hiện ở đây."
              icon="home"
            />
          ) : (
            <>
              <span className="eyebrow">
                {detail.area} · {detail.city}
              </span>
              <h2>{roomTitle(detail.title)}</h2>
              {detail.features_text && <p>{detail.features_text}</p>}
              <CostBreakdown cost={detail.cost} />
              <h3>Nội quy & cách tính phí của chủ nhà</h3>
              <p>{detail.house_rules || "Chủ nhà chưa cung cấp nội quy."}</p>
              <ul className="catalog-fees">
                {detail.quote.fees.map((fee) => (
                  <li key={fee.name}>
                    {fees[fee.name] || fee.name}:{" "}
                    {fee.included_in_rent
                      ? "đã gồm trong tiền thuê"
                      : fee.amount_vnd == null
                        ? "chưa rõ"
                        : `${money(Number(fee.amount_vnd))} / ${fee.mode}`}
                  </li>
                ))}
              </ul>
              <form
                className="handbook-ask"
                onSubmit={(e) => {
                  e.preventDefault();
                  void ask();
                }}
              >
                <label>
                  Hỏi cẩm nang về phòng này
                  <input
                    value={question}
                    placeholder="Ví dụ: gửi xe thế nào? có hoàn cọc không?"
                    onChange={(e) => setQuestion(e.target.value)}
                  />
                </label>
                <button className="button small outline">Hỏi</button>
              </form>
              {handbook && (
                <div className="handbook-answer">
                  {handbook.house_rules.length > 0 && (
                    <p>
                      <strong>Theo nội quy chủ nhà:</strong>{" "}
                      {handbook.house_rules.join(" ")}
                    </p>
                  )}
                  {handbook.answers.map((entry) => (
                    <p key={entry.id}>
                      <strong>{entry.title}:</strong> {entry.answer}
                    </p>
                  ))}
                  {!handbook.answers.length && !handbook.house_rules.length && (
                    <p>Chưa có mục phù hợp; hãy hỏi trực tiếp chủ nhà.</p>
                  )}
                  <small>{handbook.disclaimer}</small>
                </div>
              )}
              <div className="form-actions">
                <button
                  className="button outline"
                  onClick={async () => {
                    try {
                      const conversation = await api.post<{ id: string }>(
                        "/conversations",
                        { room_id: detail.id },
                      );
                      openConversation(conversation.id, "/tin-nhan");
                    } catch (err) {
                      setError((err as Error).message);
                    }
                  }}
                >
                  <Icon name="chat" size={16} /> Chat với chủ nhà
                </button>
                <button className="button" onClick={() => setBooking(detail)}>
                  <Icon name="calendar" size={16} /> Đặt lịch xem
                </button>
              </div>
            </>
          )}
        </aside>
      </div>
      {comparison && (
        <section className="panel comparison">
          <div className="section-heading">
            <div>
              <span className="eyebrow">SO SÁNH & TƯ VẤN</span>
              <h2>So sánh các tin đã chọn</h2>
            </div>
            <button className="text-button" onClick={() => setComparison(null)}>
              Đóng so sánh
            </button>
          </div>
          <AdviceBox advice={comparison.advice} />
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Tiêu chí</th>
                  {comparison.items.map((item) => (
                    <th key={item.id}>{roomTitle(item.title)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>Tổng tháng</th>
                  {comparison.items.map((item) => (
                    <td key={item.id}>{money(item.cost.monthly_total_vnd)}</td>
                  ))}
                </tr>
                <tr>
                  <th>Tiền vào ở</th>
                  {comparison.items.map((item) => (
                    <td key={item.id}>{money(item.cost.initial_total_vnd)}</td>
                  ))}
                </tr>
                <tr>
                  <th>Diện tích</th>
                  {comparison.items.map((item) => (
                    <td key={item.id}>{item.area_m2} m²</td>
                  ))}
                </tr>
                <tr>
                  <th>Tiện nghi</th>
                  {comparison.items.map((item) => (
                    <td key={item.id}>
                      {Object.entries(item.amenities)
                        .filter(([, value]) => value === true)
                        .map(([key]) => amenities[key] || key)
                        .join(", ") || "Chưa rõ"}
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      )}
      {booking && (
        <ViewingForm
          room={{
            room_id: booking.id,
            title: booking.title,
            area: booking.area,
          }}
          sessionId={null}
          api={api}
          onCancel={() => setBooking(null)}
          onDone={() => {
            setBooking(null);
            setNotice(
              "Đã gửi yêu cầu xem phòng. Lịch chỉ được xác nhận khi chủ nhà phản hồi; theo dõi ở mục Lịch xem.",
            );
          }}
        />
      )}
    </>
  );
}
