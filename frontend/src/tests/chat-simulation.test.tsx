import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import type { Cost, Session } from "../types";
import { cost as baseCost, session } from "./fixtures";
// FE-07: thẻ mô phỏng vay trong luồng chat (README §7.4). Mọi con số do máy
// chủ tính và trả về; giao diện chỉ hiển thị, giá trị null hiện "Chưa rõ".
const actor = { id: "renter", role: "renter" as const };
const simCost: Cost = {
  ...baseCost,
  affordability: {
    shortfall_vnd: null,
    loan: {
      principal_vnd: 20000000,
      installment_vnd: 1775000,
      total_interest_vnd: 1300000,
      term_months: 12,
      annual_rate: "0.10",
      exceeds_max_principal: false,
    },
    burden_vnd: null,
    renter_burden_vnd: 3000000,
    housing_ratio: null,
    band: "phu_hop",
    thresholds: {},
  },
};
const current = session("session-1");
const chatApi = (reply: Record<string, unknown>) => {
  const api = new Api("t");
  sessionStorage.setItem("homematch.session.renter", "session-1");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path.endsWith("/results")
      ? ({
          session_id: "session-1",
          status: "awaiting_confirmation",
          results: [],
        } as never)
      : (current as never),
  );
  const post = vi
    .spyOn(api, "post")
    .mockResolvedValue({ ...current, ...reply } as never);
  return { api, post };
};
const ask = async (text: string) => {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText("Nhu cầu của bạn"), text);
  await user.click(screen.getByRole("button", { name: "Gửi nhu cầu" }));
};
it("renders the loan simulation card with the server numbers in the chat flow", async () => {
  const { api, post } = chatApi({
    status: "simulation",
    message: "Đây là mô phỏng theo kịch bản bạn hỏi, chỉ để tham khảo.",
    simulation: {
      room_id: "demo-01",
      room_title: "Studio Q7. Gần lô B",
      scenario: { annual_rate: 10, term_months: 12, principal_vnd: 20000000 },
      result: { label: "Vay 20 triệu · 12 tháng", cost: simCost },
    },
  });
  render(<RenterWorkspace api={api} actor={actor} tab="search" />);
  await ask("nếu vay 12 tháng thì sao");
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      "/sessions/session-1/messages",
      expect.objectContaining({ text: "nếu vay 12 tháng thì sao" }),
    ),
  );
  const card = await screen.findByLabelText("Thẻ mô phỏng vay");
  expect(card).toHaveTextContent("Studio Q7");
  expect(card).toHaveTextContent(
    /Lãi 10%\/năm · 12 tháng · Gốc vay 20\.000\.000 ₫/,
  );
  // Trả góp, tổng tháng, phần của khách và băng đánh giá — số của máy chủ.
  expect(card).toHaveTextContent(/1\.775\.000 ₫ × 12 tháng/);
  expect(card).toHaveTextContent("3.000.000 ₫");
  expect(card).toHaveTextContent("Trong mức khuyến nghị");
});
it("shows Chưa rõ for scenario values the server could not parse", async () => {
  const { api } = chatApi({
    status: "simulation",
    message: "Mô phỏng theo kịch bản mặc định.",
    simulation: {
      room_id: "demo-01",
      room_title: "Studio Q7. Gần lô B",
      scenario: { annual_rate: null, term_months: 12, principal_vnd: null },
      result: { label: "Kịch bản hỏi nhanh", cost: simCost },
    },
  });
  render(<RenterWorkspace api={api} actor={actor} tab="search" />);
  await ask("nếu vay 12 tháng thì sao");
  const card = await screen.findByLabelText("Thẻ mô phỏng vay");
  expect(card).toHaveTextContent(/Lãi Chưa rõ/);
  expect(card).toHaveTextContent(/Gốc vay Chưa rõ/);
});
it("offers the view-results button when status is needs_results", async () => {
  const { api } = chatApi({
    status: "needs_results",
    message: "Bạn cần xác nhận hồ sơ để máy chủ tạo danh sách gợi ý.",
  });
  render(<RenterWorkspace api={api} actor={actor} tab="search" />);
  await ask("hồ sơ của tôi đã đủ chưa");
  expect(
    await screen.findByText(
      "Bạn cần xác nhận hồ sơ để máy chủ tạo danh sách gợi ý.",
    ),
  ).toBeInTheDocument();
  const button = screen.getByRole("button", { name: /Xem danh sách gợi ý/ });
  // jsdom chưa có scrollIntoView; gắn hàm rỗng để bấm nút không lỗi.
  Element.prototype.scrollIntoView = () => {};
  button.click();
  expect(window.location.pathname).toBe("/tro-ly-ai");
  // Không có thẻ mô phỏng trong luồng chat.
  expect(screen.queryByLabelText("Thẻ mô phỏng vay")).toBeNull();
});
