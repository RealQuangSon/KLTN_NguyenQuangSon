import { useEffect, useRef, useState } from "react";
import { Icon } from "./Shared";

// Nút avatar ở góc phải thanh đầu: rê chuột (hoặc bấm/Tab vào) mở menu nhỏ gồm
// "Chi tiết" (trang hồ sơ) và "Đăng xuất". Dùng chung cho thanh đầu của màn trợ
// lý và trang chủ khi đã đăng nhập, cho mọi vai trò.
export function AccountMenu({
  initials,
  label,
  onProfile,
  onLogout,
}: {
  initials: string;
  label: string;
  onProfile: () => void;
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const closeTimer = useRef<number | undefined>(undefined);
  const cancelClose = () => window.clearTimeout(closeTimer.current);
  // Đóng trễ một nhịp để chuột đi từ avatar xuống menu không bị tắt giữa chừng.
  const scheduleClose = () => {
    cancelClose();
    closeTimer.current = window.setTimeout(() => setOpen(false), 150);
  };
  useEffect(() => () => window.clearTimeout(closeTimer.current), []);
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);
  const choose = (action: () => void) => () => {
    cancelClose();
    setOpen(false);
    action();
  };
  return (
    <div
      ref={root}
      className="account-menu"
      onMouseEnter={() => {
        cancelClose();
        setOpen(true);
      }}
      onMouseLeave={scheduleClose}
      onKeyDown={(event) => {
        if (event.key === "Escape") setOpen(false);
      }}
    >
      <button
        type="button"
        className="header-avatar"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        {initials}
      </button>
      {open && (
        <div className="account-menu-list" role="menu">
          <button type="button" role="menuitem" onClick={choose(onProfile)}>
            <Icon name="user" size={16} /> Chi tiết
          </button>
          <button
            type="button"
            role="menuitem"
            className="danger"
            onClick={choose(onLogout)}
          >
            <Icon name="logout" size={16} /> Đăng xuất
          </button>
        </div>
      )}
    </div>
  );
}
