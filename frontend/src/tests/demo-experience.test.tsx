import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "../App";
import { RouterProvider } from "../router";
import { Login } from "../pages/Login";
import { ExperienceSwitch } from "../components/DemoExperience";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const health = (authMode: string, pub: boolean) =>
  json({
    status: "ok",
    prototype: true,
    storage: "sqlite",
    auth_mode: authMode,
    matching_method: "B1",
    workers: 1,
    public: pub,
  });
const seedLoginResponse = (username: string) =>
  json({
    access_token: `token-${username}`,
    actor: {
      id: username,
      role: username.startsWith("owner") ? "owner" : "renter",
    },
    token_type: "bearer",
    expires_at: "2099-01-01",
  });
it("login page offers one-click seed experiences per role without typing credentials", async () => {
  const loginBodies: { username?: string; password?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/health")) return health("seed", false);
      if (url.endsWith("/auth/login")) {
        loginBodies.push(JSON.parse(String(options?.body)));
        return seedLoginResponse(
          loginBodies[loginBodies.length - 1].username ?? "",
        );
      }
      return json([]);
    }),
  );
  const onAuthenticated = vi.fn();
  render(
    <RouterProvider>
      <Login
        error={null}
        onError={vi.fn()}
        onBack={vi.fn()}
        pendingNeed={null}
        onAuthenticated={onAuthenticated}
      />
    </RouterProvider>,
  );
  const user = userEvent.setup();
  // Vai trò mặc định người thuê: chip tài khoản seed hiện kèm form thủ công.
  await screen.findByRole("button", { name: /renter-a/ });
  expect(screen.getByLabelText(/Tên đăng nhập/)).toBeVisible();
  await user.click(screen.getByRole("button", { name: /renter-a/ }));
  await waitFor(() =>
    expect(onAuthenticated).toHaveBeenCalledWith("token-renter-a", {
      id: "renter-a",
      role: "renter",
    }),
  );
  // Đổi vai trò chủ nhà: chip owner hiện và vào đúng tài khoản đã chọn.
  await user.click(screen.getByRole("button", { name: "Chủ nhà" }));
  await screen.findByRole("button", { name: /owner-d/ });
  await user.click(screen.getByRole("button", { name: /owner-d/ }));
  await waitFor(() =>
    expect(onAuthenticated).toHaveBeenCalledWith("token-owner-d", {
      id: "owner-d",
      role: "owner",
    }),
  );
  // Mật khẩu seed theo convention local, không yêu cầu người dùng gõ.
  expect(loginBodies[0]).toEqual({
    username: "renter-a",
    password: "local-renter-a-password",
  });
  expect(loginBodies[1]).toEqual({
    username: "owner-d",
    password: "local-owner-d-password",
  });
});
it("hides quick experiences when the deployment is public", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/health")) return health("seed", true);
      return json([]);
    }),
  );
  render(
    <RouterProvider>
      <Login
        error={null}
        onError={vi.fn()}
        onBack={vi.fn()}
        pendingNeed={null}
        onAuthenticated={vi.fn()}
      />
    </RouterProvider>,
  );
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  expect(screen.queryByRole("button", { name: /renter-a/ })).toBeNull();
  expect(screen.queryByText(/Trải nghiệm nhanh/)).toBeNull();
});
it("account block switches straight into renter or landlord experience", async () => {
  const loginBodies: { username?: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/health")) return health("seed", false);
      if (url.endsWith("/auth/login")) {
        loginBodies.push(JSON.parse(String(options?.body)));
        return seedLoginResponse(
          loginBodies[loginBodies.length - 1].username ?? "",
        );
      }
      return json([]);
    }),
  );
  const onAuthenticated = vi.fn();
  render(<ExperienceSwitch onAuthenticated={onAuthenticated} />);
  const user = userEvent.setup();
  // Chip chỉ hiện sau khi probe /health trả seed local.
  await user.click(
    await screen.findByRole("button", { name: "Trải nghiệm người thuê" }),
  );
  await waitFor(() =>
    expect(onAuthenticated).toHaveBeenCalledWith("token-renter-a", {
      id: "renter-a",
      role: "renter",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Trải nghiệm chủ nhà" }));
  await waitFor(() =>
    expect(onAuthenticated).toHaveBeenCalledWith("token-owner-a", {
      id: "owner-a",
      role: "owner",
    }),
  );
  expect(loginBodies.map((body) => body.username)).toEqual([
    "renter-a",
    "owner-a",
  ]);
});
it("full app shows the two experience options in the account block in demo mode", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url.endsWith("/health")) return health("seed", false);
      if (url.endsWith("/auth/me"))
        return json({ id: "admin-a", role: "admin" });
      return json([]);
    }),
  );
  sessionStorage.setItem("homematch.token", "token-admin");
  // Trang chủ giờ vẫn mở được khi đã đăng nhập (tham chiếu HubHome); khối
  // tài khoản nằm ở workspace, nên mở đúng cổng của vai admin.
  window.history.replaceState(null, "", "/quan-tri/hoi-thoai");
  render(<App />);
  await screen.findByText("admin-a");
  expect(
    await screen.findByRole("button", { name: "Trải nghiệm người thuê" }),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Trải nghiệm chủ nhà" }),
  ).toBeVisible();
});
