import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api, ApiError } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import type {
  Results,
  RouteResult,
  RouteSummary,
  Session,
  SessionRoutesResult,
} from "../types";
import { profile, room, session } from "./fixtures";

// dòng "x km · ~y phút tới điểm neo" trên thẻ căn và bảng so sánh.
// Mock maplibre-gl như map-anchor-route.test.tsx để bản đồ trong workspace dựng
// marker/điểm neo mà không cần tile thật; bấm marker chọn được căn.
vi.mock("maplibre-gl", () => {
  class Map {
    container: HTMLElement;
    constructor(options: { container: HTMLElement }) {
      this.container = options.container;
    }
    on(event: string, cb: () => void) {
      if (event === "load") setTimeout(() => cb(), 0);
    }
    remove() {}
    fitBounds() {}
    jumpTo() {}
    getSource() {
      return { setData: () => {} };
    }
    addSource() {}
    removeSource() {}
    getLayer() {
      return undefined;
    }
    addLayer() {}
    removeLayer() {}
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
    extend() {}
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
const ANCHOR_LABEL = "Đại học Bách Khoa";
const anchoredSession = (): Session => ({
  ...session(),
  confirmed_profile: {
    ...profile,
    destination: {
      label: ANCHOR_LABEL,
      latitude: 21.004,
      longitude: 105.8431,
      uncertainty_m: 300,
      max_distance_m: 1500,
    },
  },
});
const published = (rooms: ReturnType<typeof room>[]): Results => ({
  session_id: "session-1",
  run_id: "run-1",
  status: "published",
  results: rooms,
});
// Căn có tọa độ để bản đồ dựng marker (fixture mặc định không vĩ/kinh độ).
const pinnedRoom = (id: string) => ({
  ...room(id),
  latitude: 21.0123,
  longitude: 105.8456,
  location_accuracy: "approximate" as const,
  uncertainty_m: 200,
});
const summary = (
  roomId: string,
  over: Partial<RouteSummary> = {},
): RouteSummary => ({
  room_id: roomId,
  travel: "ride",
  provider: "goong",
  vehicle: "motorbike",
  distance_m: 1100,
  duration_s: 120,
  straight_line_m: 900,
  fallback_reason: null,
  ...over,
});
const routesPayload = (
  over: Partial<SessionRoutesResult> = {},
): SessionRoutesResult => ({
  run_id: "run-1",
  travel: "ride",
  anchor: {
    label: ANCHOR_LABEL,
    latitude: 21.004,
    longitude: 105.8431,
    max_distance_m: 1500,
    uncertainty_m: 300,
  },
  items: [],
  skipped: [],
  attribution: null,
  ...over,
});
const roomRouteResult = (travel: "ride" | "walk"): RouteResult => ({
  run_id: "run-1",
  room_id: "r-1",
  travel,
  provider: "goong",
  vehicle: travel === "ride" ? "motorbike" : "foot",
  distance_m: 1100,
  duration_s: 120,
  straight_line_m: 900,
  geometry: {
    type: "LineString",
    coordinates: [
      [105.8456, 21.0123],
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
    label: ANCHOR_LABEL,
    latitude: 21.004,
    longitude: 105.8431,
    max_distance_m: 1500,
    uncertainty_m: 300,
  },
  attribution: null,
  fallback_reason: null,
});
const travelOf = (path: string): "ride" | "walk" =>
  path.endsWith("travel=walk") ? "walk" : "ride";
// Dựng workspace kiểu renter-state.test.tsx: spy api.get trả phiên/kết quả và
// ghi lại mỗi lời gọi /routes của phiên; post phục vụ nút so sánh.
const mountWorkspace = (options: {
  current: Session;
  results: Results;
  routes?: (travel: "ride" | "walk") => Promise<SessionRoutesResult>;
  roomRoute?: (travel: "ride" | "walk") => Promise<RouteResult>;
}) => {
  const api = new Api("test");
  sessionStorage.setItem(
    "homematch.session.renter",
    options.current.session_id,
  );
  const routesCalls: string[] = [];
  vi.spyOn(api, "get").mockImplementation(async (path: string) => {
    if (path.endsWith("/results")) return options.results as never;
    if (path.startsWith(`/sessions/${options.current.session_id}/routes`)) {
      routesCalls.push(path);
      if (!options.routes) throw new ApiError(0, "unset", "Chưa dựng mock.");
      return (await options.routes(travelOf(path))) as never;
    }
    if (path.includes("/rooms/") && path.includes("/route?")) {
      if (!options.roomRoute) throw new ApiError(0, "unset", "Chưa dựng mock.");
      return (await options.roomRoute(travelOf(path))) as never;
    }
    return options.current as never;
  });
  vi.spyOn(api, "post").mockImplementation(
    async (_path, body) =>
      ({
        run_id: "run-1",
        items: ((body as { room_ids?: string[] }).room_ids ?? []).map((id) =>
          room(id),
        ),
      }) as never,
  );
  render(
    <RenterWorkspace
      api={api}
      actor={{ id: "renter", role: "renter" }}
      tab="search"
    />,
  );
  return { routesCalls };
};

it("fetches one /routes request for the whole grid and shows km · minutes on each card", async () => {
  const { routesCalls } = mountWorkspace({
    current: anchoredSession(),
    results: published([room("r-1"), room("r-2"), room("r-3")]),
    routes: async () =>
      routesPayload({
        items: [
          summary("r-1"),
          summary("r-2", { distance_m: 2300, duration_s: 480 }),
        ],
        skipped: ["r-3"],
        attribution: "Đường đi © Goong",
      }),
  });
  await screen.findByText("Phòng riêng r-1");
  expect(
    await screen.findByText("1,1 km · ~2 phút tới Đại học Bách Khoa"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("2,3 km · ~8 phút tới Đại học Bách Khoa"),
  ).toBeInTheDocument();
  // Thẻ hẹp cắt mất tên điểm neo: tooltip mang cả dòng kèm ghi chú loại xe.
  expect(
    screen
      .getByText("1,1 km · ~2 phút tới Đại học Bách Khoa")
      .getAttribute("title"),
  ).toMatch(/^1,1 km · ~2 phút tới Đại học Bách Khoa\. \S/);
  // Căn chỉ biết khu vực: không bịa số, ghi rõ chưa tính được đường.
  expect(
    screen.getByText("Chưa rõ vị trí căn, chưa tính đường"),
  ).toBeInTheDocument();
  // Ghi công nguồn chỉ đường của cả danh sách nằm dưới lưới, một dòng nhỏ.
  expect(screen.getByText("Đường đi © Goong")).toBeInTheDocument();
  // Nhiều thẻ nhưng cả danh sách chỉ một request /routes cho chế độ đi xe.
  expect(routesCalls).toEqual(["/sessions/session-1/routes?travel=ride"]);
}, 20000);

it("shows the straight-line distance without minutes when the provider falls back", async () => {
  mountWorkspace({
    current: anchoredSession(),
    results: published([room("r-1")]),
    routes: async () =>
      routesPayload({
        items: [
          summary("r-1", {
            provider: "straight_line",
            vehicle: null,
            distance_m: 1200,
            duration_s: null,
            fallback_reason: "provider_error",
          }),
        ],
      }),
  });
  await screen.findByText("Phòng riêng r-1");
  const line = await screen.findByText(
    "~1,2 km chim bay tới Đại học Bách Khoa",
  );
  // Tooltip: cả dòng + lý do rơi về chim bay.
  expect(line.getAttribute("title")).toMatch(
    /^~1,2 km chim bay tới Đại học Bách Khoa\. \S/,
  );
  // Đường chim bay không bao giờ có số phút ước lượng.
  expect(document.querySelector(".room-mini-route")?.textContent).not.toMatch(
    /phút/,
  );
}, 20000);

it("never calls /routes when the profile has no anchor", async () => {
  const { routesCalls } = mountWorkspace({
    current: session(), // fixture mặc định: destination null.
    results: published([room("r-1"), room("r-2")]),
    routes: async () => routesPayload(),
  });
  await screen.findByText("Phòng riêng r-1");
  await screen.findByText("Phòng riêng r-2");
  expect(routesCalls).toEqual([]);
  expect(document.querySelector(".room-mini-route")).toBeNull();
}, 20000);

it("keeps the cards intact when /routes fails with 422 or 500", async () => {
  for (const status of [422, 500] as const) {
    mountWorkspace({
      current: anchoredSession(),
      results: published([room("r-1"), room("r-2")]),
      routes: async () => {
        throw new ApiError(status, "no_destination", "Hồ sơ chưa có điểm neo.");
      },
    });
    await screen.findByText("Phòng riêng r-1");
    await screen.findByText("Phòng riêng r-2");
    // Không có dòng đường đi, thẻ vẫn nguyên vẹn, không vỡ trang.
    expect(document.querySelectorAll(".room-mini-route")).toHaveLength(0);
    expect(screen.queryByText(/chim bay/)).toBeNull();
    expect(screen.queryByText(/Tới Đại học Bách Khoa/)).toBeNull();
    cleanup();
  }
}, 20000);

it("switches the whole grid to walk from the route panel and back to the cached ride data", async () => {
  const ride = routesPayload({
    items: [
      summary("r-1"),
      summary("r-2", { distance_m: 2300, duration_s: 480 }),
    ],
  });
  const walk = routesPayload({
    travel: "walk",
    items: [
      summary("r-1", {
        travel: "walk",
        vehicle: "foot",
        distance_m: 1300,
        duration_s: 900,
      }),
      summary("r-2", {
        travel: "walk",
        vehicle: "foot",
        distance_m: 2500,
        duration_s: 1800,
      }),
    ],
  });
  const { routesCalls } = mountWorkspace({
    current: anchoredSession(),
    results: published([pinnedRoom("r-1"), pinnedRoom("r-2")]),
    roomRoute: async (travel) => roomRouteResult(travel),
    routes: async (travel) => (travel === "walk" ? walk : ride),
  });
  await screen.findByText("1,1 km · ~2 phút tới Đại học Bách Khoa");
  // Bấm một marker để bảng chỉ đường hiện nút chế độ đi dùng chung.
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(2),
  );
  await userEvent.click(document.querySelectorAll(".map-price-marker")[0]);
  await userEvent.click(screen.getByRole("button", { name: "Đi bộ" }));
  expect(
    await screen.findByText("1,3 km · ~15 phút tới Đại học Bách Khoa"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("2,5 km · ~30 phút tới Đại học Bách Khoa"),
  ).toBeInTheDocument();
  expect(routesCalls).toEqual([
    "/sessions/session-1/routes?travel=ride",
    "/sessions/session-1/routes?travel=walk",
  ]);
  // Quay lại "Đi xe": dùng bản đã nhớ trong phiên trang, không gọi lại máy chủ.
  await userEvent.click(screen.getByRole("button", { name: "Đi xe" }));
  expect(
    await screen.findByText("1,1 km · ~2 phút tới Đại học Bách Khoa"),
  ).toBeInTheDocument();
  expect(routesCalls).toHaveLength(2);
}, 20000);

it("draws a route only after a marker click, never from opening a card", async () => {
  const roomRouteCalls: string[] = [];
  mountWorkspace({
    current: anchoredSession(),
    results: published([pinnedRoom("r-1"), pinnedRoom("r-2")]),
    routes: async () =>
      routesPayload({ items: [summary("r-1"), summary("r-2")] }),
    roomRoute: async (travel) => {
      roomRouteCalls.push(travel);
      return roomRouteResult(travel);
    },
  });
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(2),
  );
  const hint = /Bấm một căn trên bản đồ để xem đường đi/;
  expect(screen.getByText(hint)).toBeInTheDocument();
  // Bấm marker r-2: khách chủ động muốn xem đường → lấy và vẽ đường đi.
  await userEvent.click(document.querySelectorAll(".map-price-marker")[1]);
  await waitFor(() => expect(roomRouteCalls).toEqual(["ride"]));
  expect(
    screen.getByRole("button", { name: "Ẩn đường đi" }),
  ).toBeInTheDocument();
  // Bấm thẻ r-1: chỉ mở chi tiết; đường của r-2 bị gỡ, không gọi đường r-1.
  await userEvent.click(
    document.querySelector('article[data-room-id="r-1"]') as HTMLElement,
  );
  await waitFor(() => expect(screen.getByText(hint)).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "Ẩn đường đi" })).toBeNull();
  expect(roomRouteCalls).toEqual(["ride"]);
  // Bấm marker r-1 trên bản đồ mới vẽ đường cho r-1; "Ẩn đường đi" gỡ lại.
  await userEvent.click(document.querySelectorAll(".map-price-marker")[0]);
  await waitFor(() => expect(roomRouteCalls).toEqual(["ride", "ride"]));
  await userEvent.click(screen.getByRole("button", { name: "Ẩn đường đi" }));
  expect(screen.getByText(hint)).toBeInTheDocument();
}, 20000);

it("adds the anchor row to the comparison table with each room's numbers", async () => {
  mountWorkspace({
    current: anchoredSession(),
    results: published([room("r-1"), room("r-2"), room("r-3")]),
    routes: async () =>
      routesPayload({
        items: [
          summary("r-1"),
          summary("r-2", { distance_m: 2300, duration_s: 480 }),
        ],
        skipped: ["r-3"],
      }),
  });
  await screen.findByText("1,1 km · ~2 phút tới Đại học Bách Khoa");
  const pick = await screen.findAllByRole("button", {
    name: /^So sánh căn này$/,
  });
  await userEvent.click(pick[0]);
  await userEvent.click(pick[1]);
  await userEvent.click(pick[2]);
  await userEvent.click(
    screen.getByRole("button", { name: "So sánh lựa chọn" }),
  );
  const head = await screen.findByText("Tới Đại học Bách Khoa (đi xe)");
  const row = head.closest("tr") as HTMLElement;
  // Số của từng căn đúng theo máy chủ trả; ô không lặp "tới {điểm neo}".
  expect(within(row).getByText("1,1 km · ~2 phút")).toBeInTheDocument();
  expect(within(row).getByText("2,3 km · ~8 phút")).toBeInTheDocument();
  expect(within(row).getByText("Chưa rõ vị trí")).toBeInTheDocument();
  expect(row.textContent).not.toContain("tới Đại học Bách Khoa");
  // Thời gian đi không phải tiêu chí xếp hạng: hàng này không có "Tốt nhất".
  expect(within(row).queryByText("Tốt nhất")).toBeNull();
}, 20000);
