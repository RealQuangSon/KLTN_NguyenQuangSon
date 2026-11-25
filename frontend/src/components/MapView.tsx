import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { roomTypeLabels } from "../types";
import type { Room } from "../types";
import {
  circleRing,
  formatDistance,
  goongApiKey,
  goongStyleUrl,
  priceShortLabel,
  routePadding,
} from "../map";
import { Icon, money, roomTitle } from "./Shared";
// Bản đồ tin đăng. Goong cung cấp vector style cho MapLibre GL (không còn
// endpoint raster cho Leaflet), nên engine là maplibre-gl; thiếu
// VITE_GOONG_API_KEY thì dùng style raster OpenStreetMap nội tuyến. Vị trí
// công khai là gần đúng: marker hiển thị giá tháng, tin chỉ biết tới khu vực
// không được đặt marker. Lỗi tải bản đồ không chặn việc dùng danh sách.
//
// Bản đồ giữ MỘT instance trong suốt vòng đời component: thay pins, chọn thẻ
// hay hover marker chỉ cập nhật marker/popup tại chỗ, không hủy và tạo lại
// bản đồ — tránh khung trống chớp nhoáng khi tương tác liên tiếp.
export type MapPin = Pick<
  Room,
  | "id"
  | "title"
  | "latitude"
  | "longitude"
  | "uncertainty_m"
  | "location_accuracy"
> & {
  monthly: number | null;
  // Trường phục vụ popup room card; thiếu thì popup chỉ hiện phần có.
  area?: string | null;
  city?: string | null;
  area_m2?: number | null;
  bedrooms?: number | null;
  room_type?: string | null;
  // Ảnh bìa dạng src tuyệt đối (coverPhotoSrc); không có thì popup giữ hình
  // minh họa như thẻ tin không ảnh.
  photoUrl?: string | null;
};
// MP-01: điểm neo = nơi khách muốn ở gần (trường, công ty, địa điểm), lấy từ
// hồ sơ đã xác nhận; radius_m là bán kính tối đa mà bộ lọc cứng đang dùng.
export type MapAnchor = {
  label: string;
  latitude: number;
  longitude: number;
  radius_m: number;
};
// Đường đi căn → điểm neo do máy chủ trả; straight = đường chim bay (nét đứt).
export type MapRoute = {
  coordinates: [number, number][];
  straight: boolean;
};
const ANCHOR_SOURCE = "hm-anchor-radius";
const ANCHOR_LAYERS = ["hm-anchor-fill", "hm-anchor-line"] as const;
const ROUTE_SOURCE = "hm-route";
const ROUTE_LAYERS = ["hm-route-casing", "hm-route-line"] as const;
// Paint của MapLibre không đọc biến CSS: màu nhấn thương hiệu cho vòng bán
// kính, xanh dương cho đường đi để không lẫn với chấm băng giá đỏ/cam.
const ANCHOR_COLOR = "#a5142f";
const ROUTE_COLOR = "#2f6fde";
const STRAIGHT_COLOR = "#65585d";
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
// Băng giá hiển thị (triệu/tháng) cho màu marker và chú giải — chỉ là nhóm
// màu trình bày trên giá máy chủ đã trả; frontend không tự tính nhận xét
// thị trường (kiểu "phổ biến khoảng X triệu") vì con số đó phải do máy chủ
// tính từ kho.
const PRICE_BANDS = [
  { max: 3_000_000, label: "< 3 triệu", cls: "b0" },
  { max: 4_000_000, label: "3 – 4 triệu", cls: "b1" },
  { max: 5_000_000, label: "4 – 5 triệu", cls: "b2" },
  { max: Number.POSITIVE_INFINITY, label: "> 5 triệu", cls: "b3" },
] as const;
const bandFor = (monthly: number | null | undefined) =>
  monthly == null || !Number.isFinite(monthly)
    ? null
    : (PRICE_BANDS.find((band) => monthly <= band.max) ?? null);
// URL tuyệt đối tới file worker do plugin vite phục vụ (dev) hoặc emit (build).
const workerHref = () =>
  new URL("/maplibre-gl-worker.mjs", document.baseURI).href;
export function MapView({
  pins,
  selectedId,
  onSelect,
  savedIds,
  onToggleSave,
  anchor = null,
  route = null,
  overlay,
}: {
  pins: MapPin[];
  selectedId?: string | null;
  // Bấm marker: làm nổi căn và (ở workspace) cuộn tới thẻ tương ứng.
  onSelect?: (id: string) => void;
  // Trạng thái lưu + bật/tắt lưu ngay trong popup room card.
  savedIds?: string[];
  onToggleSave?: (roomId: string) => void;
  // Điểm neo + vòng bán kính; null = không vẽ.
  anchor?: MapAnchor | null;
  // Đường đi tới điểm neo của căn đang chọn; null = không vẽ.
  route?: MapRoute | null;
  // Khung nổi góc phải trên (bảng chỉ đường của trang cha).
  overlay?: ReactNode;
}) {
  const host = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  // Style Goong trả lỗi (key sai loại/hết hạn/hết quota) thì tự chuyển
  // OpenStreetMap ngay lúc chạy, không để bản đồ trống — âm thầm, không báo
  // chữ trên giao diện.
  const [mapReady, setMapReady] = useState(false);
  // Chú giải có thể thu gọn thành một nút nhỏ; nhớ lựa chọn trong trình duyệt.
  const [legendOpen, setLegendOpen] = useState(() => {
    try {
      return localStorage.getItem("homematch.mapLegend") !== "closed";
    } catch {
      return true;
    }
  });
  const toggleLegend = () =>
    setLegendOpen((open) => {
      try {
        localStorage.setItem("homematch.mapLegend", open ? "closed" : "open");
      } catch {
        // Không lưu được: lựa chọn chỉ giữ trong phiên này.
      }
      return !open;
    });
  const mapRef = useRef<import("maplibre-gl").Map | null>(null);
  const modRef = useRef<typeof import("maplibre-gl") | null>(null);
  const markersRef = useRef(new Map<string, import("maplibre-gl").Marker>());
  const pinsRef = useRef(new Map<string, MapPin>());
  const popupRef = useRef<import("maplibre-gl").Popup | null>(null);
  const openPinRef = useRef<string | null>(null);
  const stickyPopupRef = useRef(false);
  const closeTimerRef = useRef<number | null>(null);
  const fitKeyRef = useRef("");
  // So theo nội dung: trang cha dựng mảng pins mới mỗi lần render (đọc lại kết
  // quả 5 giây/lần); so theo tham chiếu sẽ hủy và tạo lại bản đồ trước khi tile kịp tải.
  const placedKey = JSON.stringify(
    pins.filter(
      (pin) =>
        pin.latitude != null &&
        pin.longitude != null &&
        pin.location_accuracy !== "area_only",
    ),
  );
  const placed = useMemo(() => JSON.parse(placedKey) as MapPin[], [placedKey]);
  const placedRef = useRef(placed);
  placedRef.current = placed;
  const selectedRef = useRef(selectedId);
  selectedRef.current = selectedId;
  const latestSelect = useRef(onSelect);
  latestSelect.current = onSelect;
  const savedRef = useRef(savedIds);
  savedRef.current = savedIds;
  const toggleSaveRef = useRef(onToggleSave);
  toggleSaveRef.current = onToggleSave;
  // Như pins: so theo nội dung để trang cha dựng object mới mỗi render không
  // làm vẽ lại vòng bán kính/đường đi.
  const anchorKey = anchor ? JSON.stringify(anchor) : "";
  const anchorRef = useRef(anchor);
  anchorRef.current = anchor;
  const routeKey = route ? JSON.stringify(route) : "";
  const anchorMarkerRef = useRef<import("maplibre-gl").Marker | null>(null);
  const overlayRef = useRef<HTMLDivElement>(null);
  const anchorDrawnRef = useRef(false);
  const routeDrawnRef = useRef(false);
  const cancelClose = () => {
    if (closeTimerRef.current != null) {
      window.clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
  };
  const closePopup = () => {
    cancelClose();
    popupRef.current?.remove();
    openPinRef.current = null;
    stickyPopupRef.current = false;
  };
  const scheduleClose = () => {
    if (stickyPopupRef.current || closeTimerRef.current != null) return;
    closeTimerRef.current = window.setTimeout(() => {
      closeTimerRef.current = null;
      if (!stickyPopupRef.current) closePopup();
    }, 250);
  };
  // Vừa khung toàn bộ marker. Giới hạn zoom tối đa 15 (tầm tên đường + điểm
  // quanh vùng) để kết quả lẻ — nhất là 1 tin — không bị phóng tối đa tới mức
  // chỉ còn một con đường, không nhận biết được khu vực.
  const fitToPins = () => {
    const map = mapRef.current;
    const mod = modRef.current;
    if (!map || !mod) return;
    const current = placedRef.current;
    const point = anchorRef.current;
    if (!current.length && !point) {
      map.jumpTo({ center: [106.0, 16.0], zoom: 5 });
      return;
    }
    const bounds = new mod.LngLatBounds();
    for (const pin of current) bounds.extend([pin.longitude!, pin.latitude!]);
    // Có điểm neo thì khung nhìn ôm trọn cả vòng bán kính.
    if (point)
      for (const corner of circleRing(
        point.latitude,
        point.longitude,
        point.radius_m,
        4,
      ))
        bounds.extend(corner);
    map.fitBounds(bounds, { padding: 40, maxZoom: 15, duration: 600 });
  };
  // Nội dung popup room card: hình minh họa, tên, giá tháng, diện tích, khu
  // vực, nút lưu. Văn bản từ dữ liệu chèn bằng textContent, không innerHTML.
  const buildPopupContent = (pin: MapPin) => {
    const root = document.createElement("div");
    root.className = "map-popup";
    const visual = document.createElement("div");
    visual.className = "map-popup-visual";
    const cover = pin.photoUrl;
    if (cover) {
      // Ảnh bìa thật của tin, cùng nguồn với thẻ danh sách; ảnh lỗi (tin hết
      // hạn) thì rơi về hình minh họa thay vì giữ khung ảnh hỏng.
      visual.classList.add("has-photo");
      const img = document.createElement("img");
      img.className = "map-popup-photo";
      img.src = cover;
      img.alt = roomTitle(pin.title);
      img.loading = "lazy";
      img.referrerPolicy = "no-referrer";
      img.addEventListener("error", () => {
        img.remove();
        visual.classList.remove("has-photo");
        if (!visual.querySelector("small")) {
          const fallback = document.createElement("small");
          fallback.textContent = "Hình minh họa";
          visual.appendChild(fallback);
        }
      });
      visual.appendChild(img);
      const source = document.createElement("small");
      source.textContent = "Ảnh tin gốc";
      visual.appendChild(source);
    } else {
      const visualLabel = document.createElement("small");
      visualLabel.textContent = "Hình minh họa";
      visual.appendChild(visualLabel);
    }
    root.appendChild(visual);
    const body = document.createElement("div");
    body.className = "map-popup-body";
    const title = document.createElement("strong");
    title.className = "map-popup-title";
    title.textContent = roomTitle(pin.title);
    body.appendChild(title);
    const locationBits = [pin.area, pin.city].filter(Boolean).join(" · ");
    if (locationBits || pin.room_type) {
      const meta = document.createElement("span");
      meta.className = "map-popup-meta";
      const typeLabel = pin.room_type
        ? (roomTypeLabels[pin.room_type as keyof typeof roomTypeLabels] ??
          pin.room_type)
        : "";
      meta.textContent =
        [locationBits, typeLabel].filter(Boolean).join(" · ") ||
        "Vị trí gần đúng";
      body.appendChild(meta);
    }
    const sizeBits = [
      pin.area_m2 != null ? `${pin.area_m2} m²` : "",
      pin.bedrooms ? `${pin.bedrooms} PN` : "",
    ]
      .filter(Boolean)
      .join(" · ");
    if (sizeBits) {
      const size = document.createElement("span");
      size.className = "map-popup-meta";
      size.textContent = sizeBits;
      body.appendChild(size);
    }
    const foot = document.createElement("div");
    foot.className = "map-popup-foot";
    const price = document.createElement("strong");
    price.className = "map-popup-price";
    // Chi phí chưa biết là "Chưa xác định", không hiện 0.
    price.textContent = money(pin.monthly);
    foot.appendChild(price);
    if (toggleSaveRef.current) {
      const saved = savedRef.current?.includes(pin.id) ?? false;
      const saveBtn = document.createElement("button");
      saveBtn.type = "button";
      saveBtn.className = `map-popup-save${saved ? " saved" : ""}`;
      saveBtn.setAttribute("aria-pressed", String(saved));
      saveBtn.setAttribute(
        "aria-label",
        saved ? "Bỏ lưu căn này" : "Lưu căn này",
      );
      saveBtn.textContent = saved ? "Đã lưu" : "Lưu";
      saveBtn.addEventListener("click", (event) => {
        event.stopPropagation();
        toggleSaveRef.current?.(pin.id);
        const savedNow = savedRef.current?.includes(pin.id) ?? false;
        saveBtn.className = `map-popup-save${savedNow ? " saved" : ""}`;
        saveBtn.setAttribute("aria-pressed", String(savedNow));
        saveBtn.setAttribute(
          "aria-label",
          savedNow ? "Bỏ lưu căn này" : "Lưu căn này",
        );
        saveBtn.textContent = savedNow ? "Đã lưu" : "Lưu";
      });
      foot.appendChild(saveBtn);
    }
    body.appendChild(foot);
    root.appendChild(body);
    root.addEventListener("mouseenter", cancelClose);
    root.addEventListener("mouseleave", scheduleClose);
    return root;
  };
  const openPopup = (pin: MapPin, sticky: boolean) => {
    const map = mapRef.current;
    const mod = modRef.current;
    if (!map || !mod || pin.longitude == null || pin.latitude == null) return;
    cancelClose();
    // Click giữ popup lại (cảm ứng); hover marker khác thì popup theo hover,
    // đóng khi rời — sticky không kéo dài sang marker kế tiếp.
    stickyPopupRef.current = sticky;
    openPinRef.current = pin.id;
    if (!popupRef.current)
      popupRef.current = new mod.Popup({
        closeButton: false,
        maxWidth: "240px",
        offset: 14,
        className: "map-room-popup",
      });
    popupRef.current
      .setLngLat([pin.longitude, pin.latitude])
      .setDOMContent(buildPopupContent(pin))
      .addTo(map);
  };
  // Khởi tạo bản đồ đúng một lần.
  useEffect(() => {
    let disposed = false;
    (async () => {
      try {
        const maplibregl = await import("maplibre-gl");
        if (disposed || !host.current) return;
        // v6 tách worker khỏi bundle; URL cố định do plugin vite phục vụ/emit.
        if (maplibregl.getWorkerUrl() !== workerHref())
          maplibregl.setWorkerUrl(workerHref());
        modRef.current = maplibregl;
        const key = goongApiKey();
        const map = new maplibregl.Map({
          container: host.current,
          style: key ? goongStyleUrl(key) : OSM_STYLE,
          // Cuộn chuột để phóng/thu nhỏ; kéo chuột để
          // di chuyển vốn bật sẵn. Giới hạn zoom tối đa 17 để không phóng tới
          // mức chỉ còn một con đường, mất định hướng khu vực.
          scrollZoom: true,
          maxZoom: 17,
          attributionControl: { compact: false },
        });
        mapRef.current = map;
        // Fallback chỉ khi style Goong chưa nạp được (fetch lỗi, 401/403, parse
        // lỗi) hoặc quá 20 giây vẫn chưa "load". Lỗi lành tính sau khi load
        // (glyph, tile lẻ) không đổi style — MapLibre tự bỏ qua.
        let styleLoaded = false;
        let swapped = false;
        const swapToOsm = () => {
          if (swapped || disposed) return;
          swapped = true;
          map.setStyle(OSM_STYLE);
        };
        if (key) {
          map.on("error", (event) => {
            if (styleLoaded || swapped || disposed) return;
            // Chỉ swap khi có vẻ là lỗi style/mạng (không phải tile/glyph lẻ
            // sau khi đã load).
            const message = String(
              (event as { error?: { message?: string } }).error?.message ?? "",
            );
            if (
              /style|fetch|network|401|403|unauthorized|parse|Unexpected|WebGL|worker/i.test(
                message,
              )
            )
              swapToOsm();
          });
          window.setTimeout(() => {
            if (!styleLoaded) swapToOsm();
          }, 20000);
        }
        map.on("load", () => {
          styleLoaded = true;
          if (disposed) return;
          setMapReady(true);
          fitToPins();
        });
        // Bấm ra nền bản đồ đóng popup đang mở.
        map.on("click", () => closePopup());
      } catch {
        if (!disposed)
          setError("Không tải được bản đồ; bạn vẫn có thể dùng danh sách.");
      }
    })();
    return () => {
      disposed = true;
      cancelClose();
      popupRef.current?.remove();
      popupRef.current = null;
      markersRef.current.forEach((marker) => marker.remove());
      markersRef.current.clear();
      pinsRef.current.clear();
      anchorMarkerRef.current?.remove();
      anchorMarkerRef.current = null;
      anchorDrawnRef.current = false;
      routeDrawnRef.current = false;
      mapRef.current?.remove();
      mapRef.current = null;
      modRef.current = null;
      setMapReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  // Khung bản đồ đổi chiều rộng (kéo thanh chia cột) không kích hoạt resize của
  // cửa sổ, nên MapLibre phải được báo để vẽ lại canvas cho khớp khung.
  useEffect(() => {
    const el = host.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => mapRef.current?.resize());
    observer.observe(el);
    return () => observer.disconnect();
  }, []);
  // Cập nhật marker tại chỗ theo placed: thêm marker mới, gỡ marker mất,
  // làm mới nhãn giá/trạng thái chọn; không tạo lại bản đồ.
  useEffect(() => {
    const map = mapRef.current;
    const mod = modRef.current;
    if (!map || !mod || !mapReady) return;
    const seen = new Set<string>();
    for (const pin of placed) {
      seen.add(pin.id);
      pinsRef.current.set(pin.id, pin);
      let marker = markersRef.current.get(pin.id);
      if (!marker) {
        const pill = document.createElement("button");
        pill.type = "button";
        pill.className = "map-price-marker";
        const span = document.createElement("span");
        pill.appendChild(span);
        pill.addEventListener("click", (event) => {
          event.stopPropagation();
          // Đọc pin mới nhất: giá/dữ liệu có thể đổi mà marker không được tạo lại.
          const latest = pinsRef.current.get(pin.id);
          if (latest) {
            openPopup(latest, true);
            latestSelect.current?.(latest.id);
          }
        });
        pill.addEventListener("mouseenter", () => {
          const latest = pinsRef.current.get(pin.id);
          if (latest) openPopup(latest, false);
        });
        pill.addEventListener("mouseleave", scheduleClose);
        marker = new mod.Marker({ element: pill })
          .setLngLat([pin.longitude!, pin.latitude!])
          .addTo(map);
        markersRef.current.set(pin.id, marker);
      }
      paintPill(pin.id);
    }
    for (const [id, marker] of markersRef.current) {
      if (seen.has(id)) continue;
      marker.remove();
      markersRef.current.delete(id);
      pinsRef.current.delete(id);
      if (openPinRef.current === id) closePopup();
    }
    // Nạp lại nội dung popup nếu căn đang mở đổi giá/dữ liệu.
    if (openPinRef.current) {
      const openPin = pinsRef.current.get(openPinRef.current);
      const map2 = mapRef.current;
      if (openPin && map2)
        popupRef.current?.setDOMContent(buildPopupContent(openPin));
    }
    // Vừa nạp xong bản đồ hoặc tập toạ độ đổi thì đưa hết marker vào khung.
    const fitKey =
      placed
        .map((pin) => `${pin.id}:${pin.latitude},${pin.longitude}`)
        .join("|") + `#${anchorKey}`;
    if (fitKey !== fitKeyRef.current) {
      fitKeyRef.current = fitKey;
      fitToPins();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [placed, mapReady, anchorKey]);
  // Điểm neo: marker riêng (nhãn nơi khách muốn ở gần) + vòng bán kính tối
  // đa. Cập nhật tại chỗ bằng setData, không tạo lại bản đồ.
  useEffect(() => {
    const map = mapRef.current;
    const mod = modRef.current;
    if (!map || !mod || !mapReady) return;
    if (!anchor) {
      if (anchorDrawnRef.current) {
        for (const id of ANCHOR_LAYERS)
          if (map.getLayer(id)) map.removeLayer(id);
        if (map.getSource(ANCHOR_SOURCE)) map.removeSource(ANCHOR_SOURCE);
        anchorDrawnRef.current = false;
      }
      anchorMarkerRef.current?.remove();
      anchorMarkerRef.current = null;
      return;
    }
    const data = {
      type: "Feature" as const,
      properties: {},
      geometry: {
        type: "Polygon" as const,
        coordinates: [
          circleRing(anchor.latitude, anchor.longitude, anchor.radius_m),
        ],
      },
    };
    const source = map.getSource(ANCHOR_SOURCE) as
      | import("maplibre-gl").GeoJSONSource
      | undefined;
    if (source) source.setData(data);
    else {
      map.addSource(ANCHOR_SOURCE, { type: "geojson", data });
      // Vòng bán kính nằm dưới đường đi nếu đường đi đã có.
      const before = map.getLayer(ROUTE_LAYERS[0])
        ? ROUTE_LAYERS[0]
        : undefined;
      map.addLayer(
        {
          id: ANCHOR_LAYERS[0],
          type: "fill",
          source: ANCHOR_SOURCE,
          paint: { "fill-color": ANCHOR_COLOR, "fill-opacity": 0.07 },
        },
        before,
      );
      map.addLayer(
        {
          id: ANCHOR_LAYERS[1],
          type: "line",
          source: ANCHOR_SOURCE,
          paint: {
            "line-color": ANCHOR_COLOR,
            "line-width": 2,
            "line-opacity": 0.75,
            "line-dasharray": [3, 2],
          },
        },
        before,
      );
      anchorDrawnRef.current = true;
    }
    let marker = anchorMarkerRef.current;
    if (!marker) {
      const el = document.createElement("div");
      el.className = "map-anchor-marker";
      const dot = document.createElement("span");
      dot.className = "map-anchor-dot";
      dot.setAttribute("aria-hidden", "true");
      const label = document.createElement("span");
      label.className = "map-anchor-label";
      el.append(dot, label);
      marker = new mod.Marker({ element: el, anchor: "bottom" }).setLngLat([
        anchor.longitude,
        anchor.latitude,
      ]);
      marker.addTo(map);
      anchorMarkerRef.current = marker;
    } else marker.setLngLat([anchor.longitude, anchor.latitude]);
    const el = marker.getElement() as HTMLElement;
    const label = el.querySelector(".map-anchor-label");
    if (label) label.textContent = anchor.label;
    el.title = `Điểm neo: ${anchor.label} · bán kính ${formatDistance(anchor.radius_m)}`;
    el.setAttribute("aria-label", el.title);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [anchorKey, mapReady]);
  // Đường đi căn đang chọn → điểm neo. Đường thực tế: nét liền xanh có viền
  // trắng; đường chim bay: nét đứt xám. Đổi tuyến thì đưa cả tuyến vào khung.
  useEffect(() => {
    const map = mapRef.current;
    const mod = modRef.current;
    if (!map || !mod || !mapReady) return;
    if (routeDrawnRef.current) {
      for (const id of ROUTE_LAYERS) if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(ROUTE_SOURCE)) map.removeSource(ROUTE_SOURCE);
      routeDrawnRef.current = false;
    }
    if (!route || route.coordinates.length < 2) return;
    map.addSource(ROUTE_SOURCE, {
      type: "geojson",
      data: {
        type: "Feature",
        properties: {},
        geometry: { type: "LineString", coordinates: route.coordinates },
      },
    });
    map.addLayer({
      id: ROUTE_LAYERS[0],
      type: "line",
      source: ROUTE_SOURCE,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: { "line-color": "#ffffff", "line-width": route.straight ? 5 : 8 },
    });
    map.addLayer({
      id: ROUTE_LAYERS[1],
      type: "line",
      source: ROUTE_SOURCE,
      layout: { "line-join": "round", "line-cap": "round" },
      paint: route.straight
        ? {
            "line-color": STRAIGHT_COLOR,
            "line-width": 2.5,
            "line-dasharray": [2, 2],
          }
        : { "line-color": ROUTE_COLOR, "line-width": 4.5 },
    });
    routeDrawnRef.current = true;
    const bounds = new mod.LngLatBounds();
    for (const point of route.coordinates) bounds.extend(point);
    // Khung nhìn chỉ vừa tuyến từ căn tới điểm neo (không ôm cả vòng bán kính)
    // để đường đi hiện rõ; padding đã chừa chỗ cho bảng chỉ đường đè trên bản đồ.
    map.fitBounds(bounds, {
      padding: routePadding(
        host.current?.clientWidth ?? 0,
        host.current?.clientHeight ?? 0,
        overlayRef.current?.offsetWidth ?? 0,
        overlayRef.current?.offsetHeight ?? 0,
      ),
      maxZoom: 16,
      duration: 600,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [routeKey, mapReady]);
  // Đổi selection chỉ tô lại pill hiện có — không đụng bản đồ.
  useEffect(() => {
    if (!mapReady) return;
    for (const id of markersRef.current.keys()) paintPill(id);
  }, [selectedId, mapReady, placedKey]);
  // Đồng bộ trạng thái lưu trong popup khi savedIds đổi ở trang cha.
  useEffect(() => {
    if (!mapReady || !openPinRef.current) return;
    const openPin = pinsRef.current.get(openPinRef.current);
    if (openPin) popupRef.current?.setDOMContent(buildPopupContent(openPin));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [savedIds]);
  const paintPill = (id: string) => {
    const marker = markersRef.current.get(id);
    const pin = pinsRef.current.get(id);
    if (!marker || !pin) return;
    const pill = marker.getElement() as HTMLElement;
    const span = pill.firstElementChild as HTMLElement | null;
    if (!span) return;
    const band = bandFor(pin.monthly);
    const classes = [
      band?.cls ?? "",
      id === selectedRef.current ? "selected" : "",
    ];
    span.className = classes.filter(Boolean).join(" ");
    // Chấm màu theo băng giá (khớp chú giải) đứng trước số tiền.
    const dot = document.createElement("i");
    dot.className = "dot";
    dot.setAttribute("aria-hidden", "true");
    span.replaceChildren(dot, priceShortLabel(pin.monthly));
    pill.title = `${roomTitle(pin.title)} · vị trí gần đúng`;
  };
  const hasLegend = placed.some(
    (pin) => pin.monthly != null && Number.isFinite(pin.monthly),
  );
  return (
    <div className="map-view">
      {error ? (
        <p className="notice warning">{error}</p>
      ) : (
        <div className="map-frame">
          <div ref={host} className="map-canvas" aria-label="Bản đồ tin đăng" />
          {!error && mapReady && (
            <div className="map-overlay-left">
              {/* Sau khi người dùng tự kéo/zoom, nút này đưa hết căn trở lại
                  khung nhìn — gọi lại đúng logic vừa khung ban đầu. */}
              {placed.length > 0 && (
                <button
                  type="button"
                  className="map-fit"
                  aria-label="Vừa khung tất cả căn"
                  title="Đưa tất cả căn phù hợp trở lại khung bản đồ"
                  onClick={() => fitToPins()}
                >
                  Vừa khung
                </button>
              )}
              <div className="map-zoom">
                <button
                  type="button"
                  aria-label="Phóng to bản đồ"
                  onClick={() => mapRef.current?.zoomIn()}
                >
                  +
                </button>
                <button
                  type="button"
                  aria-label="Thu nhỏ bản đồ"
                  onClick={() => mapRef.current?.zoomOut()}
                >
                  −
                </button>
              </div>
              {(hasLegend || anchor) && (
                <div
                  className={`map-legend${legendOpen ? "" : " collapsed"}`}
                  aria-label="Chú giải bản đồ"
                >
                  <button
                    type="button"
                    className="map-legend-toggle"
                    aria-expanded={legendOpen}
                    aria-label={
                      legendOpen ? "Thu gọn chú giải" : "Mở chú giải bản đồ"
                    }
                    title={legendOpen ? "Thu gọn chú giải" : "Mở chú giải"}
                    onClick={toggleLegend}
                  >
                    Chú giải
                    <Icon name="chevron" size={14} />
                  </button>
                  {legendOpen && hasLegend && (
                    <>
                      <strong>Giá (triệu/tháng)</strong>
                      {PRICE_BANDS.map((band) => (
                        <span key={band.cls}>
                          <i className={`dot ${band.cls}`} aria-hidden="true" />
                          {band.label}
                        </span>
                      ))}
                    </>
                  )}
                  {legendOpen && anchor && (
                    <span className="map-legend-anchor">
                      <i className="ring" aria-hidden="true" />
                      Bán kính {formatDistance(anchor.radius_m)} quanh điểm neo
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
          {!error && mapReady && overlay && (
            <div ref={overlayRef} className="map-overlay-right">
              {overlay}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
