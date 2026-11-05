import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { PublishedResults } from "../components/Shared";
import { room } from "./fixtures";
import type { Results } from "../types";
const result = (overrides: Partial<Results>): Results => ({
  session_id: "session-1",
  run_id: "run-1",
  status: "published",
  results: [room(), room("room-2")],
  ...overrides,
});
it("shows the reviewed result count above the room cards", () => {
  render(
    <PublishedResults
      result={result({})}
      selected={[]}
      onSelect={vi.fn()}
      onViewing={vi.fn()}
    />,
  );
  expect(screen.getByText(/Kết quả phù hợp:/)).toBeInTheDocument();
  expect(screen.getByText("2")).toBeInTheDocument();
});
it("offers one-criterion relax chips on no_match that only prefill the chat", async () => {
  const onAskFollowUp = vi.fn();
  render(
    <PublishedResults
      result={result({ status: "no_match", results: [], suggestions: [] })}
      selected={[]}
      onSelect={vi.fn()}
      onViewing={vi.fn()}
      onAskFollowUp={onAskFollowUp}
    />,
  );
  expect(screen.getByText("NỚI MỘT TIÊU CHÍ ĐỂ TÌM LẠI")).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Nới ngân sách" }));
  expect(onAskFollowUp).toHaveBeenCalledWith(
    "Hãy nới ngân sách tổng tháng lên thêm 1 triệu và tìm lại.",
  );
  // Chỉ điền, không tự gửi: các chip đề xuất nới đúng một tiêu chí.
  expect(
    screen.getByText(
      "Nút chỉ điền câu nhắn vào ô trò chuyện; bạn kiểm tra rồi tự gửi.",
    ),
  ).toBeInTheDocument();
});
