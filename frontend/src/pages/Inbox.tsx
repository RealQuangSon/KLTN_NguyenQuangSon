import { useCallback, useEffect, useRef, useState } from "react";
import type { Api } from "../api";
import type { Role } from "../types";
import { amenities, bandLabels, roomTypeLabels } from "../types";
import { EmptyState, ErrorNotice, Icon, money } from "../components/Shared";
// Hộp thư hợp nhất (Unified Inbox) cho khách và chủ nhà. Tin nhắn được đọc
// lại định kỳ (polling); cuộc trò chuyện mở từ trợ lý mang theo ngữ cảnh
// chuyển giao đã che thông tin liên hệ, không có thu nhập của khách.
export const OPEN_CONVERSATION_KEY = "homematch.openConversation";
export const openConversation = (id: string, path: string) => {
  sessionStorage.setItem(OPEN_CONVERSATION_KEY, id);
  window.history.pushState(null, "", path);
  window.dispatchEvent(new PopStateEvent("popstate"));
};
interface Conversation {
  id: string;
  renter_id: string;
  landlord_id: string;
  room_id: string | null;
  last_message_at: string;
  unread: number;
  context: {
    room?: {
      id: string;
      title: string;
      area: string;
      city: string;
      rent_vnd: number;
    };
    needs?: Record<string, unknown> | null;
    affordability_band?: string | null;
    recent_ai_chat?: { speaker: string; text: string }[];
  };
}
interface Message {
  id: string;
  sender_id: string;
  sender_role: string;
  body: string;
  created_at: string;
}
const POLL_MS = 5000;
export function InboxPage({ api, role }: { api: Api; role: Role }) {
  const [items, setItems] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(() =>
    sessionStorage.getItem(OPEN_CONVERSATION_KEY),
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    sessionStorage.removeItem(OPEN_CONVERSATION_KEY);
    return () => {
      live.current = false;
    };
  }, []);
  const refresh = useCallback(async () => {
    try {
      const list = await api.get<Conversation[]>("/conversations");
      if (!live.current) return;
      setItems(list);
      const target = activeId ?? list[0]?.id ?? null;
      if (target && target !== activeId) setActiveId(target);
      if (target) {
        const thread = await api.get<{ messages: Message[] }>(
          `/conversations/${target}/messages`,
        );
        if (live.current) setMessages(thread.messages);
      }
    } catch (err) {
      if (live.current) setError((err as Error).message);
    }
  }, [api, activeId]);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);
  const active = items.find((item) => item.id === activeId) || null;
  const send = async () => {
    if (!active || !text.trim()) return;
    setBusy(true);
    try {
      await api.post(`/conversations/${active.id}/messages`, { body: text });
      setText("");
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const mine = role === "owner" ? "owner" : "renter";
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            {role === "owner" ? "HỘP THƯ HỢP NHẤT" : "TIN NHẮN"}
          </span>
          <h1>
            {role === "owner" ? "Tin nhắn với khách" : "Trò chuyện với chủ nhà"}
          </h1>
          <p>
            {role === "owner"
              ? "Khách chuyển từ trợ lý AI sang đây kèm nhu cầu đã xác nhận. Bạn chỉ thấy mức khả năng chi trả, không thấy thu nhập."
              : "Chủ nhà nhận nhu cầu đã xác nhận và các lượt chat gần nhất (đã che số điện thoại, email)."}
          </p>
        </div>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {!items.length ? (
        <section className="panel">
          <EmptyState
            title="Chưa có cuộc trò chuyện"
            description={
              role === "owner"
                ? "Khi khách bấm “Chat với chủ nhà” ở phòng của bạn, cuộc trò chuyện xuất hiện tại đây."
                : "Bấm “Chat với chủ nhà” ở một phòng để bắt đầu."
            }
            icon="chat"
          />
        </section>
      ) : (
        <div className="inbox-layout">
          <section
            className="panel inbox-list"
            aria-label="Danh sách trò chuyện"
          >
            {items.map((item) => (
              <button
                key={item.id}
                className={`queue-item ${item.id === activeId ? "active" : ""}`}
                onClick={() => setActiveId(item.id)}
              >
                <div>
                  <strong>
                    {role === "owner"
                      ? `Khách ${item.renter_id}`
                      : `Chủ nhà ${item.landlord_id}`}
                  </strong>
                  {item.unread > 0 && (
                    <span className="badge success">{item.unread} mới</span>
                  )}
                </div>
                <span>{item.context.room?.title || "Trao đổi chung"}</span>
              </button>
            ))}
          </section>
          <section className="panel inbox-thread" aria-label="Cuộc trò chuyện">
            {active && (
              <>
                {active.context.room && (
                  <div className="handover-card">
                    <strong>
                      <Icon name="home" size={15} /> {active.context.room.title}
                    </strong>
                    <span>
                      {active.context.room.area} · {active.context.room.city} ·
                      thuê {money(active.context.room.rent_vnd)}
                    </span>
                    {role === "owner" && active.context.needs && (
                      <span>
                        Nhu cầu:{" "}
                        {String(
                          active.context.needs.area ||
                            active.context.needs.city ||
                            "",
                        )}
                        {active.context.needs.room_type
                          ? ` · ${roomTypeLabels[active.context.needs.room_type as keyof typeof roomTypeLabels]}`
                          : ""}
                        {active.context.needs.people
                          ? ` · ${active.context.needs.people} người`
                          : ""}
                        {active.context.needs.max_monthly_cost_vnd
                          ? ` · trần tổng tháng ${money(Number(active.context.needs.max_monthly_cost_vnd))}`
                          : ""}
                        {Array.isArray(active.context.needs.preferences) &&
                        active.context.needs.preferences.length
                          ? ` · ưu tiên: ${(
                              active.context.needs.preferences as string[]
                            )
                              .map((key) => amenities[key] || key)
                              .join(", ")}`
                          : ""}
                      </span>
                    )}
                    {role === "owner" && active.context.affordability_band && (
                      <span>
                        Khả năng chi trả:{" "}
                        {
                          bandLabels[
                            active.context
                              .affordability_band as keyof typeof bandLabels
                          ]
                        }
                      </span>
                    )}
                    {role === "owner" &&
                      (active.context.recent_ai_chat?.length ?? 0) > 0 && (
                        <details>
                          <summary>
                            Các lượt chat gần nhất với trợ lý AI
                          </summary>
                          {active.context.recent_ai_chat!.map((turn, index) => (
                            <p key={index}>
                              <strong>
                                {turn.speaker === "user" ? "Khách" : "Trợ lý"}:
                              </strong>{" "}
                              {turn.text}
                            </p>
                          ))}
                        </details>
                      )}
                  </div>
                )}
                <div className="message-list">
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={`chat-bubble ${message.sender_role === "system" ? "system" : message.sender_role === mine ? "mine" : "theirs"}`}
                    >
                      <p>{message.body}</p>
                      <small>
                        {new Intl.DateTimeFormat("vi-VN", {
                          timeStyle: "short",
                          dateStyle: "short",
                        }).format(new Date(message.created_at))}
                      </small>
                    </div>
                  ))}
                </div>
                <form
                  className="composer"
                  onSubmit={(e) => {
                    e.preventDefault();
                    void send();
                  }}
                >
                  <label className="sr-only" htmlFor="inbox-text">
                    Tin nhắn
                  </label>
                  <input
                    id="inbox-text"
                    value={text}
                    maxLength={2000}
                    placeholder="Nhập tin nhắn…"
                    onChange={(e) => setText(e.target.value)}
                    disabled={busy}
                  />
                  <button className="button" disabled={busy || !text.trim()}>
                    Gửi
                  </button>
                </form>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
