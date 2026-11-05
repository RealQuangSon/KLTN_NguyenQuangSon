// Mascot trợ lý vẽ bằng SVG của HomeMatch (không dùng tài sản của bên kia):
// khuôn mặt tròn navy, nón nhà màu cam — spirit giống agent thân thiện.
export function AgentMascot({ size = 48 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      aria-hidden="true"
    >
      {/* nón nhà cam */}
      <path d="M32 4 L52 20 H12 Z" fill="#ff7518" />
      <rect x="29" y="10" width="6" height="5" rx="1.2" fill="#fff" />
      {/* ăng-ten */}
      <line
        x1="32"
        y1="4"
        x2="32"
        y2="1"
        stroke="#14213d"
        strokeWidth="2"
        strokeLinecap="round"
      />
      {/* đầu tròn */}
      <rect
        x="10"
        y="20"
        width="44"
        height="34"
        rx="17"
        fill="#fff"
        stroke="#14213d"
        strokeWidth="3"
      />
      {/* tai nghe hai bên */}
      <rect x="4" y="30" width="8" height="13" rx="4" fill="#14213d" />
      <rect x="52" y="30" width="8" height="13" rx="4" fill="#14213d" />
      {/* mắt */}
      <circle cx="24" cy="36" r="3" fill="#14213d" />
      <circle cx="40" cy="36" r="3" fill="#14213d" />
      {/* má + miệng cười */}
      <circle cx="18" cy="42" r="2" fill="#ffc7a3" />
      <circle cx="46" cy="42" r="2" fill="#ffc7a3" />
      <path
        d="M27 43c2 2.6 8 2.6 10 0"
        stroke="#14213d"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
    </svg>
  );
}
