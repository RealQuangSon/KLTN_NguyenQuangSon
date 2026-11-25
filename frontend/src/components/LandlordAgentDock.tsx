import { Fragment, useEffect, useRef, useState } from "react";
import { ApiError, type Api } from "../api";
import { useRouter } from "../router";
import { AgentMascot } from "./AgentMascot";
import { Icon } from "./Shared";

// Khung chat nổi của trợ lý chủ nhà ở mọi trang /chu-nha/*. Trợ lý chỉ ĐỌC và
// GỢI Ý (máy chủ không có công cụ ghi); câu trả lời nhắc tới màn nào thì đường
// dẫn là link bấm được. Hội thoại chỉ nằm trong phiên trình duyệt này — máy chủ
// không lưu, mỗi lượt gửi kèm vài tin gần nhất để agent nhớ mạch.
type Reply = {
  message: string;
  agent_mode: "agent" | "rules" | "rules_fallback";
  steps: { tool: string; ok: boolean }[];
};
type Entry = {
  role: "user" | "assistant";
  text: string;
  tools?: string[];
  mode?: Reply["agent_mode"];
  error?: boolean;
};

const toolLabels: Record<string, string> = {
  get_overview: "tổng quan",
  list_rooms: "danh sách phòng",
  room_performance: "hiệu quả phòng",
  price_advice: "giá so sánh",
  vacancy_report: "phòng trống",
  draft_post: "nháp bài đăng",
  list_viewings: "lịch xem",
  list_conversations: "tin nhắn",
  billing_overview: "hóa đơn",
  list_maintenance: "sửa chữa",
};
const suggestions = [
  "Tình hình phòng tháng này thế nào?",
  "Vì sao phòng trống lâu?",
  "Phòng nào nên chỉnh giá?",
  "Có lịch xem nào cần phản hồi?",
  "Hóa đơn nào đang quá hạn?",
];
const MAX_ENTRIES = 30;
const storageKey = (actorId: string) => `homematch.landlordAgent.${actorId}`;
const PATH = /(\/chu-nha\/[a-z-]+)/g;

function load(actorId: string): Entry[] {
  try {
    const parsed = JSON.parse(
      sessionStorage.getItem(storageKey(actorId)) ?? "[]",
    );
    return Array.isArray(parsed) ? parsed.slice(-MAX_ENTRIES) : [];
  } catch {
    return [];
  }
}

export function LandlordAgentDock({
  api,
  actorId,
}: {
  api: Api;
  actorId: string;
}) {
  const { navigate } = useRouter();
  const [open, setOpen] = useState(false);
  const [entries, setEntries] = useState<Entry[]>(() => load(actorId));
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    try {
      sessionStorage.setItem(
        storageKey(actorId),
        JSON.stringify(entries.slice(-MAX_ENTRIES)),
      );
    } catch {
      // Không lưu được: hội thoại chỉ giữ trong lúc trang đang mở.
    }
  }, [entries, actorId]);
  useEffect(() => {
    if (open) {
      input.current?.focus();
      bottom.current?.scrollIntoView?.({ block: "end" });
    }
  }, [open, entries, busy]);
  const send = async (value: string) => {
    const message = value.trim();
    if (!message || busy) return;
    const history = entries
      .filter((entry) => !entry.error)
      .slice(-8)
      .map((entry) => ({ role: entry.role, text: entry.text }));
    setEntries((list) => [...list, { role: "user", text: message }]);
    setText("");
    setBusy(true);
    try {
      const reply = await api.post<Reply>("/landlord/agent", {
        message,
        history,
      });
      setEntries((list) => [
        ...list,
        {
          role: "assistant",
          text: reply.message,
          tools: [
            ...new Set(
              reply.steps
                .filter((step) => step.ok)
                .map((step) => toolLabels[step.tool])
                .filter(Boolean),
            ),
          ],
          mode: reply.agent_mode,
        },
      ]);
    } catch (error) {
      setEntries((list) => [
        ...list,
        {
          role: "assistant",
          error: true,
          text:
            error instanceof ApiError
              ? error.message
              : "Chưa kết nối được trợ lý, bạn thử lại sau ít phút.",
        },
      ]);
    } finally {
      setBusy(false);
    }
  };
  // Đường dẫn tới màn chủ nhà trong câu trả lời thành link bấm được.
  const linkify = (value: string) =>
    value.split(PATH).map((part, index) =>
      index % 2 === 1 ? (
        <a
          key={index}
          href={part}
          onClick={(event) => {
            event.preventDefault();
            navigate(part);
            setOpen(false);
          }}
        >
          {part}
        </a>
      ) : (
        <Fragment key={index}>{part}</Fragment>
      ),
    );
  if (!open)
    return (
      <button
        type="button"
        className="lad-fab"
        aria-label="Mở trợ lý chủ nhà"
        title="Hỏi trợ lý chủ nhà"
        onClick={() => setOpen(true)}
      >
        <AgentMascot size={40} />
      </button>
    );
  return (
    <section
      className="lad-panel"
      role="dialog"
      aria-label="Trợ lý chủ nhà"
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      <header className="lad-head">
        <AgentMascot size={34} />
        <div>
          <strong>Trợ lý chủ nhà</strong>
          <small>Chỉ xem và gợi ý, không tự thay đổi gì</small>
        </div>
        <button
          type="button"
          className="lad-icon"
          aria-label="Cuộc trò chuyện mới"
          title="Cuộc trò chuyện mới"
          disabled={busy || entries.length === 0}
          onClick={() => setEntries([])}
        >
          <Icon name="refresh" size={16} />
        </button>
        <button
          type="button"
          className="lad-icon"
          aria-label="Thu nhỏ trợ lý"
          title="Thu nhỏ"
          onClick={() => setOpen(false)}
        >
          <Icon name="close" size={16} />
        </button>
      </header>
      <div className="lad-body" aria-live="polite">
        {entries.length === 0 && (
          <div className="lad-empty">
            <p>
              Hỏi mình về phòng, lịch xem, tin nhắn, hóa đơn hay giá thuê. Ví
              dụ:
            </p>
            <div className="lad-chips">
              {suggestions.map((item) => (
                <button
                  key={item}
                  type="button"
                  disabled={busy}
                  onClick={() => void send(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        )}
        {entries.map((entry, index) => (
          <div
            key={index}
            className={`lad-msg ${entry.role}${entry.error ? " error" : ""}`}
          >
            <p>
              {entry.role === "assistant" ? linkify(entry.text) : entry.text}
            </p>
            {entry.tools && entry.tools.length > 0 && (
              <small>Đã xem: {entry.tools.join(", ")}</small>
            )}
            {entry.mode && entry.mode !== "agent" && (
              <small>Trả lời theo mẫu có sẵn (chưa dùng AI)</small>
            )}
          </div>
        ))}
        {busy && (
          <div className="lad-msg assistant" role="status">
            <p className="lad-typing">Đang xem dữ liệu…</p>
          </div>
        )}
        <div ref={bottom} />
      </div>
      <form
        className="lad-foot"
        onSubmit={(event) => {
          event.preventDefault();
          void send(text);
        }}
      >
        <textarea
          ref={input}
          rows={1}
          maxLength={1000}
          value={text}
          placeholder="Nhắn cho trợ lý…"
          aria-label="Câu hỏi cho trợ lý chủ nhà"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              void send(text);
            }
          }}
        />
        <button
          type="submit"
          className="lad-send"
          aria-label="Gửi"
          disabled={busy || !text.trim()}
        >
          <Icon name="send" size={16} />
        </button>
      </form>
    </section>
  );
}
