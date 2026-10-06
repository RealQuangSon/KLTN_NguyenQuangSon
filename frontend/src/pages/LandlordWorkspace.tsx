import { useCallback, useEffect, useRef, useState } from "react";
import { Api, mutationKey } from "../api";
import type { Candidate, Recommendation, Room, Viewing } from "../types";
import {
  Badge,
  EmptyState,
  ErrorNotice,
  Icon,
  money,
  RoomCard,
  roomTitle,
} from "../components/Shared";
import { ViewingList } from "../components/ViewingPanel";
import { RoomEditor } from "../components/RoomEditor";
import { LoadingState } from "../components/LoadingState";
import { amenities, fees, occupancyLabels } from "../types";
export function LandlordWorkspace({ api, tab }: { api: Api; tab: string }) {
  const [queue, setQueue] = useState<Recommendation[]>([]),
    [detail, setDetail] = useState<Recommendation | null>(null),
    [rooms, setRooms] = useState<Room[]>([]),
    [viewings, setViewings] = useState<Viewing[]>([]),
    [selected, setSelected] = useState<string[]>([]),
    [reason, setReason] = useState(""),
    [order, setOrder] = useState<string[]>([]),
    [overrideReason, setOverrideReason] = useState(""),
    [error, setError] = useState<string | null>(null),
    [notice, setNotice] = useState<string | null>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(false),
    [editing, setEditing] = useState<Room | "new" | null>(null);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [openingId, setOpeningId] = useState<string | null>(null);
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
  const visibleQueue = queue.filter((run) =>
    normalize(
      `${run.session_id} ${run.profile.city} ${run.profile.area || ""}`,
    ).includes(normalize(query)),
  );
  useEffect(() => {
    setQuery("");
    setFilter("all");
    setOpeningId(null);
  }, [tab]);
  const live = useRef(true),
    lock = useRef(false),
    selectionRequest = useRef(0),
    attempt = useRef<{ signature: string; key: string } | null>(null),
    readMarker = useRef(0),
    currentTab = useRef(tab);
  currentTab.current = tab;
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      selectionRequest.current++;
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
      if (tab === "catalog") {
        const data = await api.get<{ rooms: Room[] }>("/landlord/rooms");
        if (fresh()) setRooms(data.rooms);
      } else if (tab === "viewings") {
        const data = await api.get<Viewing[]>("/viewings");
        if (fresh()) setViewings(data);
      } else {
        const data = await api.get<Recommendation[]>(
          "/landlord/recommendations",
        );
        if (fresh()) setQueue(data);
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
      selectionRequest.current++;
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
  const open = async (run: Recommendation) => {
    const marker = ++selectionRequest.current;
    setError(null);
    setOpeningId(run.run_id);
    setDetail(null);
    try {
      const value = await api.get<Recommendation>(
        `/landlord/recommendations/${run.run_id}`,
      );
      if (live.current && marker === selectionRequest.current) {
        setDetail(value);
        setSelected(value.items.map((x) => x.room_id));
        setOrder(value.items.map((x) => x.room_id));
        setReason("");
        setOverrideReason("");
        attempt.current = null;
      }
    } catch (err) {
      if (live.current && marker === selectionRequest.current)
        setError((err as Error).message);
    } finally {
      if (live.current && marker === selectionRequest.current)
        setOpeningId(null);
    }
  };
  // A landlord reviews once, while the shortlist is still awaiting landlord decisions.
  const canReview = (run: Recommendation) =>
    !run.decision &&
    ["pending_review", "partially_published"].includes(run.status);
  const agentOrder = detail ? detail.items.map((x) => x.room_id) : [];
  const keep = order.filter((id) => selected.includes(id));
  const overridden = keep.join("|") !== agentOrder.join("|");
  const move = (id: string, step: -1 | 1) =>
    setOrder((ids) => {
      const index = ids.indexOf(id);
      const target = index + step;
      if (index < 0 || target < 0 || target >= ids.length) return ids;
      const next = [...ids];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  const review = (decision: "approve" | "reject" | "needs_revision") =>
    mutate(async () => {
      if (!detail || !reason.trim()) {
        setError("Nhập lý do cho quyết định duyệt.");
        return;
      }
      if (decision === "approve" && !selected.length) {
        setError("Chọn ít nhất một phòng để duyệt.");
        return;
      }
      if (decision === "approve" && overridden && !overrideReason.trim()) {
        setError(
          "Bạn đã bỏ phòng hoặc đổi thứ tự so với trợ lý: hãy ghi lý do để bảo đảm không ưu tiên căn tồn.",
        );
        return;
      }
      const body = {
        decision,
        expected_profile_version: detail.profile_version,
        keep_room_ids: decision === "approve" ? keep : null,
        reason: reason.trim(),
        ...(decision === "approve" && overridden
          ? { override_reason: overrideReason.trim() }
          : {}),
      };
      const signature = JSON.stringify({ run_id: detail.run_id, ...body });
      if (attempt.current?.signature !== signature)
        attempt.current = { signature, key: mutationKey() };
      let next: Recommendation;
      try {
        next = await api.post<Recommendation>(
          `/landlord/recommendations/${detail.run_id}/review`,
          { ...body, idempotency_key: attempt.current.key },
        );
      } catch (error) {
        try {
          const actual = await api.get<Recommendation>(
            `/landlord/recommendations/${detail.run_id}`,
          );
          if (live.current && actual.status !== "pending_review")
            setDetail(actual);
          await latestRefresh.current();
        } catch {}
        throw error;
      }
      if (live.current) {
        setDetail(next);
        setNotice(
          next.status === "published"
            ? "Đã công bố đúng danh sách được duyệt cho người thuê."
            : "Quyết định đã được máy chủ ghi nhận.",
        );
        await latestRefresh.current();
      }
    });
  const retry = () =>
    mutate(async () => {
      if (!detail) return;
      const next = await api.post<Recommendation>(
        `/landlord/recommendations/${detail.run_id}/retry`,
        {},
      );
      if (live.current) {
        setDetail(next);
        setSelected(next.items.map((x) => x.room_id));
        setOrder(next.items.map((x) => x.room_id));
        setReason("");
        setOverrideReason("");
        attempt.current = null;
        setNotice(
          "Đã yêu cầu khôi phục có kiểm tra phiên bản. Bản mới vẫn cần duyệt.",
        );
        await latestRefresh.current();
      }
    });
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
            "Trạng thái phòng đã cập nhật. Các gợi ý có phòng này hết hiệu lực và cần duyệt lại.",
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
        : "Đã lưu tin. Các gợi ý cũ có phòng này cần duyệt lại.",
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
            {tab === "catalog"
              ? "Phòng & tin đăng"
              : tab === "viewings"
                ? "Lịch hẹn xem phòng"
                : "Duyệt phòng trước khi giới thiệu"}
          </h1>
          <p>
            {tab === "catalog"
              ? "Tạo, sửa tin và cập nhật tình trạng trống / đã cọc / đã thuê. Đổi tin làm gợi ý cũ hết hiệu lực."
              : tab === "viewings"
                ? "Chỉ xác nhận lịch khi thông tin phòng và bản gợi ý còn hiệu lực."
                : "Trợ lý gợi ý phòng của bạn cho khách; bạn duyệt phòng của mình trước khi khách thấy. Bạn không thấy thu nhập của khách."}
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
          : tab === "viewings"
            ? [
                {
                  label: "Yêu cầu xem",
                  value: viewings.length,
                  icon: "calendar",
                },
                {
                  label: "Đang chờ phản hồi",
                  value: viewings.filter((v) => v.status === "requested")
                    .length,
                  icon: "clock",
                },
                {
                  label: "Lịch đã xác nhận",
                  value: viewings.filter((v) => v.status === "confirmed")
                    .length,
                  icon: "check",
                },
              ]
            : [
                {
                  label: "Trong hàng đợi của bạn",
                  value: queue.length,
                  icon: "chat",
                },
                {
                  label: "Cần duyệt",
                  value: queue.filter((r) => r.status === "pending_review")
                    .length,
                  icon: "clock",
                },
                {
                  label: "Cần khôi phục",
                  value: queue.filter((r) =>
                    ["generation_failed", "generating_failed"].includes(
                      r.status,
                    ),
                  ).length,
                  icon: "refresh",
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
      {tab === "catalog" ? (
        <section className="panel">
          {editing && (
            <RoomEditor
              key={
                editing === "new" ? "new" : `${editing.id}:${editing.revision}`
              }
              room={editing === "new" ? null : editing}
              onSubmit={saveRoom}
              onCancel={() => setEditing(null)}
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
      ) : tab === "viewings" ? (
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
        <div className="review-layout">
          <section className="panel review-queue">
            <div className="section-heading">
              <h2>
                Chờ xử lý <span className="count">{queue.length}</span>
              </h2>
            </div>
            <label className="search-field queue-search">
              <Icon name="search" size={17} />
              <input
                type="search"
                aria-label="Tìm bản gợi ý"
                placeholder="Tìm phiên hoặc khu vực…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </label>
            {loading && !queue.length ? (
              <LoadingState label="Đang tải hàng đợi…" />
            ) : !visibleQueue.length ? (
              <EmptyState
                title={
                  queue.length
                    ? "Không có kết quả phù hợp"
                    : "Hàng đợi đang trống"
                }
                description={
                  queue.length
                    ? "Thử tìm bằng khu vực hoặc mã phiên khác."
                    : "Các gợi ý của khách được phân công sẽ xuất hiện sau khi khách xác nhận nhu cầu."
                }
                icon="shield"
              />
            ) : (
              visibleQueue.map((run) => (
                <button
                  className={`queue-item ${detail?.run_id === run.run_id || openingId === run.run_id ? "active" : ""}`}
                  key={run.run_id}
                  onClick={() => void open(run)}
                  disabled={busy}
                >
                  <div>
                    <strong>Phiên {run.session_id.slice(0, 8)}</strong>
                    <Badge status={run.status} />
                  </div>
                  <span>
                    {run.profile.city} ·{" "}
                    {run.profile.area || "Không giới hạn khu vực"}
                  </span>
                  <small>
                    {money(run.profile.max_monthly_cost_vnd)} / tháng ·{" "}
                    {run.items.length} lựa chọn · hồ sơ v{run.profile_version}
                  </small>
                  <Icon name="arrow" size={16} />
                </button>
              ))
            )}
          </section>
          <section className="panel review-detail">
            {openingId ? (
              <LoadingState label="Đang tải hồ sơ và gợi ý…" />
            ) : !detail ? (
              <EmptyState
                title="Chọn một bản gợi ý để kiểm tra"
                description="Bạn có thể rà nguồn, bảng phí và đánh đổi trước khi duyệt subset phù hợp."
                icon="shield"
              />
            ) : (
              <>
                <div className="section-heading">
                  <div>
                    <span className="eyebrow">
                      HỒ SƠ v{detail.profile_version}
                    </span>
                    <h2>Phiên {detail.session_id.slice(0, 8)}</h2>
                  </div>
                  <Badge status={detail.status} />
                </div>
                {detail.review_progress &&
                  detail.review_progress.landlords > 1 && (
                    <p className="input-hint">
                      Danh sách gồm phòng của {detail.review_progress.landlords}{" "}
                      chủ nhà; {detail.review_progress.decided} đã quyết định.
                      Bạn chỉ thấy và duyệt phòng của mình.
                    </p>
                  )}
                <div className="profile-facts">
                  <span>
                    {detail.profile.city} · {detail.profile.area}
                  </span>
                  <span>
                    {detail.profile.scenario.people} người ·{" "}
                    {detail.profile.scenario.vehicles} xe
                  </span>
                  <span>
                    Tổng tháng ≤ {money(detail.profile.max_monthly_cost_vnd)}
                  </span>
                  <span>
                    Tiền mặt vào ở {money(detail.profile.max_initial_cash_vnd)}
                  </span>
                  {detail.profile.loan && (
                    <span>
                      Chấp nhận vay {detail.profile.loan.term_months} tháng
                      {detail.profile.loan.max_principal_vnd
                        ? ` ≤ ${money(detail.profile.loan.max_principal_vnd)}`
                        : ""}
                    </span>
                  )}
                </div>
                <p className="input-hint">
                  Thu nhập của khách không hiển thị; mỗi phòng chỉ có mức đánh
                  giá khả năng chi trả.
                </p>
                <p className="subtle">
                  Bắt buộc:{" "}
                  {detail.profile.must_amenities
                    .map((key) => amenities[key] || key)
                    .join(", ") || "Không có tiện ích bắt buộc"}{" "}
                  · Kho phiên bản {detail.catalog_version.slice(0, 8)}
                </p>
                {Object.keys(detail.diagnostics?.verification ?? {}).length >
                  0 && (
                  <p className="notice warning">
                    Phòng chưa đủ thông tin trong lượt tìm:{" "}
                    {Object.entries(detail.diagnostics?.verification ?? {})
                      .map(
                        ([key, n]) =>
                          `${({ monthly_fees: "Phí hàng tháng", initial_fees: "Tiền ban đầu", required_amenity: "Tiện ích bắt buộc", availability: "Tình trạng còn phòng", destination: "Vị trí" } as Record<string, string>)[key] || key} (${n})`,
                      )
                      .join(", ")}
                  </p>
                )}
                <div className="review-items">
                  {order
                    .map((id) => detail.items.find((x) => x.room_id === id))
                    .filter((item): item is Candidate => Boolean(item))
                    .map((item, index) => (
                      <div key={item.room_id} className="review-item">
                        <div className="review-order">
                          <span>
                            Vị trí {index + 1} · trợ lý xếp #
                            {agentOrder.indexOf(item.room_id) + 1}
                          </span>
                          <button
                            type="button"
                            className="text-button"
                            aria-label={`Đưa ${roomTitle(item.title)} lên`}
                            onClick={() => move(item.room_id, -1)}
                            disabled={busy || index === 0 || !canReview(detail)}
                          >
                            ↑
                          </button>
                          <button
                            type="button"
                            className="text-button"
                            aria-label={`Đưa ${roomTitle(item.title)} xuống`}
                            onClick={() => move(item.room_id, 1)}
                            disabled={
                              busy ||
                              index === order.length - 1 ||
                              !canReview(detail)
                            }
                          >
                            ↓
                          </button>
                        </div>
                        <label className="checkbox-line">
                          <input
                            type="checkbox"
                            checked={selected.includes(item.room_id)}
                            onChange={() =>
                              setSelected((ids) =>
                                ids.includes(item.room_id)
                                  ? ids.filter((x) => x !== item.room_id)
                                  : [...ids, item.room_id],
                              )
                            }
                            disabled={busy || !canReview(detail)}
                          />
                          Đưa {roomTitle(item.title)} vào danh sách duyệt
                        </label>
                        <RoomCard item={item} />
                      </div>
                    ))}
                </div>
                {canReview(detail) && (
                  <form
                    className="review-form"
                    onSubmit={(e) => {
                      e.preventDefault();
                      void review("approve");
                    }}
                  >
                    <label>
                      Lý do quyết định
                      <textarea
                        required
                        minLength={1}
                        maxLength={1000}
                        rows={3}
                        placeholder="Đã kiểm tra nguồn, tổng phí và tiêu chí bắt buộc…"
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        disabled={busy}
                      />
                    </label>
                    {overridden && (
                      <label>
                        Lý do khác đề xuất của trợ lý
                        <textarea
                          required
                          maxLength={1000}
                          rows={2}
                          placeholder="Ví dụ: khách đã từ chối tòa này ở phiên trước…"
                          value={overrideReason}
                          onChange={(e) => setOverrideReason(e.target.value)}
                          disabled={busy}
                        />
                        <small className="input-hint">
                          Bạn đã bỏ phòng hoặc đổi thứ tự. Lý do được lưu cùng
                          quyết định để kiểm tra không ưu tiên căn tồn.
                        </small>
                      </label>
                    )}
                    <div className="form-actions">
                      <button
                        type="button"
                        className="button outline"
                        disabled={busy || !reason.trim()}
                        onClick={() => void review("needs_revision")}
                      >
                        Yêu cầu sửa
                      </button>
                      <button
                        type="button"
                        className="button outline"
                        disabled={busy || !reason.trim()}
                        onClick={() => void review("reject")}
                      >
                        Từ chối
                      </button>
                      <button
                        className="button"
                        disabled={busy || !selected.length || !reason.trim()}
                      >
                        <Icon name="check" size={17} />
                        Duyệt {selected.length} phòng
                      </button>
                    </div>
                  </form>
                )}
                {[
                  "reviewed",
                  "generation_failed",
                  "generating_failed",
                  "generating",
                ].includes(detail.status) && (
                  <div className="notice warning">
                    <span>
                      Khôi phục chỉ kiểm tra event đã ghi hoặc tạo run mới.
                      Không thừa kế duyệt cho nháp mới.
                    </span>
                    <button
                      className="button small outline"
                      disabled={busy}
                      onClick={() => void retry()}
                    >
                      Khôi phục có kiểm tra
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
