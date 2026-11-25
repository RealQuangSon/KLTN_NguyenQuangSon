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
// Quãng đường kiểu "850 m" / "3,2 km" — chỉ định dạng số máy chủ trả.
export function formatDistance(meters: number): string {
  if (meters < 1000) return `${Math.max(10, Math.round(meters / 10) * 10)} m`;
  const km = Math.round(meters / 100) / 10;
  return `${km.toFixed(1).replace(/\.0$/, "").replace(".", ",")} km`;
}
// Thời gian kiểu "11 phút" / "1 giờ 5 phút".
export function formatDuration(seconds: number): string {
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) return `${minutes} phút`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} giờ ${rest} phút` : `${hours} giờ`;
}
// Vòng tròn bán kính quanh điểm neo dạng ring GeoJSON [[lng, lat], ...]
// (MapLibre không có circle theo mét). Xấp xỉ phẳng, đủ đúng cho bán kính
// vài km trong một thành phố; chỉ để vẽ, không dùng để lọc.
export function circleRing(
  latitude: number,
  longitude: number,
  radiusM: number,
  steps = 64,
): [number, number][] {
  const dLat = radiusM / 111_320;
  const dLng = radiusM / (111_320 * Math.cos((latitude * Math.PI) / 180));
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const angle = ((i % steps) / steps) * 2 * Math.PI;
    ring.push([
      longitude + dLng * Math.cos(angle),
      latitude + dLat * Math.sin(angle),
    ]);
  }
  return ring;
}
export type MapPadding = {
  top: number;
  bottom: number;
  left: number;
  right: number;
};
// Lề khi vừa khung tuyến + vòng bán kính, chừa chỗ cho bảng chỉ đường nằm ở
// góc trên bên phải. Thử hai cách (chừa lề phải bằng bề ngang bảng, hoặc chừa
// lề trên bằng chiều cao bảng) rồi lấy cách để lại vùng vuông lớn hơn — vòng
// bán kính là hình vuông khi vừa khung. Khung bản đồ hẹp mà cao (đang mở chi
// tiết căn) thì đẩy xuống dưới bảng thay vì ép sang trái. Còn quá ít chỗ thì
// chỉ chừa lề mỏng, chấp nhận bảng che một phần.
export function routePadding(
  width: number,
  height: number,
  panelWidth: number,
  panelHeight: number,
): MapPadding {
  const base = { top: 70, bottom: 70, left: 70, right: 70 };
  if (!width || !height) return base;
  const room = (pad: MapPadding) =>
    Math.min(width - pad.left - pad.right, height - pad.top - pad.bottom);
  let best = base;
  if (panelWidth && panelHeight) {
    const side = { ...base, right: Math.max(70, panelWidth + 30) };
    const below = { ...base, top: Math.max(70, panelHeight + 30) };
    best = room(side) >= room(below) ? side : below;
  }
  return room(best) >= 120
    ? best
    : { top: 20, bottom: 20, left: 20, right: 20 };
}
// Chỉ đường chi tiết từng ngã rẽ trên Google Maps (khách tự bấm mở tab mới).
// Đi xe không ép travelmode để Google tự chọn (ở Việt Nam có xe máy).
export function googleDirectionsUrl(
  origin: { latitude: number; longitude: number },
  destination: { latitude: number; longitude: number },
  travel: "ride" | "walk",
): string {
  const params = new URLSearchParams({
    api: "1",
    origin: `${origin.latitude},${origin.longitude}`,
    destination: `${destination.latitude},${destination.longitude}`,
  });
  if (travel === "walk") params.set("travelmode", "walking");
  return `https://www.google.com/maps/dir/?${params.toString()}`;
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
