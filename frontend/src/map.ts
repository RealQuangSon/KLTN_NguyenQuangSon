// Bản đồ Goong — vector style cho MapLibre GL. Key loại "Map tiles" lấy từ
// VITE_GOONG_API_KEY (frontend/.env.local, đã gitignore); thiếu key thì
// MapView dùng style raster OpenStreetMap nội tuyến.
export function goongApiKey(): string | null {
  const key = import.meta.env.VITE_GOONG_API_KEY;
  return typeof key === "string" && key.trim() ? key.trim() : null;
}
// Style JSON của Goong — MapLibre GL nạp trực tiếp URL này.
export function goongStyleUrl(key: string): string {
  return `https://tiles.goong.io/assets/goong_map_web.json?api_key=${encodeURIComponent(key)}`;
}
// Nhãn giá ngắn trên marker theo kiểu "3,5 tr" (triệu/tháng). Null -> "?" vì
// máy chủ chưa đủ dữ liệu phí, không tự bịa giá.
export function priceShortLabel(monthly: number | null | undefined): string {
  if (monthly == null || !Number.isFinite(monthly)) return "?";
  const millions = monthly / 1_000_000;
  const rounded = Math.round(millions * 10) / 10;
  const text = rounded.toFixed(1).replace(/\.0$/, "").replace(".", ",");
  return `${text} tr`;
}
