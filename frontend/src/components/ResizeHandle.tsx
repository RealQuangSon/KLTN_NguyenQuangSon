import { useRef, useState } from "react";

// Thanh kéo đổi chiều rộng giữa hai khung cạnh nhau. Kéo (chuột/cảm ứng) hoặc
// dùng phím ←/→; bấm đúp hoặc phím Home trả về kích thước mặc định. Chiều rộng
// khung bên trái do trang cha giữ (getSize đo kích thước thật, onChange nhận số
// px mới đã kẹp trong [min, max]).
export function ResizeHandle({
  label,
  getSize,
  min,
  max,
  onChange,
  onReset,
}: {
  label: string;
  getSize: () => number;
  min: number;
  max: () => number;
  onChange: (px: number) => void;
  onReset: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const start = useRef({ x: 0, size: 0 });
  const clamp = (px: number) => Math.round(Math.min(max(), Math.max(min, px)));
  return (
    <div
      className={`panel-resizer${dragging ? " dragging" : ""}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuemin={min}
      aria-valuenow={Math.round(getSize())}
      tabIndex={0}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        start.current = { x: event.clientX, size: getSize() };
        setDragging(true);
      }}
      onPointerMove={(event) => {
        if (!dragging) return;
        onChange(clamp(start.current.size + event.clientX - start.current.x));
      }}
      onPointerUp={() => setDragging(false)}
      onPointerCancel={() => setDragging(false)}
      onDoubleClick={onReset}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          onChange(clamp(getSize() - 24));
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          onChange(clamp(getSize() + 24));
        } else if (event.key === "Home") {
          event.preventDefault();
          onReset();
        }
      }}
    />
  );
}
