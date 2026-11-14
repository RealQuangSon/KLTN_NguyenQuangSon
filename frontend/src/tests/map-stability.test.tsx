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
}));
vi.mock("maplibre-gl", () => {
  class Map {
    container: HTMLElement;
    constructor(options: { container: HTMLElement }) {
      this.container = options.container;
      created.maps += 1;
    }
    on(_event: string, cb: () => void) {
      // Style nạp xong ngay: marker effect chạy như khi style thật load.
      if (_event === "load") setTimeout(() => cb(), 0);
    }
    remove() {}
    fitBounds() {}
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
  // Băng giá chỉ là nhóm màu trình bày; chú giải hiện đúng 4 mức tham chiếu.
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
