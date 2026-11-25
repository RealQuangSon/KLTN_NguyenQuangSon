import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { ViewingForm, ViewingList } from "../components/ViewingPanel";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { RouterProvider } from "../router";
import { room as fixtureRoom, session } from "./fixtures";
import type { Viewing } from "../types";
// Form đặt lịch dùng chung (ngày + 3 khung giờ + liên hệ + đồng
// ý) và danh sách lịch xem hai phía với thao tác vòng đời mới.
const room = () => ({
  room_id: "demo-01",
  title: "Phòng trọ Quận 7. Rẻ",
  area: "Quận 7",
});
it("requires contact and consent and composes date + slot into +07:00 ISO", async () => {
  const api = new Api("t");
  const post = vi.spyOn(api, "post").mockResolvedValue({ status: "requested" });
  const done = vi.fn();
  const user = userEvent.setup();
  render(
    <ViewingForm
      api={api}
      sessionId={null}
      room={room()}
      onDone={done}
      onCancel={vi.fn()}
    />,
  );
  const day = new Date(Date.now() + 86400000 * 3).toISOString().slice(0, 10);
  fireEvent.change(screen.getByLabelText(/Ngày muốn xem/), {
    target: { value: day },
  });
  await user.type(screen.getByLabelText("Họ tên"), "Trần Thị B");
  await user.type(screen.getByLabelText("Số điện thoại"), "0987654321");
  // Chưa tick đồng ý → form tự chặn với thông báo rõ (E-01/R3).
  await user.click(screen.getByRole("button", { name: "Gửi yêu cầu xem" }));
  expect(screen.getByText(/Cần đồng ý chia sẻ/)).toBeInTheDocument();
  // Sau khi có lỗi, nút đổi thành "Thử gửi lại cùng yêu cầu" (cùng idempotency key).
  await user.click(screen.getByRole("checkbox"));
  await user.click(screen.getByText("Chiều (12:00–17:00)"));
  await user.click(
    screen.getByRole("button", { name: "Thử gửi lại cùng yêu cầu" }),
  );
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  const payload = post.mock.calls[0][1] as {
    requested_at: string;
    time_slot: string;
    contact_consent: boolean;
  };
  // Ngày + khung giờ chiều ghép thành 14:00+07:00 (07:00Z).
  expect(payload.requested_at).toContain("T07:00:00");
  expect(payload.time_slot).toBe("afternoon");
  expect(payload.contact_consent).toBe(true);
});
it("shows the truthful concierge message and next actions per status", async () => {
  const rows: Viewing[] = [
    {
      id: "v1",
      session_id: null,
      run_id: null,
      room_id: "chotot-9",
      requested_at: "2026-11-10T01:00:00Z",
      status: "requested",
      handler: "concierge",
    },
    {
      id: "v2",
      session_id: null,
      run_id: null,
      room_id: "demo-02",
      requested_at: "2026-11-10T01:00:00Z",
      status: "reschedule_proposed",
      proposed_at: "2026-11-12T09:00:00+07:00",
    },
    {
      id: "v3",
      session_id: null,
      run_id: null,
      room_id: "demo-03",
      requested_at: "2026-11-10T01:00:00Z",
      status: "completed",
      feedback_rating: null,
    },
    {
      id: "v4",
      session_id: null,
      run_id: null,
      room_id: "demo-04",
      requested_at: "2026-11-10T01:00:00Z",
      status: "completed",
      feedback_rating: 5,
      feedback_note: "Ổn",
      lease_id: "lease-1",
      lease_visible: true,
    },
  ];
  const onAction = vi.fn();
  render(<ViewingList items={rows} onAction={onAction} />);
  // Tin cào: thông điệp đúng sự thật — chưa phải lịch đã chốt.
  expect(
    screen.getByText(
      /HomeMatch sẽ liên hệ người đăng để xác nhận; đây chưa phải lịch đã chốt/,
    ),
  ).toBeInTheDocument();
  // reschedule_proposed: chấp nhận giờ mới + hủy.
  expect(
    screen.getByRole("button", { name: "Đồng ý giờ mới" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Giờ đề xuất mới/)).toBeInTheDocument();
  // completed chưa phản hồi: nút gửi phản hồi; completed đã phản hồi: hiện điểm.
  expect(
    screen.getByRole("button", { name: "Gửi phản hồi" }),
  ).toBeInTheDocument();
  expect(screen.getByText(/Bạn đã đánh giá 5\/5/)).toBeInTheDocument();
  // Hợp đồng không còn draft → hiện link.
  expect(
    screen.getByRole("link", { name: "Xem hợp đồng" }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Đồng ý giờ mới" }));
  expect(onAction).toHaveBeenCalledWith("v2", "accept");
});
it("landlord sees the renter contact and a create-lease link on a completed landlord viewing", () => {
  const base = {
    room_id: "room-9",
    requested_at: "2026-11-10T01:00:00Z",
    mode: "offline",
    status: "completed",
    contact_name: "Nguyễn Văn A",
    contact_phone: "0912345678",
  };
  const rows = [
    { ...base, id: "v-own", handler: "landlord", lease_id: null },
    { ...base, id: "v-leased", handler: "landlord", lease_id: "lease-1" },
    { ...base, id: "v-crawl", handler: "concierge", lease_id: null },
  ] as unknown as Viewing[];
  render(<ViewingList items={rows} manager onAction={vi.fn()} />);
  expect(
    screen.getAllByText(/Liên hệ khách: Nguyễn Văn A · 0912345678/),
  ).toHaveLength(3);
  // Chỉ lịch của tin chủ nhà chưa có hợp đồng mới có nút tạo; tin cào thì không.
  const create = screen.getAllByRole("link", { name: "Tạo hợp đồng" });
  expect(create).toHaveLength(1);
  expect(create[0]).toHaveAttribute(
    "href",
    "/chu-nha/hop-dong?viewing=v-own&room=room-9",
  );
  expect(screen.getAllByRole("link", { name: "Xem hợp đồng" })).toHaveLength(1);
});
it("feedback asks the renter for a rating and a note instead of sending a default", async () => {
  const onFeedback = vi.fn();
  const done = {
    id: "v9",
    room_id: "room-1",
    status: "completed",
    requested_at: "2026-11-10T01:00:00Z",
    mode: "offline",
    feedback_rating: null,
  } as unknown as Viewing;
  render(<ViewingList items={[done]} onFeedback={onFeedback} />);
  await userEvent.click(screen.getByRole("button", { name: "Gửi phản hồi" }));
  const submit = screen.getByRole("button", { name: "Gửi đánh giá" });
  expect(submit).toBeDisabled();
  expect(onFeedback).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("radio", { name: "3" }));
  await userEvent.type(screen.getByRole("textbox"), "Phòng hơi tối");
  await userEvent.click(submit);
  expect(onFeedback).toHaveBeenCalledWith("v9", 3, "Phòng hơi tối");
});
it("UX-10: prefills name and phone from the account, defaults to tomorrow and blocks past dates", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue({
    display_name: "Nguyễn Văn A",
    contact_phone: "0912345678",
  } as never);
  render(
    <ViewingForm
      api={api}
      sessionId={null}
      room={room()}
      onDone={vi.fn()}
      onCancel={vi.fn()}
    />,
  );
  await waitFor(() =>
    expect(screen.getByLabelText("Họ tên")).toHaveValue("Nguyễn Văn A"),
  );
  expect(screen.getByLabelText("Số điện thoại")).toHaveValue("0912345678");
  const dayInput = screen.getByLabelText(/Ngày muốn xem/) as HTMLInputElement;
  const vn = (offset: number) =>
    new Date(Date.now() + 7 * 3600000 + offset * 86400000)
      .toISOString()
      .slice(0, 10);
  expect(dayInput.value).toBe(vn(1));
  expect(dayInput.min).toBe(vn(0));
});
it("sửa luồng UX: đặt lịch từ khung trợ lý xong hiện thông báo thành công kèm link lịch xem", async () => {
  // Trước đây form "Yêu cầu xem" ở /tro-ly-ai xong hộp thoại chỉ đóng lại.
  // Nay phải có dòng thông báo cùng câu chữ trang tìm kiếm, kèm đường dẫn tới
  // /nguoi-thue/lich-xem.
  const actor = { id: "renter", role: "renter" as const };
  const current = session("session-1");
  const published = {
    session_id: "session-1",
    status: "published",
    results: [fixtureRoom("demo-01"), fixtureRoom("demo-02")],
  };
  const api = new Api("t");
  sessionStorage.setItem("homematch.session.renter", "session-1");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path.endsWith("/results")
      ? (published as never)
      : path.startsWith("/viewings")
        ? ([] as never)
        : (current as never),
  );
  vi.spyOn(api, "post").mockResolvedValue({ status: "requested" } as never);
  Element.prototype.scrollIntoView = () => {};
  const user = userEvent.setup();
  render(
    // Thông báo kèm Link tới /nguoi-thue/lich-xem — Link cần RouterProvider.
    <RouterProvider>
      <RenterWorkspace api={api} actor={actor} tab="search" />
    </RouterProvider>,
  );
  // Mở khung chi tiết căn từ thẻ kết quả, rồi bấm "Yêu cầu xem" trên thẻ đầy đủ.
  await user.click(await screen.findByText("Phòng riêng demo-01"));
  await user.click(await screen.findByRole("button", { name: "Yêu cầu xem" }));
  const day = new Date(Date.now() + 86400000 * 3).toISOString().slice(0, 10);
  fireEvent.change(screen.getByLabelText(/Ngày muốn xem/), {
    target: { value: day },
  });
  await user.type(screen.getByLabelText("Họ tên"), "Trần Thị B");
  await user.type(screen.getByLabelText("Số điện thoại"), "0987654321");
  await user.click(screen.getByRole("checkbox"));
  // Ô chọn lấy tên trợ năng từ nhãn bao quanh (không phải giá trị "on").
  await user.click(screen.getByRole("radio", { name: "Chiều (12:00–17:00)" }));
  expect(
    screen.getByRole("checkbox", { name: /Tôi đồng ý để HomeMatch chia sẻ/ }),
  ).toBeChecked();
  // Ghi chú tùy chọn đi kèm yêu cầu; phần lưu ý nhắc không chuyển tiền trước.
  await user.type(
    screen.getByLabelText(/Ghi chú cho bên phụ trách tin/),
    "Đi cùng một người bạn",
  );
  expect(screen.getByText("Lưu ý khi đi xem")).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Gửi yêu cầu xem" }));
  expect(vi.mocked(api.post).mock.calls[0][1]).toMatchObject({
    note: "Đi cùng một người bạn",
    time_slot: "afternoon",
  });
  const notice = await screen.findByRole("status");
  expect(notice).toHaveTextContent("Đã gửi lịch xem mong muốn");
  expect(notice).toHaveTextContent(
    "Bên phụ trách tin (chủ nhà hoặc điều phối với tin từ tin gốc) sẽ xác nhận hoặc đề xuất giờ khác",
  );
  expect(screen.getByRole("link", { name: "Xem lịch đã gửi" })).toHaveAttribute(
    "href",
    "/nguoi-thue/lich-xem",
  );
  await waitFor(() =>
    expect(screen.queryByLabelText(/Ngày muốn xem/)).not.toBeInTheDocument(),
  );
});
