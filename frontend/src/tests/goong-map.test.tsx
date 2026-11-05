import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { PublicListing } from "../pages/PublicListing";
import { goongApiKey, goongStyleUrl, priceShortLabel } from "../map";
import { cost as baseCost } from "./fixtures";
import type { Cost, Room } from "../types";
afterEach(() => vi.unstubAllEnvs());
it("formats the short price label like the reference listing markers", () => {
  expect(priceShortLabel(3_500_000)).toBe("3,5 tr");
  expect(priceShortLabel(12_000_000)).toBe("12 tr");
  expect(priceShortLabel(2_800_000)).toBe("2,8 tr");
  expect(priceShortLabel(null)).toBe("?");
});
it("builds the Goong vector style url with the configured map-tiles key", () => {
  vi.stubEnv("VITE_GOONG_API_KEY", "test-goong-key");
  expect(goongApiKey()).toBe("test-goong-key");
  expect(goongStyleUrl("test-goong-key")).toBe(
    "https://tiles.goong.io/assets/goong_map_web.json?api_key=test-goong-key",
  );
});
it("reports no key when the env var is empty so the map falls back to OSM", () => {
  vi.stubEnv("VITE_GOONG_API_KEY", "");
  expect(goongApiKey()).toBeNull();
});
const twoDaysAgo = new Date(Date.now() - 2 * 86_400_000).toISOString();
const room = (overrides: Partial<Room> = {}): Room & { cost: Cost } => ({
  id: "chotot-777",
  revision: 1,
  title: "Phòng trọ Hồ Văn Huê. Có bếp đầy đủ",
  city: "TP.HCM",
  area: "Quận Phú Nhuận",
  room_type: "room",
  bedrooms: null,
  capacity: 2,
  published: true,
  available: true,
  occupancy: "vacant",
  area_m2: 20,
  source: "https://www.chotot.com/87761600.htm",
  synthetic: false,
  amenities: { kitchen: true, wifi: false, elevator: null },
  quote: {
    rent_vnd: 3500000,
    deposit_vnd: null,
    payment_cycle_months: null,
    min_lease_months: 6,
    fees: [],
  },
  description: "Phòng mới xây, có bếp nguyên bộ, không chung chủ. ",
  posted_at: twoDaysAgo,
  poster_kind: "broker",
  ward: "Phường 9",
  ward_2025: "Phường Đức Nhuận",
  street: "Đường Hồ Văn Huê",
  available_from: "2026-12-01",
  photos: [],
  promotion: null,
  ...overrides,
  cost: baseCost,
});
const serve = (payload: unknown) =>
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
it("public listing lazily loads the map and offers zero-quota directions links", async () => {
  serve(
    room({
      latitude: 10.81,
      longitude: 106.68,
      location_accuracy: "approximate",
    }),
  );
  render(<PublicListing roomId="chotot-777" />);
  expect(await screen.findByText("Vị trí trên bản đồ")).toBeInTheDocument();
  // Lazy: nút xem bản đồ thay cho canvas tự nạp — tiết kiệm map load Goong.
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Xem bản đồ gần đúng" }));
  expect(
    screen.getByRole("link", { name: "Mở trong Goong Maps ↗" }),
  ).toHaveAttribute("href", "https://map.goong.io/?lat=10.81&lng=106.68");
  expect(screen.getByRole("link", { name: "Xem đường đi ↗" })).toHaveAttribute(
    "href",
    "https://www.google.com/maps/dir/?api=1&destination=10.81,106.68",
  );
});
it("keeps an area-only listing off the map with the count hint", async () => {
  serve(
    room({ latitude: null, longitude: null, location_accuracy: "area_only" }),
  );
  render(<PublicListing roomId="chotot-777" />);
  expect(await screen.findByText("Vị trí trên bản đồ")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Xem bản đồ gần đúng" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "Mở trong Goong Maps ↗" }),
  ).toBeNull();
});
