import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { RouterProvider } from "../router";
import type { ChatHistory } from "../types";
import { session } from "./fixtures";

const stamp = new Date().toISOString();
const history = (items: ChatHistory["items"]): ChatHistory => ({
  retention_days: 90,
  items,
});
const entry = (id: string, title: string, turns = 1) => ({
  session_id: id,
  title,
  turns,
  started_at: stamp,
  last_at: stamp,
});

function setup(list: ChatHistory, welcome = false) {
  const api = new Api("test");
  sessionStorage.clear();
  if (!welcome) sessionStorage.setItem("homematch.session.renter", "session-1");
  const get = vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path === "/sessions") return list as never;
    if (path === "/sessions/session-2")
      return { ...session("session-2"), active_run_id: null } as never;
    if (path === "/sessions/session-2/transcript")
      return {
        session_id: "session-2",
        retention_days: 90,
        messages: [
          { role: "user", text: "Tìm phòng Cầu Giấy", created_at: stamp },
          {
            role: "assistant",
            text: "Bạn có ngân sách bao nhiêu?",
            created_at: stamp,
          },
        ],
      } as never;
    if (path.endsWith("/results"))
      return {
        session_id: "x",
        run_id: null,
        status: "awaiting_confirmation",
        results: [],
      } as never;
    return session() as never;
  });
  const post = vi.spyOn(api, "post").mockResolvedValue({
    ...session("session-3"),
    active_run_id: null,
  });
  render(
    <RouterProvider>
      <RenterWorkspace
        api={api}
        actor={{ id: "renter", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  return { get, post };
}

beforeEach(() => vi.restoreAllMocks());

it("lists saved chats, marks the current one and reopens another from the server transcript", async () => {
  const { get } = setup(
    history([
      entry("session-1", "Phòng Quận 7 dưới 5 triệu", 3),
      entry("session-2", "Tìm phòng Cầu Giấy"),
    ]),
  );
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Lịch sử trò chuyện" }),
  );
  const panel = await screen.findByRole("region", {
    name: "Lịch sử trò chuyện",
  });
  const rows = await within(panel).findAllByRole("button", { name: /lượt/ });
  expect(rows).toHaveLength(2);
  expect(rows[0]).toHaveAttribute("aria-current", "true");
  expect(rows[1]).not.toHaveAttribute("aria-current");
  expect(within(panel).getByText(/3 lượt/)).toBeInTheDocument();
  expect(within(panel).getByText(/lưu 90 ngày/)).toBeInTheDocument();
  await user.click(rows[1]);
  await waitFor(() =>
    expect(get).toHaveBeenCalledWith("/sessions/session-2/transcript"),
  );
  expect(get).toHaveBeenCalledWith("/sessions/session-2");
  expect(await screen.findByText("Bạn có ngân sách bao nhiêu?")).toBeVisible();
  expect(screen.getByText("Tìm phòng Cầu Giấy")).toBeVisible();
  expect(
    screen.queryByRole("region", { name: "Lịch sử trò chuyện" }),
  ).toBeNull();
  expect(sessionStorage.getItem("homematch.session.renter")).toBe("session-2");
});

it("starts a new chat from the history panel", async () => {
  const { post } = setup(history([entry("session-1", "Phòng Quận 7")]));
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Lịch sử trò chuyện" }),
  );
  const panel = await screen.findByRole("region", {
    name: "Lịch sử trò chuyện",
  });
  await user.click(
    within(panel).getByRole("button", { name: "Cuộc trò chuyện mới" }),
  );
  await waitFor(() => expect(post).toHaveBeenCalledWith("/sessions"));
  await waitFor(() =>
    expect(
      screen.queryByRole("region", { name: "Lịch sử trò chuyện" }),
    ).toBeNull(),
  );
});

it("shows the empty state", async () => {
  setup(history([]));
  await userEvent.click(
    await screen.findByRole("button", { name: "Lịch sử trò chuyện" }),
  );
  expect(
    await screen.findByText("Chưa có cuộc trò chuyện nào được lưu."),
  ).toBeVisible();
});

const recent = () =>
  screen.queryByRole("region", { name: "Cuộc trò chuyện gần đây" });

it("welcome screen lists recent chats and reopens one", async () => {
  const { get } = setup(
    history([entry("session-2", "Tìm phòng Cầu Giấy", 2)]),
    true,
  );
  const section = await screen.findByRole("region", {
    name: "Cuộc trò chuyện gần đây",
  });
  const user = userEvent.setup();
  await user.click(within(section).getByRole("button", { name: /Cầu Giấy/ }));
  await waitFor(() =>
    expect(get).toHaveBeenCalledWith("/sessions/session-2/transcript"),
  );
  expect(get).toHaveBeenCalledWith("/sessions/session-2");
  expect(await screen.findByText("Bạn có ngân sách bao nhiêu?")).toBeVisible();
  expect(recent()).toBeNull();
});

it("welcome screen shows no recent section when history is empty", async () => {
  const { get } = setup(history([]), true);
  await screen.findByText(/nơi ở/);
  await waitFor(() => expect(get).toHaveBeenCalledWith("/sessions"));
  expect(recent()).toBeNull();
});

it("welcome screen caps recent chats at 5 and expands on demand", async () => {
  setup(
    history(Array.from({ length: 7 }, (_, n) => entry(`s-${n}`, `Chat ${n}`))),
    true,
  );
  const section = await screen.findByRole("region", {
    name: "Cuộc trò chuyện gần đây",
  });
  expect(within(section).getAllByRole("listitem")).toHaveLength(5);
  await userEvent.click(
    within(section).getByRole("button", { name: "Xem tất cả (7)" }),
  );
  expect(within(section).getAllByRole("listitem")).toHaveLength(7);
});
