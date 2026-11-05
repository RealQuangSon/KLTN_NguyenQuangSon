import { useEffect, useMemo, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Room } from "../types";
import { goongApiKey, goongStyleUrl, priceShortLabel } from "../map";
// Bản đồ tin đăng. Goong cung cấp vector style cho MapLibre GL (không còn
// endpoint raster cho Leaflet), nên engine là maplibre-gl; thiếu
// VITE_GOONG_API_KEY thì dùng style raster OpenStreetMap nội tuyến. Vị trí
// công khai là gần đúng: marker hiển thị giá tháng, tin chỉ biết tới khu vực
// không được đặt marker. Lỗi tải bản đồ không chặn việc dùng danh sách.
type Pin = Pick<
  Room,
  | "id"
  | "title"
  | "latitude"
  | "longitude"
  | "uncertainty_m"
  | "location_accuracy"
> & {
  monthly: number | null;
};
const OSM_STYLE = {
  version: 8 as const,
  sources: {
    osm: {
      type: "raster" as const,
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap",
    },
  },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};
// URL tuyệt đối tới file worker do plugin vite phục vụ (dev) hoặc emit (build).
const workerHref = new URL("/maplibre-gl-worker.mjs", document.baseURI).href;
export function MapView({
  pins,
  selectedId,
  onSelect,
}: {
  pins: Pin[];
  selectedId?: string | null;
  // Bỏ onSelect ở ngữ cảnh chỉ xem (trang chi tiết tin): marker không nhấn được.
  onSelect?: (id: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  // Style Goong trả lỗi (key sai loại/hết hạn/hết quota) thì tự chuyển
  // OpenStreetMap ngay lúc chạy, không để bản đồ trống.
  const [goongFailed, setGoongFailed] = useState(false);
  const [goongFailReason, setGoongFailReason] = useState("");
  const placed = useMemo(
    () =>
      pins.filter(
        (pin) =>
          pin.latitude != null &&
          pin.longitude != null &&
          pin.location_accuracy !== "area_only",
      ),
    [pins],
  );
  useEffect(() => {
    let disposed = false;
    let map: import("maplibre-gl").Map | null = null;
    const markers: import("maplibre-gl").Marker[] = [];
    (async () => {
      try {
        const maplibregl = await import("maplibre-gl");
        if (disposed || !host.current) return;
        // v6 tách worker khỏi bundle; URL cố định do plugin vite phục vụ/emit.
        if (maplibregl.getWorkerUrl() !== workerHref)
          maplibregl.setWorkerUrl(workerHref);
        const key = goongApiKey();
        const leafletMap = new maplibregl.Map({
          container: host.current,
          style: key ? goongStyleUrl(key) : OSM_STYLE,
          scrollZoom: false,
          attributionControl: { compact: false },
        });
        map = leafletMap;
        // Fallback chỉ khi style Goong chưa nạp được (fetch lỗi, 401/403, parse
        // lỗi) hoặc quá 8 giây vẫn chưa "load". Lỗi lành tính sau khi load
        // (glyph, tile lẻ) không đổi style — MapLibre tự bỏ qua.
        let styleLoaded = false;
        let swapped = false;
        let firstError = "";
        const swapToOsm = (reason: string) => {
          if (swapped || disposed) return;
          swapped = true;
          setGoongFailed(true);
          setGoongFailReason(reason);
          leafletMap.setStyle(OSM_STYLE);
        };
        if (key) {
          leafletMap.on("error", (event) => {
            if (styleLoaded || swapped || disposed) return;
            // Ghi lại lỗi đầu tiên để chẩn đoán; chỉ swap khi có vẻ là lỗi
            // style/mạng (không phải tile/glyph lẻ sau khi đã load).
            const message = String(
              (event as { error?: { message?: string } }).error?.message ??
                "lỗi không rõ",
            );
            if (!firstError) firstError = message;
            if (
              /style|fetch|network|401|403|unauthorized|parse|Unexpected|WebGL|worker/i.test(
                message,
              )
            )
              swapToOsm(message.slice(0, 120));
          });
          setTimeout(() => {
            if (!styleLoaded)
              swapToOsm(
                `style Goong quá 20 giây chưa nạp xong${firstError ? `; lỗi đầu: ${firstError.slice(0, 100)}` : "; không có error event"}`,
              );
          }, 20000);
        }
        leafletMap.on("load", () => {
          styleLoaded = true;
          if (disposed) return;
          for (const pin of placed) {
            const selected = pin.id === selectedId;
            const pill = document.createElement("button");
            pill.type = "button";
            pill.className = "map-price-marker";
            pill.title = `${pin.title} · vị trí gần đúng`;
            pill.innerHTML = `<span class="${selected ? "selected" : ""}">${priceShortLabel(pin.monthly)}</span>`;
            pill.addEventListener("click", () => onSelect?.(pin.id));
            const marker = new maplibregl.Marker({ element: pill })
              .setLngLat([pin.longitude!, pin.latitude!])
              .addTo(leafletMap);
            markers.push(marker);
          }
          if (placed.length) {
            const bounds = new maplibregl.LngLatBounds();
            for (const pin of placed)
              bounds.extend([pin.longitude!, pin.latitude!]);
            leafletMap.fitBounds(bounds, { padding: 24, duration: 0 });
          } else {
            leafletMap.jumpTo({ center: [106.0, 16.0], zoom: 5 });
          }
        });
      } catch {
        if (!disposed)
          setError("Không tải được bản đồ; bạn vẫn có thể dùng danh sách.");
      }
    })();
    return () => {
      disposed = true;
      markers.forEach((marker) => marker.remove());
      map?.remove();
    };
  }, [placed, selectedId, onSelect]);
  return (
    <div className="map-view">
      {error ? (
        <p className="notice warning">{error}</p>
      ) : (
        <div ref={host} className="map-canvas" aria-label="Bản đồ tin đăng" />
      )}
      <small className="input-hint">
        {placed.length}/{pins.length} tin có tọa độ gần đúng; marker là giá
        tháng tại vị trí gần đúng. Tin chỉ biết tới khu vực không hiện trên bản
        đồ.
        {goongApiKey() &&
          goongFailed &&
          ` Tile Goong không tải được (${goongFailReason || "lỗi không rõ"}) — đang dùng OpenStreetMap dự phòng (kiểm tra key Goong loại Map tiles).`}
      </small>
    </div>
  );
}
