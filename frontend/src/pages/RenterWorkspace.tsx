import { useCallback, useEffect, useRef, useState } from "react";
import { Api, ApiError } from "../api";
import { visibleStatuses } from "../types";
import type {
  Actor,
  Candidate,
  Profile,
  Results,
  Session,
  Viewing,
} from "../types";
import {
  Badge,
  Comparison,
  EmptyState,
  ErrorNotice,
  Icon,
  PublishedResults,
} from "../components/Shared";
import { ProfileForm } from "../components/ProfileForm";
import { SimulationPanel } from "../components/Simulation";
import type { Advice } from "../components/Advice";
import { openConversation } from "./Inbox";
import { ViewingForm, ViewingList } from "../components/ViewingPanel";
import { Journey } from "../components/Journey";
import { RoomIllustration } from "../components/RoomIllustration";
import { LoadingState } from "../components/LoadingState";
type Message = { role: "user" | "assistant"; text: string };
export function RenterWorkspace({
  api,
  actor,
  tab,
  initialNeed = null,
  onNeedHandled,
}: {
  api: Api;
  actor: Actor;
  tab: string;
  initialNeed?: string | null;
  onNeedHandled?: () => void;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [result, setResult] = useState<Results | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Candidate[] | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [viewRoom, setViewRoom] = useState<Candidate | null>(null);
  const [simRoom, setSimRoom] = useState<Candidate | null>(null);
  const [viewings, setViewings] = useState<Viewing[]>([]);
  const [editing, setEditing] = useState(false);
  const [restoring, setRestoring] = useState(() =>
    Boolean(sessionStorage.getItem(`homematch.session.${actor.id}`)),
  );
  const [viewsLoading, setViewsLoading] = useState(false);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const messageList = useRef<HTMLDivElement>(null);
  const viewsMarker = useRef(0);
  const needHandled = useRef(false);
  const live = useRef(true),
    epoch = useRef(0),
    current = useRef<string | null>(null),
    lock = useRef(false),
    readMarker = useRef(0),
    resultRef = useRef(result);
  resultRef.current = result;
  useEffect(() => {
    const list = messageList.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages, busy]);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      epoch.current++;
    };
  }, []);
  const apply = useCallback(
    (value: Session) => {
      current.current = value.session_id;
      setSession(value);
      sessionStorage.setItem(`homematch.session.${actor.id}`, value.session_id);
    },
    [actor.id],
  );
  const loadViews = useCallback(async () => {
    const e = epoch.current;
    const marker = ++viewsMarker.current;
    setViewsLoading(true);
    try {
      const rows = await api.get<Viewing[]>("/viewings");
      if (live.current && e === epoch.current && marker === viewsMarker.current)
        setViewings(rows);
    } catch (err) {
      if (live.current && e === epoch.current && marker === viewsMarker.current)
        setError((err as Error).message);
    } finally {
      if (live.current && marker === viewsMarker.current)
        setViewsLoading(false);
    }
  }, [api]);
  const refresh = useCallback(async () => {
    const sid = current.current;
    if (!sid) return;
    const e = epoch.current;
    const marker = ++readMarker.current;
    setLoading(true);
    try {
      const next = await api.get<Results>(`/sessions/${sid}/results`);
      if (
        live.current &&
        e === epoch.current &&
        current.current === sid &&
        marker === readMarker.current
      ) {
        const old = resultRef.current;
        if (
          old?.run_id !== next.run_id ||
          old?.status !== next.status ||
          !visibleStatuses.includes(next.status)
        ) {
          setSelected([]);
          setComparison(null);
          setViewRoom(null);
          setSimRoom(null);
        }
        setResult(next);
      }
    } catch (err) {
      if (live.current && e === epoch.current) setError((err as Error).message);
    } finally {
      if (live.current && e === epoch.current && marker === readMarker.current)
        setLoading(false);
    }
  }, [api]);
  useEffect(() => {
    const sid = sessionStorage.getItem(`homematch.session.${actor.id}`);
    if (!sid) return;
    let cancelled = false;
    const version = epoch.current;
    api
      .get<Session>(`/sessions/${sid}`)
      .then((s) => {
        if (!cancelled && live.current && version === epoch.current) apply(s);
      })
      .catch((err) => {
        if (!cancelled && live.current && version === epoch.current) {
          sessionStorage.removeItem(`homematch.session.${actor.id}`);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled && live.current && version === epoch.current)
          setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, actor.id, apply]);
  useEffect(() => {
    if (!session) return;
    void refresh();
  }, [session?.session_id, session?.active_run_id, refresh]);
  useEffect(() => {
    if (
      !["pending_review", "reviewed", "generating"].includes(
        result?.status || "",
      )
    )
      return;
    let ticks = 0;
    const timer = setInterval(() => {
      if (++ticks > 60) {
        clearInterval(timer);
        return;
      }
      if (!lock.current && document.visibilityState !== "hidden")
        void refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [result?.status, result?.run_id, refresh]);
  useEffect(() => {
    if (tab === "viewings") void loadViews();
  }, [tab, loadViews]);
  const mutate = async (action: () => Promise<void>) => {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      if (live.current) {
        setError((err as Error).message);
        if (
          err instanceof ApiError &&
          (err.status === 409 || err.status === 0) &&
          current.current
        ) {
          const sid = current.current;
          try {
            const s = await api.get<Session>(`/sessions/${sid}`);
            if (live.current && sid === current.current) apply(s);
            await refresh();
          } catch {
            /* Preserve original failure. Read-only recovery can be retried manually. */
          }
        }
      }
      return false;
    } finally {
      lock.current = false;
      if (live.current) setBusy(false);
    }
  };
  const create = () =>
    mutate(async () => {
      epoch.current++;
      setRestoring(false);
      current.current = null;
      setResult(null);
      setSelected([]);
      setComparison(null);
      setViewRoom(null);
      setSimRoom(null);
      const s = await api.post<Session>("/sessions");
      if (live.current) {
        apply(s);
        setMessages([
          {
            role: "assistant",
            text: "Bạn muốn tìm phòng ở đâu, cho bao nhiêu người và tổng ngân sách mỗi tháng là bao nhiêu?",
          },
        ]);
        setEditing(false);
      }
    });
  const sendText = (content: string) =>
    mutate(async () => {
      const sid = current.current;
      const value = content.trim();
      if (!sid || !value) return;
      const response = await api.post<Session>(`/sessions/${sid}/messages`, {
        text: value,
      });
      if (live.current && current.current === sid) {
        apply(response);
        setMessages((m) => [
          ...m,
          { role: "user", text: value },
          {
            role: "assistant",
            text:
              (response.answers?.length || response.house_rules?.length
                ? [
                    ...(response.house_rules || []),
                    ...(response.answers || []).map(
                      (entry) => `${entry.title}: ${entry.answer}`,
                    ),
                    response.disclaimer || "",
                  ]
                    .filter(Boolean)
                    .join("\n\n")
                : "") ||
              response.message ||
              response.questions?.join("\n") ||
              "Nhu cầu đã được ghi vào nháp. Kiểm tra biểu mẫu và xác nhận để tiếp tục.",
          },
        ]);
      }
    });
  const send = async () => {
    const content = text.trim();
    if (!content) return;
    if (await sendText(content)) setText("");
  };
  // Nhu cầu khách chia sẻ trên trang chủ: mở phiên mới rồi gửi ngay câu đầu
  // tiên; nếu đã có phiên đang mở thì chỉ điền sẵn để khách quyết định gửi.
  useEffect(() => {
    if (!initialNeed || needHandled.current || restoring) return;
    needHandled.current = true;
    onNeedHandled?.();
    const need = initialNeed;
    if (sessionStorage.getItem(`homematch.session.${actor.id}`)) {
      setText(need);
      messageInput.current?.focus();
      return;
    }
    void (async () => {
      if (await create()) await sendText(need);
    })();
    // Chạy một lần sau khi việc khôi phục phiên kết thúc.
  }, [restoring]);
  const confirm = (profile: Profile) =>
    mutate(async () => {
      if (!session) return;
      epoch.current++;
      setResult(null);
      setComparison(null);
      setSelected([]);
      setViewRoom(null);
      setSimRoom(null);
      const sid = session.session_id;
      const response = await api.post<Results>(`/sessions/${sid}/confirm`, {
        expected_draft_revision: session.draft_revision,
        profile,
      });
      const updated = await api.get<Session>(`/sessions/${sid}`);
      if (live.current && current.current === sid) {
        apply(updated);
        setResult(response);
        setEditing(false);
      }
    });
  const save = (
    values: Parameters<React.ComponentProps<typeof ProfileForm>["onSave"]>[0],
  ) =>
    mutate(async () => {
      if (!session) return;
      const sid = session.session_id;
      const s = await api.patch<Session>(`/sessions/${sid}/draft`, {
        expected_draft_revision: session.draft_revision,
        set: values,
        clear_fields: [],
        remove_preferences: [],
      });
      if (live.current && sid === current.current) {
        apply(s);
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: "Đã lưu điều chỉnh nháp. Ngân sách và kịch bản chỉ được xác nhận khi bạn chọn “Xác nhận & tìm phòng”.",
          },
        ]);
      }
    });
  const toggle = (id: string) => {
    setError(null);
    setComparison(null);
    setSelected((ids) => {
      if (ids.includes(id)) return ids.filter((x) => x !== id);
      if (ids.length >= 3) {
        setError(
          "Bạn chỉ có thể so sánh tối đa 3 phòng. Bỏ một lựa chọn để thêm phòng khác.",
        );
        return ids;
      }
      return [...ids, id];
    });
  };
  // Live chat with the room's landlord, carrying this session's context (smart handover).
  const chat = async (item: Candidate) => {
    if (!session) return;
    try {
      const conversation = await api.post<{ id: string }>("/conversations", {
        room_id: item.room_id,
        session_id: session.session_id,
      });
      openConversation(conversation.id, "/tin-nhan");
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const compare = () =>
    mutate(async () => {
      if (!session || selected.length < 2) return;
      const sid = session.session_id;
      const version = epoch.current;
      const output = await api.post<{
        run_id: string;
        items: Candidate[];
        advice?: Advice | null;
      }>(`/sessions/${sid}/compare`, { room_ids: selected });
      if (
        live.current &&
        sid === current.current &&
        version === epoch.current &&
        output.run_id === result?.run_id
      ) {
        setComparison(output.items);
        setAdvice(output.advice ?? null);
      }
    });
  if (tab === "viewings")
    return (
      <>
        <div className="page-heading">
          <span className="eyebrow">THỜI GIAN DÀNH CHO NƠI Ở MỚI</span>
          <h1>Lịch xem phòng</h1>
          <p>
            Đề xuất của bạn được quản lý xác nhận trước khi trở thành lịch hẹn.
          </p>
        </div>
        <ErrorNotice error={error} onClose={() => setError(null)} />
        <section className="panel">
          <div className="section-heading">
            <h2>Yêu cầu của bạn</h2>
            <button
              className="button outline small"
              onClick={() => void loadViews()}
              disabled={viewsLoading}
            >
              <Icon name="refresh" size={16} />
              Đọc lại
            </button>
          </div>
          {viewsLoading && !viewings.length ? (
            <LoadingState label="Đang tải lịch xem phòng…" />
          ) : (
            <ViewingList items={viewings} />
          )}
        </section>
      </>
    );
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">MỘT NƠI Ở. NHIỀU ĐIỀU PHÙ HỢP.</span>
          <h1>Nhà mới, vừa với cuộc sống.</h1>
          <p>Chia sẻ nhu cầu. Hiểu rõ chi phí. Tìm một nơi bạn muốn trở về.</p>
        </div>
        {session && (
          <button
            className="button outline small"
            onClick={() => void create()}
            disabled={busy}
          >
            Phiên mới
          </button>
        )}
      </div>
      <Journey
        step={
          !session
            ? 0
            : editing ||
                !session.confirmed_profile ||
                ["invalidated", "needs_revision", "no_match"].includes(
                  result?.status || "",
                )
              ? 1
              : visibleStatuses.includes(result?.status ?? "")
                ? 3
                : 2
        }
      />
      <div className="trust-strip">
        <span>
          <Icon name="shield" size={17} />
          Quản lý duyệt trước khi giới thiệu
        </span>
        <span>
          <Icon name="check" size={17} />
          Chi phí theo kịch bản của bạn
        </span>
        <span className="demo-label">Kho phòng giả lập · KLTN</span>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {restoring ? (
        <section className="panel">
          <LoadingState label="Đang khôi phục phiên tư vấn…" />
        </section>
      ) : !session ? (
        <section className="panel welcome">
          <div className="welcome-copy">
            <span className="welcome-tag">
              <Icon name="sparkles" size={16} /> Trợ lý tìm phòng của bạn
            </span>
            <span className="eyebrow">BẮT ĐẦU TỪ MỘT CUỘC TRÒ CHUYỆN</span>
            <h2>Nơi ở tiếp theo của bạn cần điều gì?</h2>
            <p>
              Gần trường, có cửa sổ, đủ yên tĩnh hay tổng chi phí dưới một mức
              nhất định? HomeMatch giúp bạn làm rõ từng điều.
            </p>
            <button
              className="button"
              onClick={() => void create()}
              disabled={busy}
            >
              Bắt đầu phiên tư vấn <Icon name="arrow" size={18} />
            </button>
            <div className="welcome-footnote">
              <Icon name="clock" size={14} /> Bắt đầu với khu vực, ngân sách và
              điều bạn ưu tiên.
            </div>
          </div>
          <div className="welcome-art">
            <RoomIllustration />
            <span>Không gian minh họa</span>
          </div>
        </section>
      ) : (
        <div className="workspace-grid">
          <div className="workspace-main">
            <section className="panel chat-panel">
              <div className="section-heading">
                <div className="agent-heading">
                  <div className="agent-avatar">
                    <Icon name="sparkles" size={22} />
                  </div>
                  <div>
                    <h2>Trợ lý HomeMatch</h2>
                    <span>Cùng bạn tìm một nơi ở phù hợp</span>
                  </div>
                </div>
                <span className="badge muted">
                  {session.session_id.slice(0, 8)}
                </span>
              </div>
              <div
                className="chat-messages"
                aria-live="polite"
                ref={messageList}
              >
                {messages.length === 0 ? (
                  <p className="subtle">
                    Bạn có thể tiếp tục chia sẻ nhu cầu. Nội dung hội thoại
                    không được lưu trên trình duyệt sau khi đăng xuất.
                  </p>
                ) : (
                  messages.map((m, i) => (
                    <div className={`chat-message ${m.role}`} key={i}>
                      <span>
                        {m.role === "assistant" ? "HomeMatch" : "Bạn"}
                      </span>
                      <p>{m.text}</p>
                    </div>
                  ))
                )}
                {busy && (
                  <div className="chat-typing" role="status">
                    <span aria-hidden="true">•••</span> Trợ lý đang xử lý…
                  </div>
                )}
              </div>
              {messages.length <= 1 && (
                <div className="chat-suggestions" aria-label="Gợi ý bắt đầu">
                  <span>Bạn có thể bắt đầu với</span>
                  {[
                    {
                      label: "Có cửa sổ",
                      text: "Tôi muốn phòng có cửa sổ, thoáng sáng",
                    },
                    {
                      label: "Yên tĩnh",
                      text: "Tôi muốn phòng yên tĩnh, phù hợp học tập",
                    },
                    {
                      label: "Gần trường",
                      text: "Tôi cần phòng gần nơi học tập",
                    },
                  ].map((suggestion) => (
                    <button
                      type="button"
                      key={suggestion.label}
                      disabled={busy}
                      onClick={() => {
                        setText(suggestion.text);
                        messageInput.current?.focus();
                      }}
                    >
                      {suggestion.label}
                      <Icon name="arrow" size={12} />
                    </button>
                  ))}
                </div>
              )}
              <form
                className="chat-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  void send();
                }}
              >
                <label className="visually-hidden" htmlFor="message">
                  Nhu cầu của bạn
                </label>
                <textarea
                  id="message"
                  ref={messageInput}
                  rows={2}
                  maxLength={2000}
                  placeholder="Ví dụ: studio Quận 7 TP.HCM có cửa sổ, hoặc căn hộ 2PN Thanh Xuân, Hà Nội…"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  disabled={busy}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      if (!busy && text.trim()) void send();
                    }
                  }}
                />
                <button
                  className="button icon-button"
                  disabled={busy || !text.trim()}
                  aria-label="Gửi nhu cầu"
                >
                  <Icon name="arrow" />
                </button>
              </form>
              <p className="input-hint">
                Enter để gửi · Shift + Enter để xuống dòng. Ngân sách được xác
                nhận trong hồ sơ.
              </p>
            </section>
            <section className="panel results-panel">
              <div className="section-heading">
                <div>
                  <span className="eyebrow">ÍT LỰA CHỌN HƠN. PHÙ HỢP HƠN.</span>
                  <h2>Gợi ý dành cho bạn</h2>
                </div>
                <div className="inline-actions">
                  {result && <Badge status={result.status} />}
                  <button
                    className="button outline small"
                    onClick={() => void refresh()}
                    disabled={loading || busy}
                  >
                    <Icon name="refresh" size={16} />
                    {loading ? "Đang đọc…" : "Đọc lại"}
                  </button>
                </div>
              </div>
              {loading && !result ? (
                <LoadingState label="Đang kiểm tra trạng thái gợi ý…" />
              ) : editing && visibleStatuses.includes(result?.status ?? "") ? (
                <EmptyState
                  title="Bạn đang điều chỉnh nhu cầu"
                  description="Xác nhận hồ sơ mới để tìm và duyệt lại. Gợi ý trước thuộc kịch bản đã xác nhận trước đó."
                  icon="chat"
                />
              ) : (
                <PublishedResults
                  result={result}
                  selected={selected}
                  onSelect={toggle}
                  onViewing={setViewRoom}
                  onSimulate={setSimRoom}
                  onChat={(item) => void chat(item)}
                />
              )}{" "}
              {!editing &&
                result &&
                visibleStatuses.includes(result.status) &&
                result.results.length > 1 && (
                  <div className="compare-bar">
                    <span>
                      Đã chọn <strong>{selected.length}/3</strong> phòng
                    </span>
                    <button
                      className="button"
                      disabled={selected.length < 2 || busy}
                      onClick={() => void compare()}
                    >
                      <Icon name="compare" size={17} />
                      So sánh lựa chọn
                    </button>
                  </div>
                )}
            </section>
            {comparison && !editing && (
              <Comparison
                items={comparison}
                advice={advice}
                onClose={() => setComparison(null)}
              />
            )}
            {simRoom &&
              !editing &&
              visibleStatuses.includes(result?.status ?? "") &&
              session.confirmed_profile && (
                <SimulationPanel
                  key={simRoom.room_id}
                  room={simRoom}
                  sessionId={session.session_id}
                  profile={session.confirmed_profile}
                  api={api}
                  onClose={() => setSimRoom(null)}
                />
              )}
          </div>
          <ProfileForm
            key={session.session_id}
            draft={session.draft}
            revision={session.draft_revision}
            confirmed={session.confirmed_profile}
            confirmedVersion={session.profile_version}
            busy={busy}
            onConfirm={confirm}
            onSave={save}
            onDirty={setEditing}
          />
        </div>
      )}
      {viewRoom &&
        session &&
        !editing &&
        visibleStatuses.includes(result?.status ?? "") && (
          <ViewingForm
            room={viewRoom}
            sessionId={session.session_id}
            api={api}
            onCancel={() => setViewRoom(null)}
            onDone={() => {
              setViewRoom(null);
              void loadViews();
              setMessages((m) => [
                ...m,
                {
                  role: "assistant",
                  text: "Đã ghi nhận yêu cầu xem phòng. Bạn có thể theo dõi ở mục Lịch xem; lịch còn chờ quản lý xác nhận.",
                },
              ]);
            }}
          />
        )}
    </>
  );
}
