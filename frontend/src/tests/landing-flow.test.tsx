import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "../App";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { session } from "./fixtures";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const need = "Cần phòng gần trường, yên tĩnh, tầm 3 triệu";
it("carries the landing need through the login bounce into a fresh consultation", async () => {
  const posts: Array<{ url: string; body?: unknown }> = [];
  const get = vi.fn(async (url: string) => {
    if (url.endsWith("/auth/me"))
      return json({ id: "renter-a", role: "renter" });
    if (url.endsWith("/sessions/session-9/results"))
      return json({
        session_id: "session-9",
        status: "awaiting_confirmation",
        results: [],
      });
    return json([]);
  });
  const post = vi.fn(async (url: string, options?: RequestInit) => {
    const body = options?.body ? JSON.parse(String(options.body)) : undefined;
    posts.push({ url, body });
    if (url.endsWith("/auth/login"))
      return json({
        access_token: "token-r",
        token_type: "bearer",
        expires_at: "2099-01-01",
        actor: { id: "renter-a", role: "renter" },
      });
    if (url.endsWith("/sessions/session-9/messages"))
      return json({
        ...session("session-9"),
        message:
          "Bạn muốn tìm phòng ở khu vực nào và tổng ngân sách tháng là bao nhiêu?",
      });
    if (url.endsWith("/sessions")) return json(session("session-9"));
    return json({});
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) =>
      (options?.method || "GET") === "GET" ? get(url) : post(url, options),
    ),
  );
  render(<App />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Nhu cầu tìm phòng của bạn"), need);
  await user.click(screen.getByRole("button", { name: "Gửi nhu cầu" }));
  expect(screen.getByText(need)).toBeVisible();
  await screen.findByText(
    "Bạn vừa chia sẻ nhu cầu với trợ lý",
    {},
    { timeout: 2500 },
  );
  await user.type(screen.getByLabelText("Tên đăng nhập"), "renter-a");
  await user.type(screen.getByLabelText("Mật khẩu"), "test-password");
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await screen.findByText(/tổng ngân sách tháng là bao nhiêu/);
  expect(posts.find((call) => call.url.endsWith("/sessions"))).toBeTruthy();
  expect(
    posts.find((call) => call.url.endsWith("/sessions/session-9/messages"))
      ?.body,
  ).toEqual({ text: need });
  expect(sessionStorage.getItem("homematch.session.renter-a")).toBe(
    "session-9",
  );
}, 20000);
it("prefills the composer instead of auto-sending when a stored session exists", async () => {
  const api = new Api("test");
  const current = session("session-1");
  sessionStorage.setItem("homematch.session.renter-a", "session-1");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path.endsWith("/results")
      ? ({
          session_id: "session-1",
          status: "awaiting_confirmation",
          results: [],
        } as never)
      : (current as never),
  );
  const post = vi.spyOn(api, "post").mockResolvedValue(current as never);
  render(
    <RenterWorkspace
      api={api}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
      initialNeed={need}
      onNeedHandled={vi.fn()}
    />,
  );
  const input = await screen.findByLabelText("Nhu cầu của bạn");
  await waitFor(() => expect(input).toHaveValue(need));
  expect(post).not.toHaveBeenCalled();
}, 20000);
it("drops the pending landing need when a landlord signs in", async () => {
  const post = vi.fn(async (url: string) => {
    if (url.endsWith("/auth/login"))
      return json({
        access_token: "token-m",
        token_type: "bearer",
        expires_at: "2099-01-01",
        actor: { id: "owner-a", role: "owner" },
      });
    return json({});
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if ((options?.method || "GET") === "GET") {
        if (url.endsWith("/auth/me"))
          return json({ id: "owner-a", role: "owner" });
        if (url.endsWith("/landlord/rooms")) return json({ rooms: [] });
        return json([]);
      }
      return post(url);
    }),
  );
  render(<App />);
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Nhu cầu tìm phòng của bạn"), need);
  await user.click(screen.getByRole("button", { name: "Gửi nhu cầu" }));
  await screen.findByText(
    "Bạn vừa chia sẻ nhu cầu với trợ lý",
    {},
    { timeout: 2500 },
  );
  await user.type(screen.getByLabelText("Tên đăng nhập"), "owner-a");
  await user.type(screen.getByLabelText("Mật khẩu"), "test-password");
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await screen.findAllByText("Duyệt gợi ý");
  expect(
    post.mock.calls.filter(([url]) => url.endsWith("/sessions")),
  ).toHaveLength(0);
}, 20000);
