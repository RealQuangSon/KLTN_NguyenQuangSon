import { useCallback, useEffect, useRef, useState } from "react";
import type { Api } from "../api";
import { Icon } from "./Shared";
// Thông báo trong ứng dụng: nhắc lịch, phòng được duyệt, tin nhắn mới, phòng
// đổi trạng thái/giá, gợi ý tương đương. Đọc lại mỗi 30 giây.
interface Item {
  id: string;
  kind: string;
  title: string;
  body: string;
  link: string | null;
  created_at: string;
  read_at: string | null;
}
const POLL_MS = 30000;
export function NotificationBell({
  api,
  onNavigate,
}: {
  api: Api;
  onNavigate: (path: string) => void;
}) {
  const [state, setState] = useState<{ unread: number; items: Item[] }>({
    unread: 0,
    items: [],
  });
  const [open, setOpen] = useState(false);
  const live = useRef(true);
  const load = useCallback(async () => {
    try {
      const data = await api.get<{ unread?: number; items?: Item[] }>(
        "/notifications",
      );
      if (live.current)
        setState({ unread: data.unread ?? 0, items: data.items ?? [] });
    } catch {
      // Thông báo là phụ trợ: lỗi đọc không chặn màn chính.
    }
  }, [api]);
  useEffect(() => {
    live.current = true;
    void load();
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => {
      live.current = false;
      window.clearInterval(timer);
    };
  }, [load]);
  const markAll = async () => {
    try {
      const data = await api.post<{ unread: number; items: Item[] }>(
        "/notifications/read",
        {},
      );
      setState({ unread: data.unread ?? 0, items: data.items ?? [] });
    } catch {
      /* giữ trạng thái hiện tại */
    }
  };
  return (
    <div className="notification-bell">
      <button
        className="icon-button"
        aria-label={`Thông báo (${state.unread} chưa đọc)`}
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <Icon name="clock" size={18} />
        {state.unread > 0 && <span className="bell-count">{state.unread}</span>}
      </button>
      {open && (
        <div
          className="notification-panel"
          role="dialog"
          aria-label="Thông báo"
        >
          <div className="section-heading">
            <strong>Thông báo</strong>
            <button className="text-button" onClick={() => void markAll()}>
              Đánh dấu đã đọc
            </button>
          </div>
          {state.items.length === 0 ? (
            <p className="subtle">Chưa có thông báo.</p>
          ) : (
            <ul>
              {state.items.map((item) => (
                <li key={item.id} className={item.read_at ? "" : "unread"}>
                  <button
                    className="text-button"
                    onClick={() => {
                      setOpen(false);
                      void api
                        .post(`/notifications/${item.id}/read`, {})
                        .catch(() => {});
                      if (item.link) onNavigate(item.link);
                    }}
                  >
                    <strong>{item.title}</strong>
                    <span>{item.body}</span>
                    <small>
                      {new Intl.DateTimeFormat("vi-VN", {
                        dateStyle: "short",
                        timeStyle: "short",
                      }).format(new Date(item.created_at))}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
