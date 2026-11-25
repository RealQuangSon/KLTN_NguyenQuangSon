import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { MapView, type MapPin } from "../components/MapView";

// Mock maplibre-gl: đếm số instance bản đồ/marker, ghi lại handler "load" và
// phát ngay để marker effect chạy như trình duyệt thật.
const created = vi.hoisted(() => ({
  maps: 0,
  markers: 0,
  zoom: [] as string[],
  options: null as
    | (Record<string, unknown> & { container: HTMLElement })
    | null,
  fit: [] as unknown[][],
}));
vi.mock("maplibre-gl", () => {
  class Map {
    container: HTMLElement;
    constructor(options: { container: HTMLElement } & Record<string, unknown>) {
      this.container = options.container;
      created.options = options;
      created.maps += 1;
    }
    on(_event: string, cb: () => void) {
      // Style nạp xong ngay: marker effect chạy như khi style thật load.
      if (_event === "load") setTimeout(() => cb(), 0);
    }
    remove() {}
    fitBounds(...args: unknown[]) {
      created.fit.push(args);
    }
    jumpTo() {}
    zoomIn() {
      created.zoom.push("in");
    }
    zoomOut() {
      created.zoom.push("out");
    }
  }
  class Marker {
    element: HTMLElement;
    constructor({ element }: { element: HTMLElement }) {
      this.element = element;
      created.markers += 1;
    }
    setLngLat() {
      return this;
    }
    addTo(map: Map) {
      // Như bản đồ thật: element marker nằm trong DOM container.
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
    content: HTMLElement | null = null;
    setLngLat() {
      return this;
    }
    setDOMContent(el: HTMLElement) {
      // Như bản đồ thật: nội dung popup nằm trong DOM để query được.
      this.content?.remove();
      this.content = el;
      document.body.appendChild(el);
      return this;
    }
    addTo() {
      return this;
    }
    remove() {
      this.content?.remove();
      this.content = null;
    }
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
const pin = (monthly: number, id = "room-1"): MapPin => ({
  id,
  title: "Phòng",
  latitude: 10.7,
  longitude: 106.7,
  uncertainty_m: 200,
  location_accuracy: "approximate",
  monthly,
});
it("keeps exactly one map instance across pin and selection changes", async () => {
  created.maps = 0;
  const view = render(<MapView pins={[pin(3_000_000)]} />);
  // Bản đồ nạp xong, marker hiện ra.
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(1),
  );
  expect(created.maps).toBe(1);
  // Đọc lại kết quả tạo mảng mới cùng nội dung: bản đồ phải sống qua, tile mới kịp tải.
  view.rerender(<MapView pins={[pin(3_000_000)]} />);
  view.rerender(<MapView pins={[pin(3_000_000)]} onSelect={() => {}} />);
  await new Promise((resolve) => setTimeout(resolve, 30));
  expect(created.maps).toBe(1);
  // Đổi selection (hover/chọn thẻ) không được hủy và tạo lại bản đồ.
  view.rerender(
    <MapView pins={[pin(3_000_000)]} onSelect={() => {}} selectedId="room-1" />,
  );
  await waitFor(() =>
    expect(
      document.querySelector(".map-price-marker span")?.className,
    ).toContain("selected"),
  );
  expect(created.maps).toBe(1);
  // Đổi giá: chỉ cập nhật nhãn marker tại chỗ, vẫn một bản đồ.
  view.rerender(
    <MapView pins={[pin(3_500_000)]} onSelect={() => {}} selectedId="room-1" />,
  );
  await waitFor(() =>
    expect(document.querySelector(".map-price-marker span")?.textContent).toBe(
      "3,5 tr",
    ),
  );
  expect(created.maps).toBe(1);
});
it("adds and removes markers in place when the pin set changes", async () => {
  created.maps = 0;
  created.markers = 0;
  const view = render(
    <MapView pins={[pin(3_000_000), pin(2_000_000, "room-2")]} />,
  );
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(2),
  );
  expect(created.maps).toBe(1);
  view.rerender(<MapView pins={[pin(3_000_000)]} />);
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(1),
  );
  // Marker mới được thêm, marker mất được gỡ — không tạo lại bản đồ.
  expect(created.maps).toBe(1);
});
it("enables wheel zoom with a ceiling and re-fits all pins from the button", async () => {
  created.maps = 0;
  created.fit = [];
  render(<MapView pins={[pin(3_000_000)]} />);
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(1),
  );
  // Cuộn chuột zoom được; zoom tối đa bị chặn để một tin lẻ không phóng tối đa
  // tới mức chỉ còn một con đường, và "vừa khung" cũng không vượt zoom 15.
  expect(created.options?.scrollZoom).toBe(true);
  expect(created.options?.maxZoom).toBe(17);
  await waitFor(() => expect(created.fit.length).toBeGreaterThan(0));
  expect((created.fit.at(-1) as unknown[])[1]).toMatchObject({ maxZoom: 15 });
  // Nút "Vừa khung" gọi lại vừa khung trên chính bản đồ hiện có.
  const fitCalls = created.fit.length;
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("button", { name: "Vừa khung tất cả căn" }),
  );
  expect(created.maps).toBe(1);
  expect(created.fit.length).toBeGreaterThan(fitCalls);
});
it("click a marker reports the id, zoom buttons drive the existing map", async () => {
  created.maps = 0;
  created.zoom = [];
  const onSelect = vi.fn();
  render(<MapView pins={[pin(3_000_000)]} onSelect={onSelect} />);
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(1),
  );
  const user = userEvent.setup();
  await user.click(document.querySelector(".map-price-marker") as HTMLElement);
  expect(onSelect).toHaveBeenCalledWith("room-1");
  await user.click(screen.getByRole("button", { name: "Phóng to bản đồ" }));
  await user.click(screen.getByRole("button", { name: "Thu nhỏ bản đồ" }));
  expect(created.zoom).toEqual(["in", "out"]);
  expect(created.maps).toBe(1);
});
it("colors markers and legend by price band from server-provided prices", async () => {
  created.maps = 0;
  const view = render(
    <MapView
      pins={[
        pin(2_500_000, "room-1"),
        pin(3_500_000, "room-2"),
        pin(5_500_000, "room-3"),
      ]}
    />,
  );
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(3),
  );
  // Băng giá chỉ là nhóm màu trình bày; chú giải hiện đúng 4 mức.
  expect(screen.getByText("< 3 triệu")).toBeInTheDocument();
  expect(screen.getByText("3 – 4 triệu")).toBeInTheDocument();
  expect(screen.getByText("4 – 5 triệu")).toBeInTheDocument();
  expect(screen.getByText("> 5 triệu")).toBeInTheDocument();
  const spans = document.querySelectorAll(".map-price-marker span");
  expect(spans[0].className).toContain("b0");
  expect(spans[1].className).toContain("b1");
  expect(spans[2].className).toContain("b3");
  view.unmount();
  // Giá chưa biết: nhãn "?" chứ không phải 0, không có băng màu.
  render(<MapView pins={[{ ...pin(0), monthly: null }]} />);
  await waitFor(() =>
    expect(document.querySelector(".map-price-marker span")?.textContent).toBe(
      "?",
    ),
  );
});
it("popup shows the room cover photo and falls back to the illustration", async () => {
  created.maps = 0;
  const user = userEvent.setup();
  // Không có ảnh bìa: popup giữ nhãn hình minh họa, không render img hỏng.
  const plain = render(<MapView pins={[pin(3_000_000)]} />);
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(1),
  );
  await user.click(document.querySelector(".map-price-marker") as HTMLElement);
  expect(screen.getByText("Hình minh họa")).toBeInTheDocument();
  expect(document.querySelector(".map-popup-photo")).toBeNull();
  plain.unmount();
  // Có ảnh bìa: img popup dùng đúng src, nhãn nguồn ảnh tin gốc.
  render(
    <MapView
      pins={[{ ...pin(3_000_000), photoUrl: "https://cdn.chotot.com/a.jpg" }]}
    />,
  );
  await waitFor(() =>
    expect(document.querySelectorAll(".map-price-marker").length).toBe(1),
  );
  await user.click(document.querySelector(".map-price-marker") as HTMLElement);
  const img = document.querySelector(
    ".map-popup-photo",
  ) as HTMLImageElement | null;
  expect(img?.getAttribute("src")).toBe("https://cdn.chotot.com/a.jpg");
  expect(screen.getByText("Ảnh tin gốc")).toBeInTheDocument();
});
