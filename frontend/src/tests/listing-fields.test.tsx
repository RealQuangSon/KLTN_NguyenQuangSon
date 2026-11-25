import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { PublicListing } from "../pages/PublicListing";
import { SearchPage } from "../pages/SearchPage";
import { CostBreakdown, costSourceText } from "../components/Shared";
import { addressLine, postedAgoLabel } from "../types";
import { cost as baseCost } from "./fixtures";
import type { Cost, Room } from "../types";
// LF-05: hiển thị địa chỉ chi tiết, ngày đăng, nhãn người đăng, điều khoản
// thuê ("Chưa rõ" cho mục thiếu), nội dung tin thu gọn, chip tiện ích; bộ lọc
// thêm tiện ích mới và sắp xếp "Mới đăng" (chỉ ở tìm theo bộ lọc, F2).

const NOW = Date.parse("2026-11-02T10:00:00Z");

it("builds the address from the parts that exist and skips the missing ones", () => {
  expect(
    addressLine({
      street: "Đường Hồ Văn Huê",
      ward: "Phường 9",
      ward_2025: "Phường Đức Nhuận",
      area: "Quận Phú Nhuận",
    }),
  ).toBe(
    "Đường Hồ Văn Huê, Phường 9 (nay là Phường Đức Nhuận), Quận Phú Nhuận",
  );
  expect(
    addressLine({
      street: null,
      ward: "Phường 9",
      ward_2025: null,
      area: "Quận Phú Nhuận",
    }),
  ).toBe("Phường 9, Quận Phú Nhuận");
  expect(
    addressLine({
      street: null,
      ward: null,
      ward_2025: "Phường Đức Nhuận",
      area: "Quận Phú Nhuận",
    }),
  ).toBe("Phường Đức Nhuận, Quận Phú Nhuận");
  expect(
    addressLine({ street: null, ward: null, ward_2025: null, area: "Quận 7" }),
  ).toBe("Quận 7");
});

it("formats the posting age and stays null without a date", () => {
  expect(postedAgoLabel("2026-10-31T10:00:00Z", NOW)).toBe("Đăng 2 ngày trước");
  expect(postedAgoLabel("2026-11-02T08:00:00Z", NOW)).toBe("Đăng hôm nay");
  expect(postedAgoLabel(null, NOW)).toBeNull();
  expect(postedAgoLabel("không phải ngày", NOW)).toBeNull();
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
  description: "Phòng mới xây, có bếp nguyên bộ, không chung chủ. ".repeat(12),
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

it("shows address, broker badge, posting age, terms and amenity chips on the public page", async () => {
  serve(room());
  render(<PublicListing roomId="chotot-777" />);
  expect(
    await screen.findByText(
      "Đường Hồ Văn Huê, Phường 9 (nay là Phường Đức Nhuận), Quận Phú Nhuận",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("Môi giới")).toBeInTheDocument();
  expect(screen.getByText(/Đăng 2 ngày trước/)).toBeInTheDocument();
  expect(screen.getByText(/Điều khoản thuê/)).toBeInTheDocument();
  expect(screen.getByText(/Tiền cọc: Chưa rõ/)).toBeInTheDocument();
  expect(screen.getByText(/Kỳ thanh toán: Chưa rõ/)).toBeInTheDocument();
  expect(
    screen.getByText(/Thời hạn hợp đồng tối thiểu: 6 tháng/),
  ).toBeInTheDocument();
  expect(screen.getByText(/Trống từ: 01\/12/)).toBeInTheDocument();
  // Nội dung tin dài → thu gọn kèm "Xem thêm".
  expect(screen.getByRole("button", { name: "Xem thêm" })).toBeInTheDocument();
  // Tiện ích dạng lưới trên trang chi tiết, chỉ mục true —
  // tin nói "không wifi" hay không nói tới thì không hiện (không gạch ngang,
  // không suy ra 0/false hiển thị).
  expect(screen.getByText("Bếp")).toBeInTheDocument();
  expect(screen.queryByText("Wifi")).toBeNull();
  expect(screen.queryByText("Thang máy")).toBeNull();
});

it("shows no poster badge at all when poster_kind is null", async () => {
  serve(room({ poster_kind: null }));
  render(<PublicListing roomId="chotot-777" />);
  expect(await screen.findByText(/Phòng trọ Hồ Văn Huê/)).toBeInTheDocument();
  expect(screen.queryByText("Môi giới")).toBeNull();
  expect(screen.queryByText("Chính chủ")).toBeNull();
});

it("shows the individual badge for individual posters", async () => {
  serve(room({ poster_kind: "individual" }));
  render(<PublicListing roomId="chotot-777" />);
  expect(await screen.findByText("Chính chủ")).toBeInTheDocument();
});

// Bảng chi phí không hiện mã nội bộ — tên khoản và nguồn đều
// tiếng Việt ở lớp hiển thị; tên trường trong API không đổi.
it("shows Vietnamese cost sources and line names instead of internal codes", () => {
  expect(costSourceText("quote.rent_vnd")).toBe("Theo tin đăng");
  expect(costSourceText("quote")).toBe("Theo tin đăng");
  expect(costSourceText("missing")).toBe("Tin chưa ghi");
  expect(costSourceText("scenario")).toBe("Theo kịch bản của bạn");
  expect(costSourceText("chotot://ad/1/body#water")).toBe(
    "Theo nội dung tin gốc",
  );
  const cost: Cost = {
    ...baseCost,
    missing_monthly: [],
    lines: [
      {
        name: "first_rent",
        period: "initial",
        amount_vnd: 3_500_000,
        source: "quote",
        included_in_rent: false,
      },
      {
        name: "rent",
        period: "monthly",
        amount_vnd: 3_000_000,
        source: "quote.rent_vnd",
        included_in_rent: false,
      },
      {
        name: "water",
        period: "monthly",
        amount_vnd: null,
        source: "missing",
        included_in_rent: false,
      },
      {
        name: "moving",
        period: "initial",
        amount_vnd: 300_000,
        source: "scenario",
        included_in_rent: false,
      },
    ],
    missing_initial: ["first_rent", "deposit"],
  };
  render(<CostBreakdown cost={cost} />);
  expect(screen.getByText("Tiền thuê trả trước")).toBeInTheDocument();
  expect(screen.getAllByText("Theo tin đăng").length).toBeGreaterThan(0);
  expect(screen.getByText("Tin chưa ghi")).toBeInTheDocument();
  expect(screen.getByText("Theo kịch bản của bạn")).toBeInTheDocument();
  const body = document.body.textContent ?? "";
  for (const code of ["first_rent", "quote.rent_vnd", "missing", "scenario"]) {
    expect(body).not.toContain(code);
  }
  expect(body).toContain("Chưa đủ thông tin: Tiền thuê trả trước, Tiền cọc");
});

it("never shows the crawled poster name to an anonymous visitor", async () => {
  // Bảo đảm chính nằm ở máy chủ: khách ẩn danh nhận contact.poster_name = null
  // (test backend test_crawl_images_and_poster_name_flow_only_to_allowed_surfaces).
  // Giao diện chỉ render đúng dữ liệu máy chủ gửi: tên null → không có khối tên.
  serve(
    room({
      contact: {
        kind: "external",
        original_url: "https://www.chotot.com/87761600.htm",
        phone: null,
        phone_requires_login: false,
        poster_name: null,
      },
    }),
  );
  render(<PublicListing roomId="chotot-777" />);
  expect(
    await screen.findByText("Xem tin gốc trên Chợ Tốt"),
  ).toBeInTheDocument();
  expect(document.querySelector(".poster-name")).toBeNull();
});

const searchListing = (overrides: Record<string, unknown> = {}) => ({
  id: "chotot-777",
  revision: 1,
  title: "Phòng trọ Hồ Văn Huê. Có bếp đầy đủ",
  city: "TP.HCM",
  area: "Quận Phú Nhuận",
  room_type: "room",
  bedrooms: null,
  published: true,
  available: true,
  occupancy: "vacant",
  area_m2: 20,
  source: "https://www.chotot.com/87761600.htm",
  synthetic: false,
  amenities: { kitchen: true, wifi: false },
  quote: {
    rent_vnd: 3500000,
    deposit_vnd: null,
    min_lease_months: 6,
    fees: [],
  },
  posted_at: twoDaysAgo,
  poster_kind: "broker",
  ward: "Phường 9",
  ward_2025: "Phường Đức Nhuận",
  street: "Đường Hồ Văn Huê",
  available_from: "2026-12-01",
  description: "Phòng mới xây.",
  photos: [],
  promotion: null,
  cost: baseCost,
  ...overrides,
});

it("filters by a new amenity, sorts by newest and previews terms in the quick view", async () => {
  const api = new Api("t");
  const get = vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path.startsWith("/listings?"))
      return { total: 1, items: [searchListing()] } as never;
    return searchListing() as never;
  });
  const user = userEvent.setup();
  render(<SearchPage api={api} />);
  await screen.findByText(/Phòng trọ Hồ Văn Huê/);
  // Checkbox tiện ích mới có trong bộ lọc.
  await user.click(screen.getByRole("button", { name: "Thang máy" }));
  // Sắp xếp "Mới đăng" (chỉ ở tìm theo bộ lọc).
  await user.selectOptions(screen.getByLabelText("Sắp xếp"), "posted_desc");
  await user.click(screen.getByRole("button", { name: /^Tìm$/ }));
  const { waitFor } = await import("@testing-library/react");
  await waitFor(() =>
    expect(
      get.mock.calls.some(([path]) => path.includes("amenities=elevator")),
    ).toBe(true),
  );
  await waitFor(() =>
    expect(
      get.mock.calls.some(([path]) => path.includes("sort=posted_desc")),
    ).toBe(true),
  );
  await user.click(screen.getAllByRole("button", { name: "Xem nhanh" })[0]);
  expect(
    await screen.findByText(
      "Đường Hồ Văn Huê, Phường 9 (nay là Phường Đức Nhuận), Quận Phú Nhuận",
    ),
  ).toBeInTheDocument();
  expect(screen.getByText(/Trống từ: 01\/12/)).toBeInTheDocument();
  expect(screen.getByText("Môi giới")).toBeInTheDocument();
}, 20000);
