import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "../App";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const actor = (id: string, role: string) => ({ id, role });
function stubSession(
  jsonFetch: (url: string, options?: RequestInit) => Promise<Response>,
) {
  const calls: Array<{ url: string; method: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      calls.push({ url, method: options?.method || "GET" });
      return jsonFetch(url, options);
    }),
  );
  return calls;
}
it("opens a renter deep link directly, navigates by links and returns via browser back", async () => {
  sessionStorage.setItem("homematch.token", "token-r");
  window.history.replaceState(null, "", "/nguoi-thue/lich-xem");
  const calls = stubSession(async (url) => {
    if (url.endsWith("/auth/me")) return json(actor("renter-a", "renter"));
    if (url.endsWith("/viewings")) return json([]);
    return json([]);
  });
  render(<App />);
  // Đủ thời gian cho boot gate /auth/me trước khi màn hình xuất hiện.
  await screen.findByRole(
    "heading",
    { name: "Lịch xem phòng" },
    { timeout: 4000 },
  );
  // Effect mount có thể chạy sau commit DOM, nên đợi đúng lời gọi dữ liệu
  // thay vì khẳng định ngay khi tiêu đề xuất hiện.
  await waitFor(
    () =>
      expect(calls.some((call) => call.url.endsWith("/viewings"))).toBe(true),
    { timeout: 4000 },
  );
  expect(
    screen.queryByRole("link", { name: "Duyệt gợi ý" }),
  ).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(screen.getByRole("link", { name: "Tìm phòng" }));
  await waitFor(() => expect(window.location.pathname).toBe("/tro-ly-ai"));
  await screen.findByText("Nhà mới, vừa với cuộc sống.");
  await act(async () => {
    window.history.back();
  });
  await screen.findByRole(
    "heading",
    { name: "Lịch xem phòng" },
    { timeout: 4000 },
  );
  expect(window.location.pathname).toBe("/nguoi-thue/lich-xem");
}, 15000);
it("redirects an anonymous deep link into a protected area to the login page", async () => {
  window.history.replaceState(null, "", "/chu-nha/phong");
  stubSession(async () => json({}));
  render(<App />);
  await screen.findByText("Chào mừng bạn trở lại.", {}, { timeout: 4000 });
  expect(window.location.pathname).toBe("/dang-nhap");
}, 15000);
it("blocks a renter from the landlord route with a truthful 403 screen instead of landlord data", async () => {
  sessionStorage.setItem("homematch.token", "token-r");
  window.history.replaceState(null, "", "/chu-nha/duyet-goi-y");
  const calls = stubSession(async (url) => {
    if (url.endsWith("/auth/me")) return json(actor("renter-a", "renter"));
    return json([]);
  });
  render(<App />);
  await screen.findByText(
    "Bạn không có quyền truy cập khu vực này",
    {},
    { timeout: 4000 },
  );
  expect(
    calls.filter((call) => call.url.includes("/landlord/recommendations")),
  ).toHaveLength(0);
  const user = userEvent.setup();
  await user.click(
    screen.getByRole("link", { name: /về không gian của bạn/i }),
  );
  await waitFor(() => expect(window.location.pathname).toBe("/tro-ly-ai"));
});
it("opens the landlord portal on the landlord's own rooms with landlord-only navigation", async () => {
  sessionStorage.setItem("homematch.token", "token-o");
  window.history.replaceState(null, "", "/chu-nha/phong");
  const calls = stubSession(async (url) => {
    if (url.endsWith("/auth/me")) return json(actor("owner-a", "owner"));
    if (url.endsWith("/landlord/rooms")) return json({ rooms: [] });
    return json([]);
  });
  render(<App />);
  await screen.findByRole(
    "heading",
    { name: "Phòng & tin đăng" },
    { timeout: 4000 },
  );
  expect(calls.some((call) => call.url.endsWith("/landlord/rooms"))).toBe(true);
  expect(screen.getByRole("link", { name: "Duyệt gợi ý" })).toBeVisible();
  expect(
    screen.queryByRole("link", { name: "Tìm phòng" }),
  ).not.toBeInTheDocument();
  const active = screen.getByRole("link", { name: "Phòng & tin" });
  expect(active).toHaveAttribute("href", "/chu-nha/phong");
  expect(active).toHaveAttribute("aria-current", "page");
}, 15000);
const fillRegisterForm = async () => {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText(/^Họ và tên/), "Nguyễn Văn A");
  await user.type(screen.getByLabelText(/^Email/), "nguyen-a@example.com");
  await user.type(screen.getByLabelText(/^Tên đăng nhập/), "nguyen-a");
  await user.type(screen.getByLabelText(/^Mật khẩu/), "mat-khau-dai-10");
  await user.type(
    screen.getByLabelText(/^Nhập lại mật khẩu/),
    "mat-khau-dai-10",
  );
  return user;
};
it("validates the registration form locally before any network request", async () => {
  window.history.replaceState(null, "", "/dang-ky");
  const calls = stubSession(async () => json({}));
  render(<App />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Đăng ký" }));
  expect(await screen.findByText("Vui lòng nhập họ và tên.")).toBeVisible();
  expect(screen.getByText("Vui lòng nhập email hợp lệ.")).toBeVisible();
  expect(screen.getByText("Tên đăng nhập cần ít nhất 3 ký tự.")).toBeVisible();
  expect(screen.getByText("Mật khẩu cần ít nhất 10 ký tự.")).toBeVisible();
  expect(calls).toHaveLength(0);
  // Sau submit lỗi, label chứa thêm câu báo lỗi nên đối chiếu bằng đầu nhãn.
  await user.type(screen.getByLabelText(/^Họ và tên/), "Nguyễn Văn A");
  await user.type(screen.getByLabelText(/^Email/), "khong-hop-le");
  await user.type(screen.getByLabelText(/^Tên đăng nhập/), "nguyen-a");
  await user.type(screen.getByLabelText(/^Mật khẩu/), "mat-khau-dai-10");
  await user.type(screen.getByLabelText(/^Nhập lại mật khẩu/), "khac-ra");
  await user.click(screen.getByRole("button", { name: "Đăng ký" }));
  expect(screen.getByText("Vui lòng nhập email hợp lệ.")).toBeVisible();
  expect(screen.getByText("Mật khẩu nhập lại chưa khớp.")).toBeVisible();
  expect(calls).toHaveLength(0);
}, 15000);
it("reports a truthful error when the server has no register endpoint instead of faking success", async () => {
  window.history.replaceState(null, "", "/dang-ky");
  const calls = stubSession(async (url, options) => {
    if ((options?.method || "GET") === "POST" && url.endsWith("/auth/register"))
      return json(
        { error: { code: "not_found", message: "Không tìm thấy" } },
        404,
      );
    return json({});
  });
  render(<App />);
  const user = await fillRegisterForm();
  await user.click(screen.getByRole("button", { name: "Đăng ký" }));
  await screen.findByText(
    /Máy chủ chưa có chức năng đăng ký \(cần POST \/auth\/register\)/,
    {},
    { timeout: 4000 },
  );
  // Gọi đúng đường gốc 0.4.0, không còn giả định namespace /v1.
  expect(calls.some((call) => call.url.endsWith("/api/auth/register"))).toBe(
    true,
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
}, 15000);
it("shows only the server-provided outcome when registration succeeds", async () => {
  window.history.replaceState(null, "", "/dang-ky");
  stubSession(async (url, options) => {
    if ((options?.method || "GET") === "POST" && url.endsWith("/auth/register"))
      return json({
        status: "pending_verification",
        message: "Đã ghi nhận đăng ký; chờ xác minh theo quy trình máy chủ.",
      });
    return json({});
  });
  render(<App />);
  const user = await fillRegisterForm();
  await user.click(screen.getByRole("button", { name: "Đăng ký" }));
  await screen.findByText(
    "Đã ghi nhận đăng ký; chờ xác minh theo quy trình máy chủ.",
    {},
    { timeout: 4000 },
  );
  // Không tự đăng nhập và không điều hướng vào workspace sau đăng ký.
  expect(
    screen.queryByRole("button", { name: "Đăng xuất" }),
  ).not.toBeInTheDocument();
}, 15000);
it("describes the pending-verification state from the 0.4.0 DTO when the server sends no message", async () => {
  window.history.replaceState(null, "", "/dang-ky");
  stubSession(async (url, options) => {
    if ((options?.method || "GET") === "POST" && url.endsWith("/auth/register"))
      return json({
        status: "pending_verification",
        user: { id: "nguyen-a", role: "renter" },
        delivery: "dev_stub_log_only",
      });
    return json({});
  });
  render(<App />);
  const user = await fillRegisterForm();
  await user.click(screen.getByRole("button", { name: "Đăng ký" }));
  await screen.findByText(/đang chờ xác minh email/, {}, { timeout: 4000 });
  expect(
    screen.queryByRole("button", { name: "Đăng xuất" }),
  ).not.toBeInTheDocument();
}, 15000);
