import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { AdminWorkspace } from "../pages/AdminWorkspace";

// A1 (15/11): link tin gốc của trang điều phối phải là `source_url` do máy chủ
// trả (lấy từ source của phòng), không dựng từ mã phòng.
const conciergeQueue = [
  {
    id: "v1",
    room_id: "chotot-178764528",
    requested_at: "2026-11-15T02:00:00Z",
    status: "requested",
    time_slot: "morning",
    handler: "concierge",
    source_url: "https://www.chotot.com/134679995.htm",
  },
  {
    id: "v2",
    room_id: "chotot-999",
    requested_at: "2026-11-15T03:00:00Z",
    status: "requested",
    time_slot: "evening",
    handler: "concierge",
    source_url: null,
  },
];

it("link tin gốc dùng đúng source_url máy chủ trả, không dựng từ mã phòng", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/admin/viewings" ? (conciergeQueue as never) : ({} as never),
  );
  render(<AdminWorkspace api={api} section="dieu-phoi" />);
  const link = await screen.findByRole("link", {
    name: "Mở tin gốc trên Chợ Tốt ↗",
  });
  expect(link).toHaveAttribute("href", "https://www.chotot.com/134679995.htm");
  expect(link).toHaveAttribute("target", "_blank");
  // Link cũ dựng từ mã phòng không còn xuất hiện.
  expect(
    screen.queryByRole("link", {
      name: "Mở tin gốc trên Chợ Tốt ↗",
    }),
  ).toHaveAttribute("href", expect.not.stringContaining("178764528"));
});

it("tin không có link tin gốc thì hiển thị chú thích thay vì link sai", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/admin/viewings" ? (conciergeQueue as never) : ({} as never),
  );
  render(<AdminWorkspace api={api} section="dieu-phoi" />);
  expect(await screen.findByText("Không có link tin gốc")).toBeInTheDocument();
  expect(screen.getAllByRole("link").length).toBe(1);
});
