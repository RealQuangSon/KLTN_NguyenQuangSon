import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import App from "../App";
import { Api } from "../api";
import { ViewingForm } from "../components/ViewingPanel";
import { deferred, room } from "./fixtures";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
it("clears private data on logout and ignores an expired response from the prior actor after new login", async () => {
  sessionStorage.setItem("homematch.token", "token-a");
  sessionStorage.setItem("homematch.session.renter-a", "session-a");
  const old = deferred<Response>();
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      const headers = options?.headers as Record<string, string>;
      if (url.endsWith("/auth/me"))
        return json({
          id:
            headers.Authorization === "Bearer token-a"
              ? "renter-a"
              : "renter-b",
          role: "renter",
        });
      if (url.endsWith("/sessions/session-a")) return old.promise;
      if (url.endsWith("/auth/logout")) return json({});
      if (url.endsWith("/auth/login"))
        return json({
          access_token: "token-b",
          actor: { id: "renter-b", role: "renter" },
          token_type: "bearer",
          expires_at: "2099-01-01",
        });
      return json([]);
    }),
  );
  render(<App />);
  await screen.findByText("renter-a");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Đăng xuất" }));
  expect(sessionStorage.getItem("homematch.session.renter-a")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await user.type(screen.getByLabelText("Tên đăng nhập"), "renter-b");
  await user.type(screen.getByLabelText("Mật khẩu"), "test-password");
  await user.click(screen.getByRole("button", { name: "Đăng nhập" }));
  await screen.findByText("renter-b");
  await act(async () => {
    old.resolve(
      json(
        { error: { code: "unauthorized", message: "expired old token" } },
        401,
      ),
    );
    await old.promise;
  });
  expect(screen.getByText("renter-b")).toBeVisible();
  expect(sessionStorage.getItem("homematch.token")).toBe("token-b");
}, 20000);
it("manually retries a viewing with the exact payload/key instead of issuing a new action", async () => {
  const api = new Api("test");
  const post = vi
    .spyOn(api, "post")
    .mockRejectedValueOnce(new Error("Mất mạng"))
    .mockResolvedValueOnce({ status: "requested" });
  const done = vi.fn();
  render(
    <ViewingForm
      api={api}
      sessionId="session-1"
      room={room()}
      onDone={done}
      onCancel={vi.fn()}
    />,
  );
  const user = userEvent.setup();
  const time = new Date(Date.now() + 86400000 * 2).toISOString().slice(0, 16);
  await user.type(screen.getByLabelText(/Thời gian xem/), time);
  await user.click(screen.getByRole("button", { name: "Gửi yêu cầu xem" }));
  await screen.findByText("Mất mạng");
  await user.click(
    screen.getByRole("button", { name: "Thử gửi lại cùng yêu cầu" }),
  );
  await waitFor(() => expect(done).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenCalledTimes(2);
  expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
  expect(
    (post.mock.calls[0][1] as { requested_at: string }).requested_at,
  ).toMatch(/Z$/);
});
