import { useCallback, useEffect, useRef, useState } from "react";
import { Api } from "../api";
import type { Room, Viewing } from "../types";
import {
  EmptyState,
  ErrorNotice,
  Icon,
  money,
  roomTitle,
} from "../components/Shared";
import { ViewingList } from "../components/ViewingPanel";
import { RoomEditor } from "../components/RoomEditor";
import { LoadingState } from "../components/LoadingState";
import { fees, occupancyLabels } from "../types";
export function LandlordWorkspace({
  api,
  tab,
  publishLocked = false,
}: {
  api: Api;
  tab: string;
  // FE-02: chủ nhà chưa được duyệt chỉ soạn tin được, không bật công khai.
  publishLocked?: boolean;
}) {
  const [rooms, setRooms] = useState<Room[]>([]),
    [viewings, setViewings] = useState<Viewing[]>([]),
    [error, setError] = useState<string | null>(null),
    [notice, setNotice] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [editing, setEditing] = useState<Room | "new" | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const normalize = (value: string) =>
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/đ/g, "d");
  const visibleRooms = rooms.filter(
    (room) =>
      normalize(`${room.id} ${room.title} ${room.city} ${room.area}`).includes(
        normalize(query),
      ) &&
      (filter === "all" ||
        (filter === "published" && room.published) ||
        (filter === "unpublished" && !room.published) ||
        (filter === "available" && room.available === true) ||
        (filter === "unavailable" && room.available === false) ||
        (filter === "unknown" && room.available === null)),
  );
  useEffect(() => {
    setQuery("");
    setFilter("all");
  }, [tab]);
  const live = useRef(true),
    lock = useRef(false),
    readMarker = useRef(0),
    currentTab = useRef(tab);
  currentTab.current = tab;
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      readMarker.current++;
    };
  }, []);
  const refresh = useCallback(async () => {
    const marker = ++readMarker.current;
    const scope = tab;
    const fresh = () =>
      live.current &&
      marker === readMarker.current &&
      scope === currentTab.current;
    setLoading(true);
    setError(null);
    try {
      if (tab === "viewings") {
        const data = await api.get<Viewing[]>("/viewings");
        if (fresh()) setViewings(data);
      } else {
        const data = await api.get<{ rooms: Room[] }>("/landlord/rooms");
        if (fresh()) setRooms(data.rooms);
      }
    } catch (err) {
      if (fresh()) setError((err as Error).message);
    } finally {
      if (fresh()) setLoading(false);
    }
  }, [api, tab]);
  const latestRefresh = useRef(refresh);
  latestRefresh.current = refresh;
  useEffect(() => {
    void refresh();
    return () => {
      readMarker.current++;
    };
  }, [refresh]);
  const mutate = async (action: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    readMarker.current++;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await action();
    } catch (err) {
      if (live.current) setError((err as Error).message);
    } finally {
      lock.current = false;
      if (live.current) setBusy(false);
    }
  };
  const roomStatus = (
    room: Room,
    patch: {
      published?: boolean;
      available?: boolean | null;
      occupancy?: string;
    },
  ) =>
    mutate(async () => {
      try {
        await api.patch(`/landlord/rooms/${room.id}/status`, {
          expected_revision: room.revision,
          ...patch,
        });
        if (live.current)
          setNotice(
            "Trạng thái phòng đã cập nhật. Các gợi ý có phòng này hết hiệu lực; khách xác nhận lại nhu cầu để tìm lại.",
          );
      } finally {
        if (live.current) await latestRefresh.current();
      }
    });
  const saveRoom = async (body: Record<string, unknown>) => {
    if (editing === "new") await api.post("/landlord/rooms", body);
    else if (editing) await api.put(`/landlord/rooms/${editing.id}`, body);
    if (!live.current) return;
    setNotice(
      editing === "new"
        ? "Đã tạo tin. Tin chỉ hiện với khách khi bạn bật công khai."
        : "Đã lưu tin. Các gợi ý cũ có phòng này hết hiệu lực.",
    );
    setEditing(null);
    await latestRefresh.current();
  };
  const respond = (id: string, status: "confirmed" | "declined") =>
    mutate(async () => {
      await api.post(`/landlord/viewings/${id}/respond`, { status });
      if (live.current) {
        setNotice(
          status === "confirmed"
            ? "Đã xác nhận thời gian xem."
            : "Đã phản hồi chưa chấp nhận lịch xem.",
        );
        await latestRefresh.current();
      }
    });
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">CỔNG CHỦ NHÀ</span>
          <h1>
            {tab === "catalog" ? "Phòng & tin đăng" : "Lịch hẹn xem phòng"}
          </h1>
          <p>
            {tab === "catalog"
              ? "Tạo, sửa tin và cập nhật tình trạng trống / đã cọc / đã thuê. Đổi tin làm gợi ý cũ hết hiệu lực."
              : "Chỉ xác nhận lịch khi thông tin phòng còn hiệu lực."}
          </p>
        </div>
        <button
          className="button outline small"
          onClick={() => void refresh()}
          disabled={loading || busy}
        >
          <Icon name="refresh" size={16} />
          {loading ? "Đang đọc…" : "Đọc lại"}
        </button>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {notice && (
        <div className="notice success" role="status">
          {notice}
        </div>
      )}
      <div
        className="workspace-stats"
        aria-label="Tổng quan"
        aria-busy={loading}
      >
        {(tab === "catalog"
          ? [
              { label: "Phòng trong kho", value: rooms.length, icon: "home" },
              {
                label: "Tin đã duyệt",
                value: rooms.filter((r) => r.published).length,
                icon: "shield",
              },
              {
                label: "Đã xác minh còn phòng",
                value: rooms.filter((r) => r.available === true).length,
                icon: "check",
              },
            ]
          : [
              {
                label: "Yêu cầu xem",
                value: viewings.length,
                icon: "calendar",
              },
              {
                label: "Đang chờ phản hồi",
                value: viewings.filter((v) => v.status === "requested").length,
                icon: "clock",
              },
              {
                label: "Lịch đã xác nhận",
                value: viewings.filter((v) => v.status === "confirmed").length,
                icon: "check",
              },
            ]
        ).map((stat) => (
          <div className="stat-card" key={stat.label}>
            <span className="stat-icon">
              <Icon name={stat.icon} size={21} />
            </span>
            <div>
              <span>{stat.label}</span>
              <strong>{loading ? "—" : stat.value}</strong>
            </div>
          </div>
        ))}
      </div>
      {tab === "viewings" ? (
        <section className="panel">
          {loading && !viewings.length ? (
            <LoadingState label="Đang tải lịch xem phòng…" />
          ) : (
            <ViewingList
              items={viewings}
              manager
              busy={busy}
              onRespond={(id, status) => void respond(id, status)}
            />
          )}
        </section>
      ) : (
        <section className="panel">
          {editing && (
            <RoomEditor
              key={
                editing === "new" ? "new" : `${editing.id}:${editing.revision}`
              }
              api={api}
              room={editing === "new" ? null : editing}
              onSubmit={saveRoom}
              onCancel={() => setEditing(null)}
              publishLocked={publishLocked}
            />
          )}
          <div className="section-heading">
            <h2>
              Phòng của bạn <span className="count">{rooms.length}</span>
            </h2>
            <button
              className="button small"
              onClick={() => setEditing("new")}
              disabled={busy}
            >
              <Icon name="home" size={15} /> Thêm phòng
            </button>
          </div>
          <div className="catalog-toolbar">
            <label className="search-field">
              <Icon name="search" size={18} />
              <input
                type="search"
                aria-label="Tìm trong kho phòng"
                placeholder="Tìm tên phòng, khu vực hoặc mã phòng…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            <select
              aria-label="Lọc kho phòng"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="all">Tất cả trạng thái</option>
              <option value="published">Tin đã duyệt</option>
              <option value="unpublished">Tin chưa duyệt</option>
              <option value="available">Còn phòng</option>
              <option value="unavailable">Hết phòng</option>
              <option value="unknown">Chưa xác minh</option>
            </select>
            <small>
              {visibleRooms.length}/{rooms.length} phòng
            </small>
          </div>
          {loading && !rooms.length ? (
            <LoadingState label="Đang tải kho phòng…" />
          ) : (
            <>
              <div className="table-scroll">
                <table className="catalog-table">
                  <thead>
                    <tr>
                      <th>Phòng / nguồn</th>
                      <th>Tiền thuê</th>
                      <th>Phí</th>
                      <th>Công khai</th>
                      <th>Tình trạng</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRooms.map((room) => (
                      <tr key={room.id}>
                        <td>
                          <strong>{roomTitle(room.title)}</strong>
                          <button
                            className="text-button"
                            onClick={() => setEditing(room)}
                            disabled={busy}
                            aria-label={`Sửa ${room.id}`}
                          >
                            Sửa
                          </button>
                          <small>
                            {room.area} · {room.area_m2} m² · v{room.revision}
                          </small>
                          <details className="catalog-source">
                            <summary>Mô tả & nguồn</summary>
                            {roomTitle(room.title) !== room.title && (
                              <p>{room.title}</p>
                            )}
                            <small className="source-text">
                              {room.source}
                              {room.synthetic ? " · giả lập" : ""}
                            </small>
                          </details>
                        </td>
                        <td>
                          {money(room.quote.rent_vnd)}
                          <small>Cọc: {money(room.quote.deposit_vnd)}</small>
                        </td>
                        <td>
                          <details>
                            <summary>
                              {room.quote.fees.length} khoản · xem đơn vị
                            </summary>
                            <ul className="catalog-fees">
                              {room.quote.fees.map((f) => (
                                <li key={f.name}>
                                  {fees[f.name] || f.name}:{" "}
                                  {f.included_in_rent
                                    ? "Đã gồm thuê"
                                    : f.amount_vnd === null
                                      ? "Chưa biết"
                                      : money(Number(f.amount_vnd))}{" "}
                                  / {f.mode}
                                  <small>{f.source}</small>
                                </li>
                              ))}
                            </ul>
                          </details>
                        </td>
                        <td>
                          <button
                            className={`toggle ${room.published ? "on" : ""}`}
                            aria-label={`${room.published ? "Ẩn tin" : "Duyệt tin"} ${room.id}`}
                            aria-pressed={room.published}
                            disabled={busy}
                            onClick={() =>
                              void roomStatus(room, {
                                published: !room.published,
                              })
                            }
                          >
                            <span />
                            {room.published ? "Đã duyệt" : "Chưa duyệt"}
                          </button>
                        </td>
                        <td>
                          <select
                            aria-label={`Tình trạng ${room.id}`}
                            value={
                              room.available === null
                                ? "unknown"
                                : room.occupancy ||
                                  (room.available ? "vacant" : "rented")
                            }
                            onChange={(e) =>
                              void roomStatus(
                                room,
                                e.target.value === "unknown"
                                  ? { available: null }
                                  : { occupancy: e.target.value },
                              )
                            }
                            disabled={busy}
                          >
                            <option value="unknown">Chưa xác minh</option>
                            {Object.entries(occupancyLabels).map(
                              ([id, label]) => (
                                <option key={id} value={id}>
                                  {label}
                                </option>
                              ),
                            )}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {!visibleRooms.length && !loading && (
                <EmptyState
                  title={
                    rooms.length
                      ? "Chưa có phòng khớp bộ lọc"
                      : "Chưa có phòng trong kho"
                  }
                  description={
                    rooms.length
                      ? "Thử đổi từ khóa hoặc chọn tất cả trạng thái để xem lại kho phòng."
                      : "Kho phòng sẽ xuất hiện sau khi dữ liệu được nhập vào hệ thống."
                  }
                />
              )}
            </>
          )}
        </section>
      )}
    </>
  );
}
