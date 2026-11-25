import { useEffect, useRef, useState } from "react";
import { ApiError, type Api } from "../api";
import type {
  RouteResult,
  RouteSummary,
  RouteTravel,
  SessionRoutesResult,
} from "../types";
import { formatDistance, formatDuration } from "../map";
import type { MapAnchor } from "./MapView";
// MP-01: bảng chỉ đường trên bản đồ workspace. Đường đi, quãng đường và thời
// gian do máy chủ trả (Goong/OSRM hoặc đường chim bay khi không có nguồn);
// giao diện chỉ định dạng, không tự ước lượng số phút.
export type RouteState = {
  route: RouteResult | null;
  loading: boolean;
  error: string | null;
};
const IDLE: RouteState = { route: null, loading: false, error: null };
// Tải đường đi căn → điểm neo; nhớ theo run + căn + chế độ trong phiên trang
// để bấm qua lại giữa các căn không gọi lại máy chủ. Bản đường chim bay do lỗi
// nguồn/hạn mức không nhớ, lần chọn sau thử lại.
export function useRoomRoute(
  api: Api,
  sessionId: string | null,
  roomId: string | null,
  runId: string | null,
  travel: RouteTravel,
): RouteState {
  const cache = useRef(new Map<string, RouteResult>());
  const [state, setState] = useState<RouteState>(IDLE);
  useEffect(() => {
    if (!sessionId || !roomId) {
      setState(IDLE);
      return;
    }
    const key = `${runId ?? ""}|${roomId}|${travel}`;
    const hit = cache.current.get(key);
    if (hit) {
      setState({ route: hit, loading: false, error: null });
      return;
    }
    const controller = new AbortController();
    setState({ route: null, loading: true, error: null });
    api
      .get<RouteResult>(
        `/sessions/${encodeURIComponent(sessionId)}/rooms/${encodeURIComponent(roomId)}/route?travel=${travel}`,
        controller.signal,
      )
      .then((route) => {
        if (controller.signal.aborted) return;
        if (
          route.fallback_reason !== "provider_error" &&
          route.fallback_reason !== "rate_limited"
        )
          cache.current.set(key, route);
        setState({ route, loading: false, error: null });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setState({
          route: null,
          loading: false,
          error:
            error instanceof ApiError
              ? error.message
              : "Không tải được đường đi.",
        });
      });
    return () => controller.abort();
  }, [api, sessionId, roomId, runId, travel]);
  return state;
}
// quãng đường/thời gian của CẢ danh sách kết quả tới điểm neo bằng
// một request /routes cho mỗi cặp (lượt tìm, chế độ đi). Nhớ theo run + chế độ
// trong phiên trang như useRoomRoute; bản có căn lỗi nguồn/hạn mức không nhớ
// để lần sau thử lại.
export type SessionRoutesState = {
  byRoom: Map<string, RouteSummary> | null;
  skipped: string[];
  attribution: string | null;
  loading: boolean;
  error: string | null;
};
const SESSION_ROUTES_IDLE: SessionRoutesState = {
  byRoom: null,
  skipped: [],
  attribution: null,
  loading: false,
  error: null,
};
export function useSessionRoutes(
  api: Api,
  sessionId: string | null,
  runId: string | null,
  travel: RouteTravel,
  enabled: boolean,
): SessionRoutesState {
  const cache = useRef(new Map<string, SessionRoutesResult>());
  const [state, setState] = useState<SessionRoutesState>(SESSION_ROUTES_IDLE);
  useEffect(() => {
    if (!enabled || !sessionId || !runId) {
      setState(SESSION_ROUTES_IDLE);
      return;
    }
    const key = `${runId}|${travel}`;
    const hit = cache.current.get(key);
    if (hit) {
      setState({
        byRoom: new Map(hit.items.map((item) => [item.room_id, item])),
        skipped: hit.skipped,
        attribution: hit.attribution,
        loading: false,
        error: null,
      });
      return;
    }
    const controller = new AbortController();
    setState({ ...SESSION_ROUTES_IDLE, loading: true });
    api
      .get<SessionRoutesResult>(
        `/sessions/${encodeURIComponent(sessionId)}/routes?travel=${travel}`,
        controller.signal,
      )
      .then((payload) => {
        if (controller.signal.aborted) return;
        const transient = payload.items.some(
          (item) =>
            item.fallback_reason === "provider_error" ||
            item.fallback_reason === "rate_limited",
        );
        if (!transient) cache.current.set(key, payload);
        setState({
          byRoom: new Map(payload.items.map((item) => [item.room_id, item])),
          skipped: payload.skipped,
          attribution: payload.attribution,
          loading: false,
          error: null,
        });
      })
      .catch((error) => {
        if (controller.signal.aborted) return;
        setState({
          byRoom: null,
          skipped: [],
          attribution: null,
          loading: false,
          error:
            error instanceof ApiError
              ? error.message
              : "Không tải được đường đi.",
        });
      });
    return () => controller.abort();
  }, [api, sessionId, runId, travel, enabled]);
  return state;
}
export const vehicleText: Record<
  NonNullable<RouteResult["vehicle"]>,
  string
> = {
  motorbike: "Đi xe máy",
  car: "Theo đường ô tô, thời gian chưa tính kẹt xe",
  foot: "Đi bộ",
};
export const fallbackText: Record<
  NonNullable<RouteResult["fallback_reason"]>,
  string
> = {
  no_provider: "Chưa bật nguồn chỉ đường; đang hiện đường chim bay.",
  provider_error:
    "Chưa lấy được đường đi thực tế lúc này; đang hiện đường chim bay.",
  rate_limited:
    "Bạn đã xem nhiều đường đi trong giờ qua; tạm hiện đường chim bay.",
};
// một dòng số liệu đường đi tới điểm neo cho thẻ căn và bảng so sánh.
// Đường thật hiện "1,1 km · ~2 phút tới {điểm neo}" (bỏ phút khi duration_s
// null); chim bay luôn không có phút. Bỏ anchorLabel (ô bảng so sánh) thì chỉ
// còn phần số liệu, không lặp "tới …". Tooltip mang cả dòng đầy đủ (thẻ hẹp cắt
// mất tên điểm neo) kèm ghi chú xe/lý do chim bay.
export function RouteLine({
  summary,
  anchorLabel,
}: {
  summary: RouteSummary;
  anchorLabel?: string;
}) {
  const target = anchorLabel ? ` tới ${anchorLabel}` : "";
  const straight = summary.provider === "straight_line";
  const text = straight
    ? `~${formatDistance(summary.distance_m)} chim bay${target}`
    : `${formatDistance(summary.distance_m)}${
        summary.duration_s != null
          ? ` · ~${formatDuration(summary.duration_s)}`
          : ""
      }${target}`;
  const note = straight
    ? summary.fallback_reason
      ? fallbackText[summary.fallback_reason]
      : null
    : summary.vehicle
      ? vehicleText[summary.vehicle]
      : null;
  return <span title={note ? `${text}. ${note}` : text}>{text}</span>;
}
// Icon Material (Apache 2.0): xe chạy trên đường và người đi bộ.
const travelIcons: Record<RouteTravel, string> = {
  ride: "M18.92 6.01C18.72 5.42 18.16 5 17.5 5h-11c-.66 0-1.21.42-1.42 1.01L3 12v8c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-1h12v1c0 .55.45 1 1 1h1c.55 0 1-.45 1-1v-8l-2.08-5.99zM6.5 16c-.83 0-1.5-.67-1.5-1.5S5.67 13 6.5 13s1.5.67 1.5 1.5S7.33 16 6.5 16zm11 0c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zM5 11l1.5-4.5h11L19 11H5z",
  walk: "M13.5 5.5c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zM9.8 8.9L7 23h2.1l1.8-8 2.1 2v6h2v-7.5l-2.1-2 .6-3C14.8 12 16.8 13 19 13v-2c-1.9 0-3.5-1-4.3-2.4l-1-1.6c-.4-.6-1-1-1.7-1-.3 0-.5.1-.8.1L6 8.3V13h2V9.6l1.8-.7",
};
export function RoutePanel({
  anchor,
  roomAddress,
  state,
  travel,
  onTravel,
  onClose,
}: {
  anchor: MapAnchor;
  // Địa chỉ căn đang chọn; null = chưa chọn căn nào.
  roomAddress: string | null;
  state: RouteState;
  travel: RouteTravel;
  onTravel: (travel: RouteTravel) => void;
  onClose: () => void;
}) {
  const { route, loading, error } = state;
  // Thu gọn: chỉ còn dòng điểm neo, để lộ bản đồ; nhớ lựa chọn trong trình duyệt.
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem("homematch.routePanel") !== "closed";
    } catch {
      return true;
    }
  });
  const toggle = () =>
    setOpen((value) => {
      try {
        localStorage.setItem("homematch.routePanel", value ? "closed" : "open");
      } catch {
        // Không lưu được: lựa chọn chỉ giữ trong phiên này.
      }
      return !value;
    });
  return (
    <section
      className={`route-panel${open ? "" : " collapsed"}`}
      aria-label="Chỉ đường tới điểm neo"
    >
      <header className="route-panel-head">
        <span className="route-panel-anchor">
          <i aria-hidden="true" />
          <span>
            <small>Điểm neo</small>
            <strong title={anchor.label}>{anchor.label}</strong>
          </span>
        </span>
        <span className="route-panel-actions">
          <button
            type="button"
            className="route-panel-toggle"
            aria-expanded={open}
            aria-label={open ? "Thu gọn bảng chỉ đường" : "Mở bảng chỉ đường"}
            title={open ? "Thu gọn" : "Mở rộng"}
            onClick={toggle}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M9 5l7 7-7 7" />
            </svg>
          </button>
          {roomAddress && (
            <button
              type="button"
              className="route-panel-close"
              aria-label="Ẩn đường đi"
              title="Ẩn đường đi"
              onClick={onClose}
            >
              ×
            </button>
          )}
        </span>
      </header>
      {!open ? null : !roomAddress ? (
        <p className="route-panel-hint">
          Vòng tròn là bán kính {formatDistance(anchor.radius_m)} bạn muốn ở
          gần. Bấm một căn trên bản đồ để xem đường đi tới đây.
        </p>
      ) : (
        <>
          <p className="route-panel-room" title={roomAddress}>
            Từ <strong>{roomAddress}</strong>
          </p>
          <div className="segmented route-panel-modes" role="group">
            {(
              [
                ["ride", "Đi xe"],
                ["walk", "Đi bộ"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={travel === value ? "choice active" : "choice"}
                aria-pressed={travel === value}
                aria-label={label}
                title={label}
                onClick={() => onTravel(value)}
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <path d={travelIcons[value]} />
                </svg>
              </button>
            ))}
          </div>
          {loading ? (
            <p className="route-panel-status" role="status">
              Đang tìm đường…
            </p>
          ) : error ? (
            <p className="route-panel-status warning" role="alert">
              {error}
            </p>
          ) : route ? (
            <div className="route-panel-body" aria-live="polite">
              <p className="route-panel-main">
                {route.provider === "straight_line"
                  ? `Chim bay ~${formatDistance(route.distance_m)}`
                  : `${formatDistance(route.distance_m)}${
                      route.duration_s != null
                        ? ` · ~${formatDuration(route.duration_s)}`
                        : ""
                    }`}
              </p>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
