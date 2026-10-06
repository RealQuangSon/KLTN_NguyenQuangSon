import { useEffect, useMemo, useRef, useState } from "react";
import "leaflet/dist/leaflet.css";
import type { Room } from "../types";
import { money } from "./Shared";
// Bản đồ tin đăng (OpenStreetMap qua Leaflet). Vị trí công khai là gần đúng:
// mỗi ghim có vòng tròn sai số; tin chỉ biết tới khu vực không được đặt ghim.
// Lỗi tải bản đồ không chặn việc dùng danh sách.
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
export function MapView({
  pins,
  selectedId,
  onSelect,
}: {
  pins: Pin[];
  selectedId?: string | null;
  onSelect: (id: string) => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
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
    let map: import("leaflet").Map | null = null;
    (async () => {
      try {
        const L = await import("leaflet");
        if (disposed || !host.current) return;
        map = L.map(host.current, { scrollWheelZoom: false });
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: "© OpenStreetMap",
        }).addTo(map);
        const bounds: [number, number][] = [];
        for (const pin of placed) {
          const point: [number, number] = [pin.latitude!, pin.longitude!];
          bounds.push(point);
          L.circle(point, {
            radius: Math.max(pin.uncertainty_m ?? 100, 50),
            color: pin.id === selectedId ? "#ab4530" : "#c6543c",
            weight: pin.id === selectedId ? 3 : 1,
            fillOpacity: 0.15,
          })
            .addTo(map)
            .bindTooltip(
              `${pin.title.split(". ")[0]} · ${money(pin.monthly)}/tháng (vị trí gần đúng)`,
            )
            .on("click", () => onSelect(pin.id));
        }
        if (bounds.length) map.fitBounds(bounds, { padding: [24, 24] });
        else map.setView([16.0, 106.0], 5);
      } catch {
        if (!disposed)
          setError("Không tải được bản đồ; bạn vẫn có thể dùng danh sách.");
      }
    })();
    return () => {
      disposed = true;
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
        {placed.length}/{pins.length} tin có tọa độ gần đúng; vòng tròn là sai
        số vị trí. Tin chỉ biết tới khu vực không hiện trên bản đồ.
      </small>
    </div>
  );
}
