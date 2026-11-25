import { useId } from "react";

/**
 * Dấu hiệu HomeMatch: ngôi nhà ghép từ hai mảnh ghép (người thuê + phòng),
 * nửa trái có núm cài vào hốc của nửa phải. Mảnh trái trắng, mảnh phải vàng
 * đồng, đặt trên ô burgundy bo góc. Khe giữa hai mảnh được khoét bằng mask nên
 * trong suốt trên mọi nền. `tile={false}` bỏ ô nền, mảnh trái chuyển burgundy.
 */
export function BrandMark({
  size = 36,
  tile = true,
}: {
  size?: number;
  tile?: boolean;
}) {
  const maskId = `brand-mark-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden="true"
      className="brand-mark-svg"
    >
      {tile && <rect width="40" height="40" rx="11" fill="var(--accent)" />}
      <mask
        id={maskId}
        maskUnits="userSpaceOnUse"
        x="0"
        y="0"
        width="40"
        height="40"
      >
        <path
          d="M20 9 8.5 18.8V31h23V18.8Z"
          fill="#fff"
          stroke="#fff"
          strokeWidth="2.4"
          strokeLinejoin="round"
        />
        <path
          d="M20 4v19.3a3.6 3.6 0 1 1 0 3.4V36"
          stroke="#000"
          strokeWidth="1.3"
        />
      </mask>
      <g mask={`url(#${maskId})`}>
        <rect width="40" height="40" fill="var(--warm)" />
        <path
          d="M0 0h20v23.3a3.6 3.6 0 1 1 0 3.4V40H0Z"
          fill={tile ? "#fff" : "var(--accent)"}
        />
      </g>
    </svg>
  );
}

export function Brand() {
  return (
    <div className="brand">
      <BrandMark />
      <span className="brand-name">
        <span className="brand-title">
          Home<span className="brand-match">Match</span>
        </span>
        <small className="brand-tag">Trợ lý tìm phòng</small>
      </span>
    </div>
  );
}
