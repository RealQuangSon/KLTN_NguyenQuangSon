import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { MapView, type MapPin } from "../components/MapView";
import { RoutePanel, useRoomRoute } from "../components/RoutePanel";
import type { Api } from "../api";
import type { RouteResult } from "../types";
import {
  circleRing,
  formatDistance,
  formatDuration,
  googleDirectionsUrl,
  routePadding,
} from "../map";

// MP-01: điểm neo (nơi khách muốn ở gần) + vòng bán kính + đường đi.
// Mock maplibre-gl ghi lại source/layer để kiểm tra những gì được vẽ.
const state = vi.hoisted(() => ({
  sources: new Map<string, { data: unknown }>(),
  layers: [] as { id: string; paint?: Record<string, unknown> }[],
  fit: [] as unknown[][],
  markers: [] as HTMLElement[],
}));
vi.mock("maplibre-gl", () => {
  class Map {
    container: HTMLElement;
    constructor(options: { container: HTMLElement }) {
      this.container = options.container;
      state.sources.clear();
      state.layers = [];
      state.fit = [];
      state.markers = [];
    }
    on(event: string, cb: () => void) {
      if (event === "load") setTimeout(() => cb(), 0);
    }
    remove() {}
    fitBounds(...args: unknown[]) {
      state.fit.push(args);
    }
    jumpTo() {}
    getSource(id: string) {
      const source = state.sources.get(id);
      return source
        ? {
            setData: (data: unknown) => {
              source.data = data;
            },
          }
        : undefined;
    }
    addSource(id: string, spec: { data: unknown }) {
      state.sources.set(id, { data: spec.data });
    }
    removeSource(id: string) {
      state.sources.delete(id);
    }
    getLayer(id: string) {
      return state.layers.find((layer) => layer.id === id);
    }
    addLayer(
      layer: { id: string; paint?: Record<string, unknown> },
      before?: string,
    ) {
      const index = before
        ? state.layers.findIndex((item) => item.id === before)
        : -1;
      if (index >= 0) state.layers.splice(index, 0, layer);
      else state.layers.push(layer);
    }
    removeLayer(id: string) {
      state.layers = state.layers.filter((layer) => layer.id !== id);
    }
  }
  class Marker {
    element: HTMLElement;
    constructor({ element }: { element: HTMLElement }) {
      this.element = element;
    }
    setLngLat() {
      return this;
    }
    addTo(map: Map) {
      map.container.appendChild(this.element);
      state.markers.push(this.element);
      return this;
    }
    remove() {
      this.element.remove();
    }
    getElement() {
      return this.element;
    }
  }
  class LngLatBounds {
    points: unknown[] = [];
    extend(point: unknown) {
      this.points.push(point);
    }
  }
  class Popup {
    setLngLat() {
      return this;
    }
    setDOMContent() {
      return this;
    }
    addTo() {
      return this;
    }
    remove() {}
  }
  return {
    Map,
    Marker,
    LngLatBounds,
    Popup,
    getWorkerUrl: () => "",
    setWorkerUrl: () => {},
  };
});
const pin: MapPin = {
  id: "room-1",
  title: "Phòng gần Bách Khoa",
  latitude: 21.0123,
  longitude: 105.8456,
  uncertainty_m: 200,
  location_accuracy: "approximate",
  monthly: 3_200_000,
};
const anchor = {
  label: "Đại học Bách Khoa Hà Nội",
  latitude: 21.004,
  longitude: 105.8431,
  radius_m: 1500,
};
const routeResult = (over: Partial<RouteResult> = {}): RouteResult => ({
  run_id: "run-1",
  room_id: "room-1",
  travel: "ride",
  provider: "goong",
  vehicle: "motorbike",
  distance_m: 3200,
  duration_s: 660,
  straight_line_m: 1010,
  geometry: {
    type: "LineString",
    coordinates: [
      [105.8456, 21.0123],
      [105.844, 21.008],
      [105.8431, 21.004],
    ],
  },
  origin: {
    latitude: 21.0123,
    longitude: 105.8456,
    location_accuracy: "approximate",
    uncertainty_m: 300,
  },
  anchor: {
    label: anchor.label,
    latitude: anchor.latitude,
    longitude: anchor.longitude,
    max_distance_m: 1500,
    uncertainty_m: 300,
  },
  attribution: "Đường đi © Goong",
  fallback_reason: null,
  ...over,
});

it("formats distance, duration and the radius ring", () => {
  expect(formatDistance(843)).toBe("840 m");
  expect(formatDistance(1500)).toBe("1,5 km");
  expect(formatDistance(3000)).toBe("3 km");
  expect(formatDuration(660)).toBe("11 phút");
  expect(formatDuration(3900)).toBe("1 giờ 5 phút");
  const ring = circleRing(21, 105.8, 1000, 8);
  expect(ring).toHaveLength(9);
  expect(ring[0]).toEqual(ring[8]);
  // Điểm phía bắc cách tâm ~1000 m theo vĩ độ.
  expect((ring[2][1] - 21) * 111_320).toBeCloseTo(1000, 0);
  expect(
    googleDirectionsUrl(
      { latitude: 21.01, longitude: 105.84 },
      { latitude: 21.004, longitude: 105.8431 },
      "walk",
    ),
  ).toBe(
    "https://www.google.com/maps/dir/?api=1&origin=21.01%2C105.84&destination=21.004%2C105.8431&travelmode=walking",
  );
});

it("leaves room for the route panel on the side that keeps more map", () => {
  // Khung rộng: chừa lề phải bằng bảng (272 + 30).
  expect(routePadding(900, 600, 272, 260)).toEqual({
    top: 70,
    bottom: 70,
    left: 70,
    right: 302,
  });
  // Khung hẹp mà cao (đang mở chi tiết căn): đẩy xuống dưới bảng.
  expect(routePadding(447, 805, 272, 265)).toEqual({
    top: 295,
    bottom: 70,
    left: 70,
    right: 70,
  });
  // Quá nhỏ: lề mỏng, chấp nhận bảng che một phần.
  expect(routePadding(200, 200, 180, 150)).toEqual({
    top: 20,
    bottom: 20,
    left: 20,
    right: 20,
  });
  // Chưa đo được khung (jsdom): lề mặc định.
  expect(routePadding(0, 0, 0, 0).right).toBe(70);
});

it("draws the anchor marker, radius ring and legend without a route", async () => {
  render(<MapView pins={[pin]} anchor={anchor} />);
  await waitFor(() => expect(state.sources.has("hm-anchor-radius")).toBe(true));
  expect(state.layers.map((layer) => layer.id)).toEqual([
    "hm-anchor-fill",
    "hm-anchor-line",
  ]);
  const ring = state.sources.get("hm-anchor-radius")!.data as {
    geometry: { type: string; coordinates: number[][][] };
  };
  expect(ring.geometry.type).toBe("Polygon");
  expect(ring.geometry.coordinates[0]).toHaveLength(65);
  const marker = state.markers.find((el) =>
    el.classList.contains("map-anchor-marker"),
  );
  expect(marker?.textContent).toBe(anchor.label);
  expect(marker?.getAttribute("aria-label")).toBe(
    "Điểm neo: Đại học Bách Khoa Hà Nội · bán kính 1,5 km",
  );
  expect(
    screen.getByText("Bán kính 1,5 km quanh điểm neo"),
  ).toBeInTheDocument();
  // Khung nhìn ôm cả căn và 4 điểm cực của vòng bán kính.
  const bounds = state.fit.at(-1)?.[0] as { points: unknown[] };
  expect(bounds.points.length).toBe(1 + 5);
  expect(state.sources.has("hm-route")).toBe(false);
});

it("draws the road route, switches to a dashed straight line, then clears it", async () => {
  const road = {
    coordinates: routeResult().geometry.coordinates,
    straight: false,
  };
  const view = render(<MapView pins={[pin]} anchor={anchor} route={road} />);
  await waitFor(() => expect(state.sources.has("hm-route")).toBe(true));
  // Đường đi nằm trên vòng bán kính.
  expect(state.layers.map((layer) => layer.id)).toEqual([
    "hm-anchor-fill",
    "hm-anchor-line",
    "hm-route-casing",
    "hm-route-line",
  ]);
  const line = () => state.layers.find((layer) => layer.id === "hm-route-line");
  expect(line()?.paint?.["line-dasharray"]).toBeUndefined();
  // Khung nhìn khi có tuyến chỉ vừa các điểm của tuyến (không ôm vòng bán kính)
  // để đường từ căn tới điểm neo hiện rõ.
  const routeFit = state.fit.at(-1)?.[0] as { points: unknown[] };
  expect(routeFit.points).toHaveLength(3);
  view.rerender(
    <MapView
      pins={[pin]}
      anchor={anchor}
      route={{
        ...road,
        coordinates: [road.coordinates[0], road.coordinates[2]],
        straight: true,
      }}
    />,
  );
  await waitFor(() =>
    expect(line()?.paint?.["line-dasharray"]).toEqual([2, 2]),
  );
  view.rerender(<MapView pins={[pin]} anchor={anchor} route={null} />);
  await waitFor(() => expect(state.sources.has("hm-route")).toBe(false));
  expect(state.layers.map((layer) => layer.id)).toEqual([
    "hm-anchor-fill",
    "hm-anchor-line",
  ]);
  view.rerender(<MapView pins={[pin]} anchor={null} route={null} />);
  await waitFor(() =>
    expect(state.sources.has("hm-anchor-radius")).toBe(false),
  );
  expect(document.querySelector(".map-anchor-marker")).toBeNull();
});

it("shows the hint until a room is picked, then the server route", async () => {
  const onTravel = vi.fn();
  const onClose = vi.fn();
  const idle = { route: null, loading: false, error: null };
  const view = render(
    <RoutePanel
      anchor={anchor}
      roomAddress={null}
      state={idle}
      travel="ride"
      onTravel={onTravel}
      onClose={onClose}
    />,
  );
  expect(
    screen.getByText(/bán kính 1,5 km bạn muốn ở gần/),
  ).toBeInTheDocument();
  view.rerender(
    <RoutePanel
      anchor={anchor}
      roomAddress="Phòng gần Bách Khoa"
      state={{ route: routeResult(), loading: false, error: null }}
      travel="ride"
      onTravel={onTravel}
      onClose={onClose}
    />,
  );
  expect(screen.getByText("3,2 km · ~11 phút")).toBeInTheDocument();
  // Bảng chỉ còn điểm neo, căn xuất phát, phương tiện và một dòng khoảng cách.
  expect(screen.queryByText("Đi xe máy")).not.toBeInTheDocument();
  expect(screen.queryByText(/Chim bay 1 km/)).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: /Google Maps/ })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Đi bộ" }));
  expect(onTravel).toHaveBeenCalledWith("walk");
  await userEvent.click(screen.getByRole("button", { name: "Ẩn đường đi" }));
  expect(onClose).toHaveBeenCalled();
});

it("labels the straight-line fallback and never shows minutes for it", () => {
  render(
    <RoutePanel
      anchor={anchor}
      roomAddress="Phòng gần Bách Khoa"
      state={{
        route: routeResult({
          provider: "straight_line",
          vehicle: null,
          duration_s: null,
          distance_m: 1010,
          attribution: null,
          fallback_reason: "provider_error",
        }),
        loading: false,
        error: null,
      }}
      travel="ride"
      onTravel={() => {}}
      onClose={() => {}}
    />,
  );
  expect(screen.getByText("Chim bay ~1 km")).toBeInTheDocument();
  expect(screen.queryByText(/phút/)).toBeNull();
});

it("loads a route once per run, room and travel mode", async () => {
  const get = vi.fn().mockResolvedValue(routeResult());
  const api = { get } as unknown as Api;
  const hook = renderHook(
    ({ room, travel }: { room: string | null; travel: "ride" | "walk" }) =>
      useRoomRoute(api, "s-1", room, "run-1", travel),
    { initialProps: { room: "room-1", travel: "ride" } },
  );
  await waitFor(() =>
    expect(hook.result.current.route?.room_id).toBe("room-1"),
  );
  expect(get).toHaveBeenCalledWith(
    "/sessions/s-1/rooms/room-1/route?travel=ride",
    expect.any(AbortSignal),
  );
  hook.rerender({ room: null, travel: "ride" });
  expect(hook.result.current.route).toBeNull();
  hook.rerender({ room: "room-1", travel: "ride" });
  expect(hook.result.current.route?.room_id).toBe("room-1");
  expect(get).toHaveBeenCalledTimes(1);
  get.mockResolvedValueOnce(routeResult({ travel: "walk", vehicle: "foot" }));
  hook.rerender({ room: "room-1", travel: "walk" });
  await waitFor(() => expect(hook.result.current.route?.vehicle).toBe("foot"));
  expect(get).toHaveBeenCalledTimes(2);
});
