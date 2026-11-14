import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { PublishedResults } from "../components/Shared";
import { room } from "./fixtures";
import type { Candidate, Results } from "../types";

const result = (count: number): Results => ({
  session_id: "session-1",
  run_id: "run-1",
  status: "published",
  results: Array.from({ length: count }, (_, i) =>
    room(`room-${i + 1}`),
  ) as Candidate[],
});
it("renders compact cards in a grid with location, size, bedrooms, one reason, price, save and compare", () => {
  render(
    <PublishedResults
      result={result(2)}
      selected={[]}
      onSelect={vi.fn()}
      onViewing={vi.fn()}
      onToggleSave={vi.fn()}
      onOpenCard={vi.fn()}
    />,
  );
  // Thẻ nhỏ: tên một dòng, khu vực, diện tích, một dòng lý do, giá tháng.
  expect(screen.getAllByText(/Quận 7 · TP.HCM · 20 m²/)).toHaveLength(2);
  expect(screen.getAllByText("Có cửa sổ theo nguồn")).toHaveLength(2);
  expect(screen.getAllByRole("button", { name: "Lưu căn này" })).toHaveLength(
    2,
  );
  expect(
    screen.getAllByRole("button", { name: "So sánh căn này" }),
  ).toHaveLength(2);
  // Thẻ giả lập còn giữ nhãn dữ liệu giả lập, không bị giấu.
  expect(screen.getAllByText("Dữ liệu giả lập")).toHaveLength(2);
});
it("adds a see-all button when the list is long and expands on demand", async () => {
  const user = userEvent.setup();
  render(
    <PublishedResults
      result={result(11)}
      selected={[]}
      onSelect={vi.fn()}
      onViewing={vi.fn()}
    />,
  );
  // Mặc định hiện 8 căn đầu, nút ghi đúng tổng số căn.
  expect(screen.getByText(/đang hiện 8 căn đầu/)).toBeInTheDocument();
  expect(document.querySelectorAll(".room-mini").length).toBe(8);
  await user.click(screen.getByRole("button", { name: "Xem tất cả 11 căn" }));
  expect(document.querySelectorAll(".room-mini").length).toBe(11);
  // Thu gọn lại được.
  await user.click(screen.getByRole("button", { name: "Rút gọn danh sách" }));
  expect(document.querySelectorAll(".room-mini").length).toBe(8);
});
it("links the card to the map: hover highlights the marker, click opens the detail frame", async () => {
  const user = userEvent.setup();
  const onHoverCard = vi.fn();
  const onOpenCard = vi.fn();
  render(
    <PublishedResults
      result={result(2)}
      selected={[]}
      onSelect={vi.fn()}
      onViewing={vi.fn()}
      highlightId="room-2"
      onHoverCard={onHoverCard}
      onOpenCard={onOpenCard}
    />,
  );
  const cards = document.querySelectorAll<HTMLElement>(".room-mini");
  // Căn đang nổi trên bản đồ (bấm marker/chọn) được viền nổi trên thẻ.
  expect(cards[1].className).toContain("highlighted");
  expect(cards[0].className).not.toContain("highlighted");
  // Hover thẻ báo về trang cha để làm nổi marker; rời hover thì bỏ nổi.
  // React gắn mouseenter qua delegation — dùng fireEvent cho đúng.
  fireEvent.mouseEnter(cards[0]);
  expect(onHoverCard).toHaveBeenLastCalledWith("room-1");
  fireEvent.mouseLeave(cards[0]);
  expect(onHoverCard).toHaveBeenLastCalledWith(null);
  // Bấm thân thẻ mở khung chi tiết.
  await user.click(cards[0]);
  expect(onOpenCard).toHaveBeenCalledTimes(1);
});
it("save and compare chips do not open the detail frame", async () => {
  const user = userEvent.setup();
  const onOpenCard = vi.fn();
  const onSelect = vi.fn();
  const onToggleSave = vi.fn();
  render(
    <PublishedResults
      result={result(1)}
      selected={[]}
      onSelect={onSelect}
      onViewing={vi.fn()}
      onOpenCard={onOpenCard}
      onToggleSave={onToggleSave}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Lưu căn này" }));
  expect(onToggleSave).toHaveBeenCalledWith("room-1");
  expect(onOpenCard).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "So sánh căn này" }));
  expect(onSelect).toHaveBeenCalledWith("room-1");
  expect(onOpenCard).not.toHaveBeenCalled();
});
