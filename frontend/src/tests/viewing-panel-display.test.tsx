import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ViewingList } from "../components/ViewingPanel";
import type { Viewing } from "../types";

const completed: Viewing = {
  id: "v1",
  session_id: "session-1",
  run_id: null,
  room_id: "room-1",
  requested_at: "2026-11-15T01:00:00Z",
  status: "completed",
  mode: "offline",
  contact_name: "Nguyễn Văn A",
  contact_phone: "0901234567",
  contact_shared: true,
  lease_id: "lease-1",
  lease_visible: true,
};

const rescheduled: Viewing = {
  id: "v2",
  session_id: "session-1",
  run_id: null,
  room_id: "room-1",
  requested_at: "2026-11-15T01:00:00Z",
  status: "reschedule_proposed",
  mode: "offline",
  proposed_at: "2026-11-16T01:00:00Z",
};

// B2 (15/11): các dòng nhỏ phải tách riêng, không dính liền chữ; link "Xem hợp
// đồng" dùng kiểu nút/link của hệ thống (button small outline).
it("người thuê thấy link Xem hợp đồng theo kiểu hệ thống và các dòng nhỏ riêng biệt", () => {
  const { container } = render(
    <ViewingList
      items={[completed]}
      onFeedback={() => {}}
      onAction={() => {}}
    />,
  );
  const leaseLink = screen.getByRole("link", { name: "Xem hợp đồng" });
  expect(leaseLink).toHaveClass("button", "small", "outline");
  expect(leaseLink).toHaveAttribute("href", "/nguoi-thue/hop-dong");
  // Các khối thông tin là các phần tử nhỏ riêng lẻ (CSS hiển thị block).
  const texts = Array.from(container.querySelectorAll("small")).map(
    (node) => node.textContent || "",
  );
  expect(texts.some((text) => text.includes("Liên hệ đã chia sẻ"))).toBe(true);
});

it("lịch được đề xuất giờ mới thì có dòng Giờ đề xuất mới tách riêng", () => {
  const { container } = render(
    <ViewingList
      items={[rescheduled]}
      onFeedback={() => {}}
      onAction={() => {}}
    />,
  );
  const texts = Array.from(container.querySelectorAll("small")).map(
    (node) => node.textContent || "",
  );
  expect(texts.some((text) => text.includes("Giờ đề xuất mới"))).toBe(true);
});

// B3 (15/11): form phản hồi nằm dưới thẻ lịch (con trực tiếp của article,
// full-width do CSS), không nằm trong cụm cột thao tác hẹp.
it("form phản hồi sau buổi xem là khối riêng trong thẻ lịch", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <ViewingList
      items={[completed]}
      onFeedback={() => {}}
      onAction={() => {}}
    />,
  );
  // Form mở sau khi bấm "Gửi phản hồi" (trước đó chỉ có nút thu gọn).
  await user.click(screen.getByRole("button", { name: "Gửi phản hồi" }));
  const form = container.querySelector("form.viewing-feedback");
  expect(form).not.toBeNull();
  expect(form?.parentElement?.className).toContain("viewing-row");
});
