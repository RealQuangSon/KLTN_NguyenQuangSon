import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import App from "../App";
import { CopilotPage } from "../pages/Copilot";
import { cost } from "./fixtures";
it("generates a channel post with a share link and answers advisory questions", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue({
    rooms: [
      {
        id: "demo-01",
        title: "Phòng 01. mô tả",
        city: "TP.HCM",
        area: "Quận 7",
      },
    ],
  } as never);
  const post = vi.spyOn(api, "post").mockImplementation(async (path) =>
    path.endsWith("/marketing")
      ? ({
          channel: "facebook",
          text: "🏠 PHÒNG TRỌ CHO THUÊ – QUẬN 7",
          share_url: "https://www.facebook.com/sharer/sharer.php?u=x",
          listing_url: "http://127.0.0.1:5173/tin/demo-01",
          highlights: ["21 m²", "cửa sổ thoáng"],
          notice: "HomeMatch không tự đăng lên mạng xã hội.",
        } as never)
      : ({
          intent: "vacancy",
          answer: "Phân tích phòng còn trống:\nPhòng 01: chưa có lượt xem tin.",
        } as never),
  );
  const user = userEvent.setup();
  render(<CopilotPage api={api} />);
  await screen.findByRole("option", { name: "Phòng 01" });
  await user.click(screen.getByRole("button", { name: /Tạo nội dung/ }));
  expect(
    await screen.findByDisplayValue(/PHÒNG TRỌ CHO THUÊ/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Chia sẻ lên Facebook" }),
  ).toHaveAttribute("href", "https://www.facebook.com/sharer/sharer.php?u=x");
  expect(post).toHaveBeenCalledWith("/landlord/rooms/demo-01/marketing", {
    channel: "facebook",
  });
  await user.type(screen.getByLabelText("Câu hỏi"), "Vì sao phòng trống lâu?");
  await user.click(screen.getByRole("button", { name: "Hỏi" }));
  expect(await screen.findByText(/chưa có lượt xem tin/)).toBeInTheDocument();
});
it("opens a public listing link without logging in", async () => {
  window.history.replaceState(null, "", "/tin/demo-01");
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            id: "demo-01",
            title: "Phòng 01. mô tả",
            city: "TP.HCM",
            area: "Quận 7",
            room_type: "room",
            area_m2: 21,
            amenities: { window: true },
            synthetic: true,
            cost,
            house_rules: "Cổng đóng 23:00.",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
    ),
  );
  render(<App />);
  expect(
    await screen.findByRole("heading", { name: "Phòng 01" }),
  ).toBeInTheDocument();
  expect(screen.getByText("Cổng đóng 23:00.")).toBeInTheDocument();
  await waitFor(() => expect(window.location.pathname).toBe("/tin/demo-01"));
});
