import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../api";
import type { Api } from "../api";
import type {
  CostMetrics,
  LandlordApplication,
  Room,
  SupportTicket,
  TicketStatus,
} from "../types";
import { roleNames, ticketStatusLabels } from "../types";
import {
  EmptyState,
  ErrorNotice,
  Icon,
  money,
  roomTitle,
} from "../components/Shared";
import { Link } from "../router";
// Admin Console: giám sát hội thoại AI (đã che PII, mỗi lần mở được ghi audit),
// đánh giá chuyển giao AI → chủ nhà, người dùng, duyệt hồ sơ chủ nhà (FE-02),
// ticket hỗ trợ (FE-03), kiểm duyệt tin và vận hành kèm chi phí AI (FE-04).
export type AdminSection =
  | "hoi-thoai"
  | "chuyen-giao"
  | "ho-tro"
  | "tai-khoan"
  | "tin-dang"
  | "van-hanh";
// FE-03: link "phiên" trong màn ho-tro mở đúng phiên ở section hoi-thoai.
export const OPEN_ADMIN_SESSION_KEY = "homematch.admin.openSession";
const titles: Record<AdminSection, [string, string]> = {
  "hoi-thoai": [
    "Giám sát hội thoại AI",
    "Lịch sử chat giữa trợ lý và người dùng, đã che số điện thoại, email, số tài khoản. Lưu tối đa 90 ngày; mỗi lần mở được ghi audit.",
  ],
  "chuyen-giao": [
    "Chuyển giao AI → chủ nhà",
    "Tỷ lệ phản hồi và thời gian phản hồi đầu tiên của từng chủ nhà sau khi khách chuyển sang live chat.",
  ],
  "ho-tro": ["Yêu cầu hỗ trợ", "Khách muốn gặp người thật"],
  "tai-khoan": [
    "Người dùng & vai trò",
    "Vai trò do máy chủ cấp; trạng thái tài khoản; duyệt hồ sơ chủ nhà chờ xác minh.",
  ],
  "tin-dang": [
    "Kiểm duyệt tin đăng",
    "Toàn bộ tin của các chủ nhà; quản trị viên có thể ẩn tin sai hoặc vi phạm.",
  ],
  "van-hanh": [
    "Vận hành",
    "Số liệu tiến trình hiện tại, chi phí AI theo bảng giá máy chủ và các bản gợi ý tạo lỗi cần khởi tạo lại.",
  ],
};
interface TranscriptRow {
  session_id: string;
  user_id: string;
  turns: number;
  started_at: string;
  last_at: string;
  flagged: number;
}
interface Turn {
  speaker: string;
  text: string;
  intent: string | null;
  agent: string | null;
  created_at: string;
}
interface HandoverReport {
  landlords: {
    landlord_id: string;
    conversations: number;
    answered: number;
    response_rate: number;
    median_response_minutes: number | null;
  }[];
}
interface UserRow {
  id: string;
  role: keyof typeof roleNames;
  status: string;
  display_name: string | null;
}
interface FailedRun {
  run_id: string;
  session_id: string;
  status: string;
}
// HN-05: lượt agent đọc từ hm_agent_turns qua /admin/agent-turns.
interface AgentTurn {
  turn_id: string;
  session_id: string;
  started_at: string;
  duration_ms: number;
  agent_mode: string | null;
  llm_calls: number;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  decided_by: string | null;
  outcome: string;
  error_code: string | null;
}
interface AgentTurnsReport {
  turns: AgentTurn[];
  count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  fallback_ratio: number | null;
  cost_usd: number;
  cost_usd_per_day: number;
}
const time = (value: string) =>
  new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
const dateOnly = (value: string) =>
  new Intl.DateTimeFormat("vi-VN").format(new Date(value));
// FE-04: ngày hiệu lực bảng giá; máy chủ trả null khi chưa có. Chuỗi ngày ISO
// được định dạng trực tiếp để không lệch múi giờ khi hiển thị dd/mm/yyyy.
const priceDate = (value: string | null) => {
  if (!value) return "không rõ ngày";
  const iso = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : new Intl.DateTimeFormat("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      }).format(parsed);
};
const ticketFilters: { id: "all" | TicketStatus; label: string }[] = [
  { id: "all", label: "Tất cả" },
  { id: "requested", label: "Chờ xử lý" },
  { id: "in_progress", label: "Đang xử lý" },
  { id: "resolved", label: "Đã giải quyết" },
];
// Hộp thoại nhập lý do/ghi chú bắt buộc: giữ focus bên trong và đóng bằng
// Escape, theo đúng mẫu của ViewingPanel.tsx.
function ReasonDialog({
  eyebrow,
  title,
  description,
  fieldLabel,
  confirmLabel,
  maxLength,
  value,
  busy,
  error,
  onChange,
  onConfirm,
  onClose,
}: {
  eyebrow: string;
  title: string;
  description: string;
  fieldLabel: string;
  confirmLabel: string;
  maxLength: number;
  value: string;
  busy: boolean;
  error: string | null;
  onChange: (value: string) => void;
  onConfirm: (trimmed: string) => Promise<void>;
  onClose: () => void;
}) {
  const panel = useRef<HTMLElement>(null);
  const close = useRef(onClose);
  const submitting = useRef(busy);
  close.current = onClose;
  submitting.current = busy;
  useEffect(() => {
    const el = panel.current;
    const previous = document.activeElement as HTMLElement | null;
    el?.querySelector<HTMLTextAreaElement>("textarea")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!submitting.current) close.current();
      }
      if (event.key !== "Tab" || !el) return;
      const targets = [
        ...el.querySelectorAll<HTMLElement>(
          "button:not(:disabled), textarea:not(:disabled), input:not(:disabled), [tabindex='0']",
        ),
      ];
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (!first) {
        event.preventDefault();
        el.focus();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    el?.addEventListener("keydown", onKeyDown);
    return () => {
      el?.removeEventListener("keydown", onKeyDown);
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  const trimmed = value.trim();
  const valid = trimmed.length >= 1 && trimmed.length <= maxLength;
  return (
    <div className="modal-backdrop">
      <section
        className="panel modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reason-dialog-title"
        ref={panel}
        tabIndex={-1}
      >
        <button
          type="button"
          className="icon-button modal-close"
          aria-label="Đóng hộp thoại"
          onClick={onClose}
          disabled={busy}
        >
          <Icon name="close" size={19} />
        </button>
        <span className="eyebrow">{eyebrow}</span>
        <h2 id="reason-dialog-title">{title}</h2>
        <p>{description}</p>
        <ErrorNotice error={error} />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!valid) return;
            void onConfirm(trimmed);
          }}
          noValidate
        >
          <label>
            {fieldLabel}
            <textarea
              rows={3}
              maxLength={maxLength}
              value={value}
              onChange={(e) => onChange(e.target.value)}
              disabled={busy}
            />
          </label>
          <small className="input-hint">
            Bắt buộc, {trimmed.length}/{maxLength} ký tự.
          </small>
          <div className="form-actions">
            <button
              type="button"
              className="button outline"
              onClick={onClose}
              disabled={busy}
            >
              Hủy
            </button>
            <button className="button" disabled={busy || !valid}>
              {confirmLabel}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
export function AdminWorkspace({
  api,
  section,
}: {
  api: Api;
  section: AdminSection;
}) {
  const [error, setError] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<TranscriptRow[]>([]);
  const [turns, setTurns] = useState<{
    session_id: string;
    turns: Turn[];
  } | null>(null);
  const [handovers, setHandovers] = useState<HandoverReport | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [failed, setFailed] = useState<FailedRun[]>([]);
  const [agentTurns, setAgentTurns] = useState<AgentTurnsReport | null>(null);
  // FE-02: hồ sơ chủ nhà chờ duyệt.
  const [applications, setApplications] = useState<LandlordApplication[]>([]);
  const [rejectTarget, setRejectTarget] = useState<LandlordApplication | null>(
    null,
  );
  const [rejectReason, setRejectReason] = useState("");
  const [rejectError, setRejectError] = useState<string | null>(null);
  const [rejectBusy, setRejectBusy] = useState(false);
  // FE-03: ticket hỗ trợ.
  const [tickets, setTickets] = useState<SupportTicket[]>([]);
  const [ticketFilter, setTicketFilter] = useState<"all" | TicketStatus>("all");
  const [resolveTarget, setResolveTarget] = useState<SupportTicket | null>(
    null,
  );
  const [resolveNote, setResolveNote] = useState("");
  const [resolveError, setResolveError] = useState<string | null>(null);
  const [resolveBusy, setResolveBusy] = useState(false);
  const load = useCallback(async () => {
    setError(null);
    try {
      if (section === "hoi-thoai") {
        setTranscripts(await api.get("/admin/transcripts"));
        // Link "phiên" từ màn ho-tro đặt phiên cần mở vào sessionStorage
        // (không đưa session vào URL); mở xong thì xóa để F5 không mở lại.
        const target = sessionStorage.getItem(OPEN_ADMIN_SESSION_KEY);
        if (target) {
          sessionStorage.removeItem(OPEN_ADMIN_SESSION_KEY);
          setTurns(await api.get(`/admin/transcripts/${target}`));
        }
      } else if (section === "chuyen-giao")
        setHandovers(await api.get("/admin/handovers"));
      else if (section === "ho-tro")
        setTickets(await api.get("/admin/support-tickets"));
      else if (section === "tai-khoan") {
        setUsers(await api.get("/admin/users"));
        setApplications(
          await api.get("/admin/landlord-applications?status=pending"),
        );
      } else if (section === "tin-dang")
        setRooms((await api.get<{ rooms: Room[] }>("/admin/rooms")).rooms);
      else {
        setMetrics(await api.get("/admin/metrics"));
        setFailed(await api.get("/admin/failed-runs"));
        setAgentTurns(await api.get("/admin/agent-turns"));
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, [api, section]);
  useEffect(() => {
    setTurns(null);
    void load();
  }, [load]);
  const act = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  // FE-03: đổi trạng thái ticket. 409 ticket_state nghĩa là ai đó đã đổi trước:
  // đọc lại danh sách rồi mới hiện thông báo (load() đặt lại error).
  const ticketAction = async (
    ticket: SupportTicket,
    body: { status: TicketStatus; note?: string },
  ) => {
    setError(null);
    try {
      await api.patch(`/admin/support-tickets/${ticket.id}`, body);
    } catch (err) {
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        err.code === "ticket_state"
      )
        await load();
      setError((err as Error).message);
      return;
    }
    await load();
  };
  const visibleTickets = tickets.filter(
    (ticket) => ticketFilter === "all" || ticket.status === ticketFilter,
  );
  // FE-04: chi phí AI do máy chủ trả về; FE chỉ định dạng số và ngày, không tính.
  const cost = (metrics?.cost ?? null) as CostMetrics | null;
  const [title, description] = titles[section];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADMIN CONSOLE</span>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <button className="button outline small" onClick={() => void load()}>
          <Icon name="refresh" size={16} /> Đọc lại
        </button>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {section === "hoi-thoai" && (
        <div className="inbox-layout">
          <section className="panel inbox-list" aria-label="Phiên chat">
            {transcripts.length === 0 && (
              <EmptyState
                title="Chưa có hội thoại"
                description="Hội thoại với trợ lý sẽ xuất hiện tại đây."
                icon="chat"
              />
            )}
            {transcripts.map((row) => (
              <button
                key={row.session_id}
                className={`queue-item ${turns?.session_id === row.session_id ? "active" : ""}`}
                onClick={() =>
                  void act(async () =>
                    setTurns(
                      await api.get(`/admin/transcripts/${row.session_id}`),
                    ),
                  )
                }
              >
                <div>
                  <strong>{row.user_id}</strong>
                  {row.flagged > 0 && (
                    <span className="badge">{row.flagged} bị chặn</span>
                  )}
                </div>
                <span>
                  {row.turns} lượt · {time(row.last_at)}
                </span>
              </button>
            ))}
          </section>
          <section
            className="panel inbox-thread"
            aria-label="Nội dung hội thoại"
          >
            {!turns ? (
              <EmptyState
                title="Chọn một phiên"
                description="Việc mở nội dung sẽ được ghi vào nhật ký kiểm toán."
                icon="shield"
              />
            ) : (
              <div className="message-list">
                {turns.turns.map((turn, index) => (
                  <div
                    key={index}
                    className={`chat-bubble ${turn.speaker === "user" ? "theirs" : "mine"}`}
                  >
                    <p>{turn.text}</p>
                    <small>
                      {turn.speaker === "user"
                        ? "Người dùng"
                        : `Trợ lý${turn.agent ? ` · ${turn.agent}` : ""}`}{" "}
                      · {time(turn.created_at)}
                    </small>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
      {section === "chuyen-giao" && (
        <section className="panel">
          {!handovers?.landlords.length ? (
            <EmptyState
              title="Chưa có chuyển giao"
              description="Khi khách chuyển sang chat với chủ nhà, số liệu xuất hiện tại đây."
              icon="chat"
            />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Chủ nhà</th>
                    <th>Cuộc trò chuyện</th>
                    <th>Đã phản hồi</th>
                    <th>Tỷ lệ phản hồi</th>
                    <th>Phản hồi đầu tiên (trung vị)</th>
                  </tr>
                </thead>
                <tbody>
                  {handovers.landlords.map((row) => (
                    <tr key={row.landlord_id}>
                      <td>{row.landlord_id}</td>
                      <td>{row.conversations}</td>
                      <td>{row.answered}</td>
                      <td>{Math.round(row.response_rate * 100)}%</td>
                      <td>
                        {row.median_response_minutes == null
                          ? "Chưa phản hồi"
                          : `${row.median_response_minutes} phút`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {section === "ho-tro" && (
        <section className="panel">
          <div
            className="chip-row"
            role="group"
            aria-label="Lọc theo trạng thái"
          >
            {ticketFilters.map((filter) => (
              <button
                key={filter.id}
                className={
                  ticketFilter === filter.id
                    ? "button small"
                    : "button small outline"
                }
                aria-pressed={ticketFilter === filter.id}
                onClick={() => setTicketFilter(filter.id)}
              >
                {filter.label}
              </button>
            ))}
          </div>
          {tickets.length === 0 ? (
            <EmptyState
              title="Chưa có yêu cầu hỗ trợ"
              description="Khi khách bấm gặp người thật trong hội thoại, ticket xuất hiện tại đây."
              icon="chat"
            />
          ) : visibleTickets.length === 0 ? (
            <p className="subtle">Không có ticket ở trạng thái này.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Thời điểm</th>
                    <th>Phiên</th>
                    <th>Trạng thái</th>
                    <th>Người xử lý</th>
                    <th>Ghi chú</th>
                    <th>Hành động</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleTickets.map((ticket) => (
                    <tr key={ticket.id}>
                      <td>{time(ticket.created_at)}</td>
                      <td>
                        <Link
                          to="/quan-tri/hoi-thoai"
                          onClick={() =>
                            sessionStorage.setItem(
                              OPEN_ADMIN_SESSION_KEY,
                              ticket.session_id,
                            )
                          }
                          aria-label={`Mở phiên ${ticket.session_id.slice(0, 8)} trong hội thoại AI`}
                        >
                          {ticket.session_id.slice(0, 8)}
                        </Link>
                      </td>
                      <td>{ticketStatusLabels[ticket.status]}</td>
                      <td>{ticket.assignee || "Chưa có"}</td>
                      <td>{ticket.note || "—"}</td>
                      <td>
                        {ticket.status === "requested" && (
                          <button
                            className="button small"
                            onClick={() =>
                              void ticketAction(ticket, {
                                status: "in_progress",
                              })
                            }
                          >
                            Nhận xử lý
                          </button>
                        )}
                        {ticket.status !== "resolved" && (
                          <button
                            className="button outline small"
                            onClick={() => {
                              setResolveNote("");
                              setResolveError(null);
                              setResolveTarget(ticket);
                            }}
                          >
                            Đã giải quyết
                          </button>
                        )}
                        {ticket.status === "resolved" && (
                          <button
                            className="button outline small"
                            onClick={() =>
                              void ticketAction(ticket, {
                                status: "in_progress",
                              })
                            }
                          >
                            Mở lại
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {section === "tai-khoan" && (
        <>
          <section className="panel" aria-label="Chủ nhà chờ duyệt">
            <div className="section-heading">
              <h2>
                Chủ nhà chờ duyệt{" "}
                <span className="count">{applications.length}</span>
              </h2>
            </div>
            {applications.length === 0 ? (
              <p className="subtle">Không có chủ nhà chờ duyệt.</p>
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Chủ nhà</th>
                      <th>Email</th>
                      <th>Đã xác minh email</th>
                      <th>Ngày đăng ký</th>
                      <th>Hành động</th>
                    </tr>
                  </thead>
                  <tbody>
                    {applications.map((app) => (
                      <tr key={app.user_id}>
                        <td>{app.display_name || app.user_id}</td>
                        <td>{app.email}</td>
                        <td>
                          {app.verified ? "Đã xác minh" : "Chưa xác minh"}
                        </td>
                        <td>{dateOnly(app.created_at)}</td>
                        <td>
                          <button
                            className="button small"
                            onClick={() =>
                              void act(() =>
                                api.post(
                                  `/admin/landlord-applications/${app.user_id}/approve`,
                                ),
                              )
                            }
                          >
                            Duyệt
                          </button>
                          <button
                            className="button outline small"
                            onClick={() => {
                              setRejectReason("");
                              setRejectError(null);
                              setRejectTarget(app);
                            }}
                          >
                            Từ chối
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
          <section className="panel table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Tài khoản</th>
                  <th>Vai trò</th>
                  <th>Trạng thái</th>
                </tr>
              </thead>
              <tbody>
                {users.map((user) => (
                  <tr key={user.id}>
                    <td>{user.display_name || user.id}</td>
                    <td>{roleNames[user.role] || user.role}</td>
                    <td>{user.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      )}
      {section === "tin-dang" && (
        <section className="panel table-scroll">
          <table>
            <thead>
              <tr>
                <th>Tin</th>
                <th>Chủ nhà</th>
                <th>Giá thuê</th>
                <th>Công khai</th>
              </tr>
            </thead>
            <tbody>
              {rooms.map((room) => (
                <tr key={room.id}>
                  <td>
                    {roomTitle(room.title)}
                    <small>
                      {room.area} · {room.city}
                    </small>
                  </td>
                  <td>{room.landlord_id || "owner-a"}</td>
                  <td>{money(room.quote.rent_vnd)}</td>
                  <td>
                    <button
                      className="text-button"
                      aria-label={`${room.published ? "Ẩn" : "Hiện"} tin ${room.id}`}
                      onClick={() =>
                        void act(() =>
                          api.patch(`/admin/rooms/${room.id}/status`, {
                            expected_revision: room.revision,
                            published: !room.published,
                          }),
                        )
                      }
                    >
                      {room.published
                        ? "Đang hiện · Ẩn tin"
                        : "Đang ẩn · Hiện lại"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {section === "van-hanh" && (
        <>
          <section className="panel" aria-label="Chi phí AI ước tính">
            <h2>Chi phí AI ước tính</h2>
            {cost && cost.estimated_cost_vnd ? (
              <p>
                ≈{" "}
                {new Intl.NumberFormat("vi-VN").format(cost.estimated_cost_vnd)}{" "}
                đ (bảng giá ngày {priceDate(cost.price_effective_date)})
              </p>
            ) : (
              // Khoản chưa biết là null, không bao giờ hiển thị 0.
              <p className="subtle">
                Chưa tính được
                {cost?.missing?.length
                  ? ` — thiếu: ${cost.missing.join(", ")}`
                  : ""}
              </p>
            )}
          </section>
          <section className="panel" aria-label="Lượt agent gần đây">
            <h2>Lượt agent gần đây</h2>
            {agentTurns === null ? (
              <p className="subtle">Chưa tải được dữ liệu lượt agent.</p>
            ) : agentTurns.count === 0 ? (
              <p className="subtle">Chưa có lượt agent nào được ghi.</p>
            ) : (
              <>
                <p className="subtle">
                  {`${agentTurns.count} lượt · p50 ${new Intl.NumberFormat(
                    "vi-VN",
                  ).format(
                    agentTurns.p50_ms ?? 0,
                  )} ms · p95 ${new Intl.NumberFormat("vi-VN").format(
                    agentTurns.p95_ms ?? 0,
                  )} ms · fallback ${(
                    (agentTurns.fallback_ratio ?? 0) * 100
                  ).toFixed(1)}% · chi phí ${
                    agentTurns.cost_usd > 0
                      ? `$${agentTurns.cost_usd.toFixed(6)}/ngày`
                      : "chưa báo"
                  }`}
                </p>
                <table>
                  <thead>
                    <tr>
                      <th>Thời điểm</th>
                      <th>Phiên</th>
                      <th>Chế độ</th>
                      <th>ms</th>
                      <th>LLM</th>
                      <th>Token (vào/ra)</th>
                      <th>Kết quả</th>
                    </tr>
                  </thead>
                  <tbody>
                    {agentTurns.turns.map((turn) => (
                      <tr key={turn.turn_id}>
                        <td>{time(turn.started_at)}</td>
                        <td>{turn.session_id.slice(0, 8)}</td>
                        <td>{turn.agent_mode ?? "graph"}</td>
                        <td>
                          {new Intl.NumberFormat("vi-VN").format(
                            turn.duration_ms,
                          )}
                        </td>
                        <td>{turn.llm_calls}</td>
                        <td>
                          {turn.input_tokens === null
                            ? "chưa báo"
                            : `${turn.input_tokens}/${turn.output_tokens ?? 0}`}
                        </td>
                        <td>
                          {turn.outcome}
                          {turn.error_code ? ` · ${turn.error_code}` : ""}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>
          <section className="panel">
            <h2>Bản gợi ý tạo lỗi</h2>
            {failed.length === 0 ? (
              <p className="subtle">Không có bản gợi ý lỗi.</p>
            ) : (
              <ul className="memory-list">
                {failed.map((run) => (
                  <li key={run.run_id}>
                    <span>
                      Phiên {run.session_id.slice(0, 8)} · {run.status}
                    </span>
                    <button
                      className="text-button"
                      onClick={() =>
                        void act(() =>
                          api.post(
                            `/admin/failed-runs/${run.run_id}/retry`,
                            {},
                          ),
                        )
                      }
                    >
                      Khởi tạo lại
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <h2>Số liệu tiến trình</h2>
            <pre className="metrics-dump">
              {metrics ? JSON.stringify(metrics, null, 2) : "—"}
            </pre>
          </section>
        </>
      )}
      {rejectTarget && (
        <ReasonDialog
          eyebrow="DUYỆT CHỦ NHÀ"
          title="Từ chối hồ sơ chờ duyệt"
          description={`${rejectTarget.display_name || rejectTarget.user_id} · ${rejectTarget.email}`}
          fieldLabel="Lý do từ chối"
          confirmLabel="Từ chối hồ sơ"
          maxLength={500}
          value={rejectReason}
          busy={rejectBusy}
          error={rejectError}
          onChange={setRejectReason}
          onConfirm={async (reason) => {
            setRejectBusy(true);
            setRejectError(null);
            try {
              await api.post(
                `/admin/landlord-applications/${rejectTarget.user_id}/reject`,
                { reason },
              );
              setRejectTarget(null);
              await load();
            } catch (err) {
              setRejectError((err as Error).message);
            } finally {
              setRejectBusy(false);
            }
          }}
          onClose={() => setRejectTarget(null)}
        />
      )}
      {resolveTarget && (
        <ReasonDialog
          eyebrow="YÊU CẦU HỖ TRỢ"
          title="Đánh dấu đã giải quyết"
          description={`Phiên ${resolveTarget.session_id.slice(0, 8)}`}
          fieldLabel="Ghi chú cách xử lý"
          confirmLabel="Xác nhận đã giải quyết"
          maxLength={1000}
          value={resolveNote}
          busy={resolveBusy}
          error={resolveError}
          onChange={setResolveNote}
          onConfirm={async (note) => {
            setResolveBusy(true);
            setResolveError(null);
            try {
              await api.patch(`/admin/support-tickets/${resolveTarget.id}`, {
                status: "resolved",
                note,
              });
              setResolveTarget(null);
              await load();
            } catch (err) {
              setResolveError((err as Error).message);
            } finally {
              setResolveBusy(false);
            }
          }}
          onClose={() => setResolveTarget(null)}
        />
      )}
    </>
  );
}
