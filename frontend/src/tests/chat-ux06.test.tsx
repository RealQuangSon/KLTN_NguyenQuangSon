import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { Api, ApiError } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { RouterProvider } from "../router";
import type { Session } from "../types";
import { session } from "./fixtures";

// UX-06: khung chat hiện tin người dùng ngay, trạng thái tiếng Việt, một nút bước.

const base = session();
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const setup = (turnImpl: (...args: any[]) => Promise<unknown>) => {
  const api = new Api("token");
  sessionStorage.setItem("homematch.session.renter-a", "session-1");
  vi.spyOn(api, "get").mockImplementation(
    async (path) =>
      (path.endsWith("/results")
        ? {
            session_id: "session-1",
            status: "awaiting_confirmation",
            results: [],
          }
        : base) as never,
  );
  const turn = vi.spyOn(api, "turn").mockImplementation(turnImpl as never);
  render(
    <RouterProvider>
      <RenterWorkspace
        api={api}
        actor={{ id: "renter-a", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  return turn;
};
afterEach(() => vi.unstubAllGlobals());

it("shows the user's message and a Vietnamese status before the API answers", async () => {
  let release: (value: unknown) => void = () => {};
  setup(async (_p: string, _b: unknown, onStep: (s: unknown) => void) => {
    onStep({
      name: "update_needs",
      kind: "tool",
      detail: "Đã ghi nhu cầu vào hồ sơ nháp",
    });
    await new Promise((resolve) => (release = resolve));
    return {
      ...base,
      message: "Xong rồi.",
      steps: ["route: Phân tích tin nhắn", "update_needs: Đã ghi nhu cầu"],
    } as unknown as Session;
  });
  const user = userEvent.setup();
  await user.type(
    await screen.findByPlaceholderText("Nhắn cho HomeMatch Agent…"),
    "tìm phòng ở bình thạnh",
  );
  await user.keyboard("{Enter}");
  expect(await screen.findByText("tìm phòng ở bình thạnh")).toBeInTheDocument();
  expect(await screen.findByText(/Đang ghi nhu cầu/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/update_needs|route\b/);
  release(null);
  await screen.findByText("Xong rồi.");
  // Chỉ một nút "Đã xử lý qua N bước" cho lượt, không dòng bản đồ preview.
  expect(screen.getAllByRole("button", { name: /Đã xử lý qua/ })).toHaveLength(
    1,
  );
  expect(screen.queryByText(/Đã mở bản đồ/)).toBeNull();
  expect(screen.getAllByText("tìm phòng ở bình thạnh")).toHaveLength(1);
});

it("marks a failed send and lets the user resend it", async () => {
  let calls = 0;
  setup(async () => {
    calls += 1;
    if (calls === 1) throw new ApiError(500, "server_error", "Mất kết nối");
    return { ...base, message: "Đã nhận." } as unknown as Session;
  });
  const user = userEvent.setup();
  await user.type(
    await screen.findByPlaceholderText("Nhắn cho HomeMatch Agent…"),
    "phòng quận 7",
  );
  await user.keyboard("{Enter}");
  expect(await screen.findByText("phòng quận 7")).toBeInTheDocument();
  await user.click(await screen.findByRole("button", { name: "Gửi lại" }));
  await screen.findByText("Đã nhận.");
  await waitFor(() => expect(screen.queryByText(/Chưa gửi được/)).toBeNull());
  expect(screen.getAllByText("phòng quận 7")).toHaveLength(1);
});

it("UX-02: the frontend never builds or posts a profile after a chat turn", async () => {
  const api = new Api("token");
  sessionStorage.setItem("homematch.session.renter-a", "session-1");
  vi.spyOn(api, "get").mockImplementation(
    async (path) =>
      (path.endsWith("/results")
        ? {
            session_id: "session-1",
            status: "awaiting_confirmation",
            results: [],
          }
        : {
            ...base,
            draft: { ...base.draft, city: "TP.HCM", budget_hint_vnd: 4000000 },
          }) as never,
  );
  vi.spyOn(api, "turn").mockResolvedValue({ ...base, message: "Ok." } as never);
  const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
  render(
    <RouterProvider>
      <RenterWorkspace
        api={api}
        actor={{ id: "renter-a", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  const user = userEvent.setup();
  await user.type(
    await screen.findByPlaceholderText("Nhắn cho HomeMatch Agent…"),
    "phòng bình thạnh tầm 4 triệu",
  );
  await user.keyboard("{Enter}");
  await screen.findByText("Ok.");
  await new Promise((resolve) => setTimeout(resolve, 100));
  expect(
    post.mock.calls.filter(([path]) => String(path).endsWith("/confirm")),
  ).toHaveLength(0);
});
