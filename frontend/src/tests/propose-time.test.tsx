import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { Api } from "../api";
import { LandlordWorkspace } from "../pages/LandlordWorkspace";
import {
  ProposeTimeForm,
  ViewingList,
  vnDate,
} from "../components/ViewingPanel";
import type { Viewing } from "../types";

const confirmedViewing: Viewing = {
  id: "v1",
  session_id: null,
  run_id: null,
  room_id: "room-1",
  requested_at: "2026-11-15T01:00:00Z",
  status: "confirmed",
  mode: "offline",
};

const setDay = (value: string) =>
  fireEvent.change(screen.getByLabelText("Ngày đề xuất"), {
    target: { value },
  });

afterEach(() => {
  vi.useRealTimers();
});

// A3: "ngày mai" tính theo giờ Việt Nam, không dùng ngày UTC.
// 02:00 ngày 15/11 giờ VN = 2026-11-14T19:00Z — ngày UTC là 14/11, ngày VN là 15/11.
it("vnDate trả ngày mai theo giờ Việt Nam tại mốc 02:00 sáng", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-15T02:00:00+07:00"));
  expect(vnDate(0)).toBe("2026-11-15");
  expect(vnDate(1)).toBe("2026-11-16");
});

// 23:30 ngày 15/11 giờ VN — ngày mai vẫn phải là 16/11 (UTC mới là 15/11 16:30).
it("vnDate trả ngày mai theo giờ Việt Nam tại mốc 23:30 đêm", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-15T23:30:00+07:00"));
  expect(vnDate(0)).toBe("2026-11-15");
  expect(vnDate(1)).toBe("2026-11-16");
});

it("nút Đề xuất giờ khác chỉ mở form, chưa gọi API; gửi đúng proposed_at theo lựa chọn", async () => {
  // Cố định "bây giờ" trước khi chọn ngày để kết quả không phụ thuộc ngày
  // thật của máy. Chỉ giả Date, giữ timer thật để userEvent/findBy/waitFor
  // không treo.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-15T10:00:00+07:00"));
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/viewings" ? ([confirmedViewing] as never) : ({} as never),
  );
  const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
  const user = userEvent.setup();
  render(<LandlordWorkspace api={api} tab="viewings" />);
  await screen.findByRole("button", { name: "Đề xuất giờ khác" });
  await user.click(screen.getByRole("button", { name: "Đề xuất giờ khác" }));
  // Bấm nút chỉ mở form chọn ngày + khung giờ — chưa gọi API.
  expect(
    screen.getByText("Khung giờ đề xuất (giờ Việt Nam)"),
  ).toBeInTheDocument();
  expect(post).not.toHaveBeenCalled();
  // Chọn ngày 20/11 và khung giờ tối, điền lý do rồi gửi.
  setDay("2026-11-20");
  await user.click(screen.getByRole("radio", { name: /Tối/ }));
  await user.type(
    screen.getByLabelText("Lý do (không bắt buộc)"),
    "Phòng đang dọn dẹp",
  );
  await user.click(screen.getByRole("button", { name: "Gửi đề xuất" }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenCalledWith("/viewings/v1/actions", {
    action: "propose",
    // 18:00 ngày 20/11 giờ Việt Nam = 11:00 UTC.
    proposed_at: "2026-11-20T11:00:00.000Z",
    reason: "Phòng đang dọn dẹp",
  });
});

it("form ProposeTimeForm từ chối thời điểm đã qua và cho gửi khi thiếu lý do", () => {
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-15T10:00:00+07:00"));
  const onSubmit = vi.fn();
  render(
    <ProposeTimeForm busy={false} onSubmit={onSubmit} onCancel={() => {}} />,
  );
  // Mặc định là ngày mai theo giờ VN (16/11), không phải "hôm nay" theo UTC.
  expect(screen.getByLabelText("Ngày đề xuất")).toHaveValue("2026-11-16");
  // Ngày hôm nay + khung giờ sáng (08:00 đã qua lúc 10:00) → chặn, không gọi onSubmit.
  setDay("2026-11-15");
  fireEvent.click(screen.getByRole("radio", { name: /Sáng/ }));
  fireEvent.click(screen.getByRole("button", { name: "Gửi đề xuất" }));
  expect(screen.getByRole("status")).toHaveTextContent(
    "Chọn thời điểm trong tương lai.",
  );
  expect(onSubmit).not.toHaveBeenCalled();
  // Đổi sang ngày mai → gửi được dù lý do bỏ trống (lý do không bắt buộc).
  setDay("2026-11-16");
  fireEvent.click(screen.getByRole("button", { name: "Gửi đề xuất" }));
  expect(onSubmit).toHaveBeenCalledWith("2026-11-16T01:00:00.000Z", "");
});

it("danh sách lịch của chủ nhà hiển thị form đề xuất trong thẻ, hủy được", async () => {
  const onPropose = vi.fn();
  const user = userEvent.setup();
  render(
    <ViewingList
      items={[confirmedViewing]}
      manager
      onAction={() => {}}
      onPropose={onPropose}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Đề xuất giờ khác" }));
  expect(screen.getByLabelText("Ngày đề xuất")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Hủy" }));
  expect(screen.queryByLabelText("Ngày đề xuất")).toBeNull();
  expect(onPropose).not.toHaveBeenCalled();
});

it("form đề xuất tự đóng khi lịch đã chuyển sang trạng thái có đề xuất giờ mới", async () => {
  const user = userEvent.setup();
  const props = { manager: true, onAction: () => {}, onPropose: vi.fn() };
  const { rerender } = render(
    <ViewingList items={[confirmedViewing]} {...props} />,
  );
  await user.click(screen.getByRole("button", { name: "Đề xuất giờ khác" }));
  expect(screen.getByLabelText("Ngày đề xuất")).toBeInTheDocument();
  rerender(
    <ViewingList
      items={[
        {
          ...confirmedViewing,
          status: "reschedule_proposed",
          proposed_at: "2026-11-18T07:00:00Z",
        },
      ]}
      {...props}
    />,
  );
  expect(screen.queryByLabelText("Ngày đề xuất")).toBeNull();
  // Khách đồng ý, lịch quay về "đã xác nhận": form không tự bật lại.
  rerender(<ViewingList items={[confirmedViewing]} {...props} />);
  expect(screen.queryByLabelText("Ngày đề xuất")).toBeNull();
});

it("chủ nhà đề xuất giờ khác được ngay từ yêu cầu mới, không cần xác nhận trước", async () => {
  // Như test trên: cố định "bây giờ" (chỉ giả Date) để ngày 20/11 chọn bên
  // dưới luôn là tương lai, bất kể ngày thật của máy chạy test.
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-11-15T10:00:00+07:00"));
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/viewings"
      ? ([{ ...confirmedViewing, status: "requested" }] as never)
      : ({} as never),
  );
  const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
  const user = userEvent.setup();
  render(<LandlordWorkspace api={api} tab="viewings" />);
  // Yêu cầu mới vẫn có đủ Xác nhận / Từ chối, thêm lối đề xuất giờ.
  await screen.findByRole("button", { name: "Xác nhận" });
  await user.click(screen.getByRole("button", { name: "Đề xuất giờ khác" }));
  expect(post).not.toHaveBeenCalled();
  setDay("2026-11-20");
  await user.click(screen.getByRole("radio", { name: /Tối/ }));
  await user.click(screen.getByRole("button", { name: "Gửi đề xuất" }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenCalledWith("/viewings/v1/actions", {
    action: "propose",
    proposed_at: "2026-11-20T11:00:00.000Z",
  });
});
