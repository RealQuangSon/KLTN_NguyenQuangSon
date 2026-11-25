import { useId } from "react";

// Mascot trợ lý vẽ bằng SVG của HomeMatch (không dùng tài sản của bên kia):
// khuôn mặt tròn nâu đen, nón mái nhà ghép từ hai mảnh (burgundy + vàng đồng)
// giống logo — nửa trái có núm cài vào hốc nửa phải, khe khoét bằng mask.
export function AgentMascot({ size = 48 }: { size?: number }) {
  const maskId = `agent-roof-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
    >
      {/* ăng-ten */}
      <line
        x1="32"
        y1="4"
        x2="32"
        y2="0.8"
        stroke="#241a1e"
        strokeWidth="2"
        strokeLinecap="round"
      />
      {/* nón mái nhà hai mảnh ghép */}
      <mask
        id={maskId}
        maskUnits="userSpaceOnUse"
        x="0"
        y="0"
        width="64"
        height="64"
      >
        <path
          d="M32 4.5 53 21.5H11Z"
          fill="#fff"
          stroke="#fff"
          strokeWidth="2.6"
          strokeLinejoin="round"
        />
        <path
          d="M32 0v10.8a3.8 3.8 0 1 1 0 3.6V26"
          stroke="#000"
          strokeWidth="1.3"
        />
      </mask>
      <g mask={`url(#${maskId})`}>
        <rect width="64" height="64" fill="#e5a93b" />
        <path d="M0 0h32v10.8a3.8 3.8 0 1 1 0 3.6V64H0Z" fill="#a5142f" />
      </g>
      {/* đầu tròn */}
      <rect
        x="10"
        y="20"
        width="44"
        height="34"
        rx="17"
        fill="#fff"
        stroke="#241a1e"
        strokeWidth="3"
      />
      {/* tai nghe hai bên */}
      <rect x="4" y="30" width="8" height="13" rx="4" fill="#241a1e" />
      <rect x="52" y="30" width="8" height="13" rx="4" fill="#241a1e" />
      {/* mắt */}
      <circle cx="24" cy="36" r="3" fill="#241a1e" />
      <circle cx="40" cy="36" r="3" fill="#241a1e" />
      {/* má + miệng cười */}
      <circle cx="18" cy="42" r="2" fill="#f3c6cf" />
      <circle cx="46" cy="42" r="2" fill="#f3c6cf" />
      <path
        d="M27 43c2 2.6 8 2.6 10 0"
        stroke="#241a1e"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}
