import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "../App";
import { Api } from "../api";
import { AdminWorkspace } from "../pages/AdminWorkspace";
// FE-02: đăng ký chủ nhà (hợp đồng README §7.1), admin duyệt/từ chối hồ sơ,
// banner chờ duyệt và khóa ô công khai. Mock theo mẫu inbox-admin.test.tsx
// (vi.spyOn(api, "get")) và stub fetch cho luồng qua App.
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
function stubSession(
  jsonFetch: (url: string, options?: RequestInit) => Promise<Response>,
) {
  const calls: Array<{ url: string; method: string; body: string | null }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      calls.push({
        url,
        method: options?.method || "GET",
        body:
          typeof options?.body === "string" ? (options.body as string) : null,
      });
      return jsonFetch(url, options);
    }),
  );
  return calls;
}
const registerBody = (
  calls: { url: string; method: string; body: string | null }[],
) => {
  const call = calls.find(
    (item) => item.method === "POST" && item.url.endsWith("/auth/register"),
  );
  return call?.body ? (JSON.parse(call.body) as Record<string, unknown>) : null;
};
const fillRegisterForm = async () => {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/^Họ và tên/), "Nguyễn Thị B");
  await user.type(screen.getByLabelText(/^Email/), "chu-nha@example.com");
  await user.type(screen.getByLabelText(/^Tên đăng nhập/), "chu-nha-b");
  await user.type(screen.getByLabelText(/^Mật khẩu/), "mat-khau-dai-10");
  await user.type(
    screen.getByLabelText(/^Nhập lại mật khẩu/),
    "mat-khau-dai-10",
  );
  return user;
};
it("sends account_type owner with the pending-approval note when Chủ nhà is picked", async () => {
  window.history.replaceState(null, "", "/dang-ky");
  const calls = stubSession(async () =>
    json({
      status: "pending_verification",
      user: { id: "chu-nha-b", role: "owner" },
      delivery: "dev_stub_log_only",
    }),
  );
  render(<App />);
  const user = await fillRegisterForm();
  await user.click(screen.getByLabelText("Chủ nhà"));
  expect(
    await screen.findByText(/cần quản trị viên duyệt trước khi công khai tin/),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Đăng ký" }));
  await waitFor(() => expect(registerBody(calls)).toBeTruthy());
  expect(registerBody(calls)?.account_type).toBe("owner");
  expect(registerBody(calls)?.username).toBe("chu-nha-b");
}, 15000);
it("defaults to account_type renter when the applicant does not choose a role", async () => {
  window.history.replaceState(null, "", "/dang-ky");
  const calls = stubSession(async () =>
    json({ status: "pending_verification" }),
  );
  render(<App />);
  const user = await fillRegisterForm();
  await user.click(screen.getByRole("button", { name: "Đăng ký" }));
  await waitFor(() => expect(registerBody(calls)).toBeTruthy());
  expect(registerBody(calls)?.account_type).toBe("renter");
}, 15000);
const application = {
  user_id: "chu-nha-b",
  email: "chu-nha@example.com",
  display_name: "Chủ Nguyễn",
  landlord_status: "pending",
  created_at: "2026-10-06T09:00:00Z",
  verified: true,
};
const mockAdminReads = (api: Api) =>
  vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path === "/admin/users") return [] as never;
    if (path === "/admin/landlord-applications?status=pending")
      return [application] as never;
    return [] as never;
  });
it("lists the pending application and Duyệt calls the contract path", async () => {
  const api = new Api("t");
  mockAdminReads(api);
  const post = vi.spyOn(api, "post").mockResolvedValue({
    user_id: "chu-nha-b",
    landlord_status: "approved",
  } as never);
  const user = userEvent.setup();
  render(<AdminWorkspace api={api} section="tai-khoan" />);
  expect(await screen.findByText("Chủ Nguyễn")).toBeInTheDocument();
  expect(screen.getByText("chu-nha@example.com")).toBeInTheDocument();
  expect(screen.getByText("Đã xác minh")).toBeInTheDocument();
  // Đối chiếu ngày bằng đúng định dạng Intl của môi trường chạy test.
  expect(
    screen.getByText(
      new Intl.DateTimeFormat("vi-VN").format(new Date("2026-10-06T09:00:00Z")),
    ),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Duyệt" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      "/admin/landlord-applications/chu-nha-b/approve",
    ),
  );
});
it("does not call the API when rejecting without a reason, then rejects with it", async () => {
  const api = new Api("t");
  mockAdminReads(api);
  const post = vi.spyOn(api, "post").mockResolvedValue({
    user_id: "chu-nha-b",
    landlord_status: "rejected",
  } as never);
  const user = userEvent.setup();
  render(<AdminWorkspace api={api} section="tai-khoan" />);
  await user.click(await screen.findByRole("button", { name: "Từ chối" }));
  expect(
    screen.getByRole("dialog", { name: "Từ chối hồ sơ chờ duyệt" }),
  ).toBeInTheDocument();
  const confirm = screen.getByRole("button", { name: "Từ chối hồ sơ" });
  expect(confirm).toBeDisabled();
  await user.click(confirm);
  expect(post).not.toHaveBeenCalled();
  await user.type(
    screen.getByLabelText("Lý do từ chối"),
    "Thiếu xác minh địa chỉ",
  );
  expect(confirm).toBeEnabled();
  await user.click(confirm);
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      "/admin/landlord-applications/chu-nha-b/reject",
      { reason: "Thiếu xác minh địa chỉ" },
    ),
  );
});
it("keeps focus in the reject dialog and closes it on Escape", async () => {
  const api = new Api("t");
  mockAdminReads(api);
  vi.spyOn(api, "post").mockResolvedValue({} as never);
  const user = userEvent.setup();
  render(<AdminWorkspace api={api} section="tai-khoan" />);
  await user.click(await screen.findByRole("button", { name: "Từ chối" }));
  const dialog = screen.getByRole("dialog", {
    name: "Từ chối hồ sơ chờ duyệt",
  });
  expect(screen.getByLabelText("Lý do từ chối")).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(dialog).not.toBeInTheDocument();
  expect(vi.mocked(api.post).mock.calls).toHaveLength(0);
});
const pendingOwnerRoom = {
  id: "room-1",
  revision: 3,
  title: "Studio Q7. Gần lô B",
  city: "TP.HCM",
  area: "Quận 7",
  room_type: "studio",
  published: false,
  available: null,
  occupancy: "vacant",
  area_m2: 22,
  source: "demo://room",
  synthetic: true,
  amenities: {},
  quote: { rent_vnd: 4500000, deposit_vnd: null, fees: [] },
  landlord_id: "owner-a",
};
const stubPendingOwner = (
  calls: { url: string; method: string; body: string | null }[],
  respond: (
    url: string,
    options?: RequestInit,
  ) => Response | Promise<Response> = () => json({}),
) =>
  stubSession(async (url, options) => {
    if (url.endsWith("/auth/me"))
      return json({
        id: "owner-a",
        role: "owner",
        landlord_status: "pending",
      });
    if (url.endsWith("/landlord/rooms"))
      return json({ rooms: [pendingOwnerRoom] });
    calls.push({
      url,
      method: options?.method || "GET",
      body: typeof options?.body === "string" ? (options.body as string) : null,
    });
    return respond(url, options);
  });
it("shows the pending banner on /chu-nha pages and locks the publish checkbox", async () => {
  sessionStorage.setItem("homematch.token", "token-o");
  window.history.replaceState(null, "", "/chu-nha/phong");
  stubPendingOwner([]);
  render(<App />);
  expect(
    await screen.findByText(/Tài khoản đang chờ quản trị viên duyệt/),
  ).toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Sửa room-1" }));
  const checkbox = await screen.findByRole("checkbox", {
    name: "Công khai tin cho khách tìm thấy",
  });
  expect(checkbox).toBeDisabled();
  expect(screen.getAllByText(/chưa công khai được/).length).toBeGreaterThan(0);
}, 15000);
it("shows the server message when the API still answers 403 landlord_not_approved", async () => {
  sessionStorage.setItem("homematch.token", "token-o");
  window.history.replaceState(null, "", "/chu-nha/phong");
  const calls: { url: string; method: string; body: string | null }[] = [];
  stubPendingOwner(calls, () =>
    json(
      {
        error: {
          code: "landlord_not_approved",
          message:
            "Tài khoản chủ nhà chưa được quản trị viên duyệt nên chưa công khai được tin.",
        },
      },
      403,
    ),
  );
  render(<App />);
  await screen.findByText(/Tài khoản đang chờ quản trị viên duyệt/);
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Duyệt tin room-1" }),
  );
  expect(
    await screen.findByText(
      "Tài khoản chủ nhà chưa được quản trị viên duyệt nên chưa công khai được tin.",
    ),
  ).toBeInTheDocument();
  expect(
    calls.some((call) => call.url.endsWith("/landlord/rooms/room-1/status")),
  ).toBe(true);
}, 15000);
