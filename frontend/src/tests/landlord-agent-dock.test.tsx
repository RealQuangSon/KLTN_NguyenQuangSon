import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ApiError, type Api } from "../api";
import { LandlordAgentDock } from "../components/LandlordAgentDock";
import { RouterProvider } from "../router";

const post = vi.fn();
const api = { post } as unknown as Api;

function setup() {
  return render(
    <RouterProvider>
      <LandlordAgentDock api={api} actorId="owner2" />
    </RouterProvider>,
  );
}

beforeEach(() => {
  post.mockReset();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/chu-nha/tong-quan");
});

it("opens from the floating button and sends a suggestion with recent history", async () => {
  const user = userEvent.setup();
  post.mockResolvedValue({
    message: "Bạn có 3 phòng trống. Xem thêm ở /chu-nha/phong nhé.",
    agent_mode: "agent",
    steps: [{ tool: "get_overview", ok: true }],
  });
  setup();
  await user.click(screen.getByRole("button", { name: "Mở trợ lý chủ nhà" }));
  expect(screen.getByRole("dialog", { name: "Trợ lý chủ nhà" })).toBeVisible();
  expect(
    screen.getByText("Chỉ xem và gợi ý, không tự thay đổi gì"),
  ).toBeVisible();
  await user.click(
    screen.getByRole("button", { name: "Vì sao phòng trống lâu?" }),
  );
  expect(post).toHaveBeenCalledWith("/landlord/agent", {
    message: "Vì sao phòng trống lâu?",
    history: [],
  });
  expect(await screen.findByText(/Bạn có 3 phòng trống/)).toBeVisible();
  expect(screen.getByText("Đã xem: tổng quan")).toBeVisible();
  // Đường dẫn trong câu trả lời là link bấm được, đóng khung và chuyển trang.
  await user.click(screen.getByRole("link", { name: "/chu-nha/phong" }));
  expect(window.location.pathname).toBe("/chu-nha/phong");
});

it("shows a friendly error and keeps failed turns out of the history", async () => {
  const user = userEvent.setup();
  post.mockRejectedValueOnce(
    new ApiError(429, "agent_rate_limited", "Bạn đã hỏi trợ lý nhiều lần."),
  );
  post.mockResolvedValueOnce({
    message: "Ổn rồi.",
    agent_mode: "rules",
    steps: [],
  });
  setup();
  await user.click(screen.getByRole("button", { name: "Mở trợ lý chủ nhà" }));
  const box = screen.getByLabelText("Câu hỏi cho trợ lý chủ nhà");
  await user.type(box, "xin chào{Enter}");
  expect(await screen.findByText("Bạn đã hỏi trợ lý nhiều lần.")).toBeVisible();
  await user.type(box, "thử lại{Enter}");
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[1][1].history).toEqual([
    { role: "user", text: "xin chào" },
  ]);
  expect(await screen.findByText("Ổn rồi.")).toBeVisible();
  expect(
    screen.getByText("Trả lời theo mẫu có sẵn (chưa dùng AI)"),
  ).toBeVisible();
});

it("restores the conversation within the browser session and can start over", async () => {
  const user = userEvent.setup();
  post.mockResolvedValue({
    message: "Chào bạn.",
    agent_mode: "agent",
    steps: [],
  });
  const first = setup();
  await user.click(screen.getByRole("button", { name: "Mở trợ lý chủ nhà" }));
  await user.type(
    screen.getByLabelText("Câu hỏi cho trợ lý chủ nhà"),
    "chào{Enter}",
  );
  await screen.findByText("Chào bạn.");
  first.unmount();
  setup();
  await user.click(screen.getByRole("button", { name: "Mở trợ lý chủ nhà" }));
  expect(screen.getByText("Chào bạn.")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Cuộc trò chuyện mới" }));
  expect(screen.queryByText("Chào bạn.")).toBeNull();
});

it("closes with Escape and never sends an empty message", async () => {
  const user = userEvent.setup();
  setup();
  await user.click(screen.getByRole("button", { name: "Mở trợ lý chủ nhà" }));
  expect(screen.getByRole("button", { name: "Gửi" })).toBeDisabled();
  await user.type(
    screen.getByLabelText("Câu hỏi cho trợ lý chủ nhà"),
    "{Escape}",
  );
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(post).not.toHaveBeenCalled();
});
