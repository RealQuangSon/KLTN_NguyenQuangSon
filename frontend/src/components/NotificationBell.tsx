import { useCallback, useEffect, useRef, useState } from "react";
import type { Api } from "../api";
import { Icon } from "./Shared";
// Thông báo trong ứng dụng: nhắc lịch, danh sách phòng sẵn sàng, tin nhắn mới, phòng
// đổi trạng thái/giá, gợi ý tương đương. Đọc lại mỗi 30 giây.
// Nút nằm trên topbar (placement "topbar", bảng mở dạng dropdown dưới nút) hoặc
// chân thanh điều hướng (mặc định, bảng mở cạnh nút theo đáy nút); đóng khi bấm
// ra ngoài hoặc nhấn Esc.
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
  placement = "sidebar",
}: {
  api: Api;
  onNavigate: (path: string) => void;
  placement?: "sidebar" | "topbar";
}) {
  const [state, setState] = useState<{ unread: number; items: Item[] }>({
    unread: 0,
    items: [],
  });
  const [open, setOpen] = useState(false);
  const [anchorBottom, setAnchorBottom] = useState(16);
  const live = useRef(true);
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
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
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      button.current?.focus();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  const toggle = () => {
    // Chỉ cần khoảng cách tới đáy màn khi bảng neo theo đáy (chế độ sidebar).
    if (placement === "sidebar" && !open && button.current) {
      const rect = button.current.getBoundingClientRect();
      setAnchorBottom(Math.max(12, window.innerHeight - rect.bottom));
    }
    setOpen(!open);
  };
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
    <div className="notification-bell" ref={root}>
      <button
        ref={button}
        type="button"
        className={open ? "nav-link nav-bell open" : "nav-link nav-bell"}
        aria-label={`Thông báo (${state.unread} chưa đọc)`}
        aria-expanded={open}
        onClick={toggle}
      >
        <Icon name="bell" size={20} />
        <span className="nav-label">Thông báo</span>
        {state.unread > 0 && <span className="bell-count">{state.unread}</span>}
      </button>
      {open && (
        <div
          className={
            placement === "topbar"
              ? "notification-panel"
              : "notification-panel side"
          }
          role="dialog"
          aria-label="Thông báo"
          style={
            placement === "sidebar"
              ? ({
                  "--anchor-bottom": `${anchorBottom}px`,
                } as React.CSSProperties)
              : undefined
          }
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
