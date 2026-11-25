import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { RouterProvider } from "../router";
import { clearLocal, clearLoginStorage } from "../session-storage";
import { session } from "./fixtures";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
it("keeps per-account consultation session keys when signing in, wipes everything on logout", () => {
  sessionStorage.setItem("homematch.token", "token-old");
  sessionStorage.setItem("homematch.session.renter", "session-a");
  sessionStorage.setItem("homematch.session.owner2", "session-o");
  sessionStorage.setItem("homematch.tmp", "x");
  clearLoginStorage();
  // Đăng nhập/chuyển trải nghiệm: khóa phiên giữ nguyên — quay lại vai là
  // dùng được trợ lý ngay với phiên cũ.
  expect(sessionStorage.getItem("homematch.session.renter")).toBe("session-a");
  expect(sessionStorage.getItem("homematch.session.owner2")).toBe("session-o");
  expect(sessionStorage.getItem("homematch.token")).toBeNull();
  expect(sessionStorage.getItem("homematch.tmp")).toBeNull();
  // Đăng xuất: xoá sạch kể cả khóa phiên (dữ liệu riêng tư trên máy này).
  clearLocal();
  expect(sessionStorage.getItem("homematch.session.renter")).toBeNull();
});
it("lets a fresh renter type the first message right away: creates the session and sends in one step", async () => {
  const posts: { url: string; body: { text?: string } }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if (options?.method === "POST") {
        const body = JSON.parse(String(options.body ?? "{}"));
        posts.push({ url, body });
        if (url.endsWith("/sessions"))
          return json({ ...session("session-fresh"), message: undefined });
        if (url.endsWith("/sessions/session-fresh/messages/stream"))
          // WS-02: luồng chat trả NDJSON, dòng cuối là done + data đầy đủ.
          return new Response(
            JSON.stringify({
              type: "done",
              data: {
                ...session("session-fresh"),
                intent: "find_room",
                status: "needs_clarification",
                message:
                  "Mình đã ghi nhận nhu cầu. Kiểm tra hồ sơ bên phải nhé.",
                usage: { logical_calls: 1, tokens: 7, mode: "demo_rules" },
              },
            }) + "\n",
            {
              status: 200,
              headers: { "Content-Type": "application/x-ndjson" },
            },
          );
        if (url.endsWith("/sessions/session-fresh/messages"))
          return json({
            ...session("session-fresh"),
            message: "Mình đã ghi nhận nhu cầu. Kiểm tra hồ sơ bên phải nhé.",
          });
      }
      return json([]);
    }),
  );
  render(
    // Màn chào mới có chip "Tìm nhanh" dạng Link của router → cần provider.
    <RouterProvider>
      <RenterWorkspace
        api={new Api(null)}
        actor={{ id: "renter", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  // Không còn bước chặn: composer hiện ngay khi chưa có phiên.
  const composer = screen.getByLabelText("Nhu cầu tìm phòng");
  expect(composer).toBeVisible();
  const user = userEvent.setup();
  await user.type(composer, "Tìm nhà trọ 4 triệu một tháng gần HUST");
  await user.click(screen.getByRole("button", { name: /Nhắn cho trợ lý/ }));
  // Đúng thứ tự: tạo phiên rồi gửi câu đầu tiên.
  expect(posts.map((p) => p.url.split("/api").pop())).toEqual([
    "/sessions",
    "/sessions/session-fresh/messages/stream",
  ]);
  expect(posts[1].body.text).toBe("Tìm nhà trọ 4 triệu một tháng gần HUST");
  // Phiên mở: câu của người dùng + phản hồi trợ lý trong khung chat.
  expect(
    await screen.findByText("Tìm nhà trọ 4 triệu một tháng gần HUST"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Mình đã ghi nhận nhu cầu. Kiểm tra hồ sơ bên phải nhé."),
  ).toBeInTheDocument();
  expect(sessionStorage.getItem("homematch.session.renter")).toBe(
    "session-fresh",
  );
});
