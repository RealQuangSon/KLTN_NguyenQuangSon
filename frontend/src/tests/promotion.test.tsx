import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RoomEditor } from "../components/RoomEditor";
import { PublicListing } from "../pages/PublicListing";
import type { Cost, Room } from "../types";
import { cost as baseCost } from "./fixtures";
// FE-06: chủ nhà đặt ưu đãi (README §7.6); khách chỉ thấy nhãn khi máy chủ
// trả promotion khác null. Ưu đãi không đổi giá hiển thị trong tin.
const room: Room = {
  id: "room-1",
  revision: 3,
  title: "Studio Q7. Gần lô B",
  city: "TP.HCM",
  area: "Quận 7",
  room_type: "studio",
  bedrooms: null,
  capacity: 2,
  published: true,
  available: null,
  occupancy: "vacant",
  area_m2: 22,
  source: "demo://room",
  synthetic: true,
  amenities: {},
  quote: {
    rent_vnd: 4500000,
    deposit_vnd: null,
    advance_months: 1,
    one_time_vnd: 0,
    fees: [],
  },
  photos: [],
  promotion: null,
};
const listing: Room & { cost: Cost } = {
  ...room,
  cost: baseCost,
  photos: [{ id: "m1", url: "/media/m1" }],
};
it("saves a promotion with PUT and the exact contract body", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue({ ...room, photos: [] } as never);
  const put = vi.spyOn(api, "put").mockResolvedValue({
    text: "Giảm nửa tháng tiền cọc",
    valid_until: "2026-12-31",
  } as never);
  const user = userEvent.setup();
  render(
    <RoomEditor api={api} room={room} onSubmit={vi.fn()} onCancel={vi.fn()} />,
  );
  await user.type(
    await screen.findByLabelText(/Nội dung ưu đãi/),
    "Giảm nửa tháng tiền cọc",
  );
  expect(screen.getByText(/23\/200 ký tự/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText(/Hết hạn vào ngày/), {
    target: { value: "2026-12-31" },
  });
  await user.click(screen.getByRole("button", { name: "Lưu ưu đãi" }));
  await waitFor(() =>
    expect(put).toHaveBeenCalledWith("/landlord/rooms/room-1/promotion", {
      text: "Giảm nửa tháng tiền cọc",
      valid_until: "2026-12-31",
    }),
  );
  expect(
    await screen.findByText(/Đang có ưu đãi đến 2026-12-31/),
  ).toBeInTheDocument();
});
it("removes the promotion with DELETE", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue({
    ...room,
    promotion: { text: "Giảm cọc", valid_until: "2026-11-30" },
  } as never);
  const del = vi.spyOn(api, "delete").mockResolvedValue(null as never);
  const user = userEvent.setup();
  render(
    <RoomEditor api={api} room={room} onSubmit={vi.fn()} onCancel={vi.fn()} />,
  );
  await user.click(await screen.findByRole("button", { name: "Gỡ ưu đãi" }));
  await waitFor(() =>
    expect(del).toHaveBeenCalledWith("/landlord/rooms/room-1/promotion"),
  );
  expect(await screen.findByText(/Đã gỡ ưu đãi khỏi tin/)).toBeInTheDocument();
  expect(screen.queryByText(/Đang có ưu đãi/)).toBeNull();
});
it("shows the promotion badge on the public listing only when the server sends one", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            ...listing,
            promotion: {
              text: "Giảm nửa tháng tiền cọc",
              valid_until: "2026-12-31",
            },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    ),
  );
  render(<PublicListing roomId="room-1" />);
  expect(await screen.findByText("Ưu đãi")).toBeVisible();
  expect(screen.getByText("đến 31/12")).toBeInTheDocument();
  expect(screen.getByText(/Giảm nửa tháng tiền cọc/)).toBeInTheDocument();
  // Giá hiển thị không bị nhãn ưu đãi thay đổi.
  expect(screen.getByText(/Đã biết 2\.500\.000 ₫/)).toBeInTheDocument();
});
it("keeps the badge hidden when promotion is null", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(JSON.stringify({ ...listing, promotion: null }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
    ),
  );
  render(<PublicListing roomId="room-1" />);
  expect(await screen.findByText("Studio Q7")).toBeInTheDocument();
  expect(screen.queryByText("Ưu đãi")).toBeNull();
  expect(screen.queryByText(/đến 31\/12/)).toBeNull();
});
