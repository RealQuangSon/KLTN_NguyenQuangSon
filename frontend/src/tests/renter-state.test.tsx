import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { ProfileForm } from "../components/ProfileForm";
import type { Results } from "../types";
import { deferred, profile, room, session } from "./fixtures";
it("limits comparison to 3 visible rooms and sends the current selected IDs to the server", async () => {
  const api = new Api("test");
  const current = session();
  sessionStorage.setItem("homematch.session.renter-a", current.session_id);
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path.endsWith("/results")
      ? {
          session_id: current.session_id,
          run_id: "run-1",
          status: "published",
          results: [1, 2, 3, 4].map((n) => room(`room-${n}`)),
        }
      : (current as never),
  );
  const post = vi.spyOn(api, "post").mockImplementation(
    async (_path, body) =>
      ({
        run_id: "run-1",
        items: (body as { room_ids: string[] }).room_ids.map((id) => room(id)),
      }) as never,
  );
  render(
    <RenterWorkspace
      api={api}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  const scrolled = vi.spyOn(Element.prototype, "scrollIntoView");
  const user = userEvent.setup();
  await screen.findByText("Phòng riêng room-1", {}, { timeout: 4000 });
  // Thẻ nhỏ dạng lưới: chip so sánh icon-only có nhãn "So sánh căn này".
  const buttons = screen.getAllByRole("button", { name: /^So sánh căn này$/ });
  await user.click(buttons[0]);
  await user.click(buttons[1]);
  await user.click(buttons[2]);
  await user.click(buttons[3]);
  expect(screen.getByRole("alert")).toHaveTextContent("tối đa 3 phòng");
  await user.click(screen.getByRole("button", { name: "So sánh lựa chọn" }));
  expect(post).toHaveBeenCalledWith("/sessions/session-1/compare", {
    room_ids: ["room-1", "room-2", "room-3"],
  });
  const heading = await screen.findByText("So sánh các lựa chọn");
  expect(heading).toBeVisible();
  // Bảng nằm dưới danh sách phòng: phải đưa vào tầm nhìn, nếu không nút bấm như không có tác dụng.
  expect(scrolled.mock.contexts).toContain(heading.closest("section"));
}, 20000);
it("keeps the verification panel on screen while results are re-read in the background", async () => {
  const api = new Api("test");
  const current = session();
  sessionStorage.setItem("homematch.session.renter-a", current.session_id);
  const held = {
    session_id: current.session_id,
    run_id: "run-1",
    status: "needs_verification",
    results: [],
  };
  const slow = deferred<Results>();
  let reads = 0;
  vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (!path.endsWith("/results")) return current as never;
    reads += 1;
    return (reads === 1 ? held : slow.promise) as never;
  });
  const intervals: (() => void)[] = [];
  const realInterval = window.setInterval.bind(window);
  vi.spyOn(globalThis, "setInterval").mockImplementation(((
    callback: () => void,
    ms: number,
  ) => {
    if (ms === 5000) intervals.push(callback);
    return realInterval(() => {}, 1_000_000);
  }) as never);
  render(
    <RenterWorkspace
      api={api}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  const panel = await screen.findByText("Cần xác minh thông tin");
  await waitFor(() => expect(intervals.length).toBeGreaterThan(0));
  act(() => intervals[intervals.length - 1]());
  await waitFor(() => expect(reads).toBe(2));
  expect(screen.queryByText("Đang soạn danh sách…")).toBeNull();
  expect(panel).toBeInTheDocument();
  await act(async () => {
    slow.resolve(held as never);
    await slow.promise;
  });
  expect(panel).toBeInTheDocument();
}, 20000);
it("ignores a delayed published result after a new session has replaced its scope", async () => {
  const api = new Api("test");
  const delayed = deferred<Results>();
  const previous = session();
  sessionStorage.setItem("homematch.session.renter-a", previous.session_id);
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/sessions/session-1"
      ? previous
      : path === "/sessions/session-1/results"
        ? delayed.promise
        : ({
            session_id: "session-2",
            status: "awaiting_confirmation",
            results: [],
          } as never),
  );
  vi.spyOn(api, "post").mockResolvedValue({
    ...session("session-2"),
    active_run_id: null,
    confirmed_profile: null,
  });
  render(
    <RenterWorkspace
      api={api}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  await screen.findByRole("button", { name: "Phiên mới" });
  await userEvent.click(screen.getByRole("button", { name: "Phiên mới" }));
  await waitFor(() =>
    expect(sessionStorage.getItem("homematch.session.renter-a")).toBe(
      "session-2",
    ),
  );
  await act(async () => {
    delayed.resolve({
      session_id: "session-1",
      run_id: "run-old",
      status: "published",
      results: [room("secret-old")],
    });
    await delayed.promise;
  });
  expect(screen.queryByText("Phòng riêng secret-old")).not.toBeInTheDocument();
}, 20000);
it("applies draft corrections while retaining the user-entered financial scenario", async () => {
  const onConfirm = vi.fn().mockResolvedValue(true),
    onSave = vi.fn().mockResolvedValue(true),
    onDirty = vi.fn();
  const props = {
    draft: session().draft,
    revision: 1,
    confirmed: profile,
    busy: false,
    onConfirm,
    onSave,
    onDirty,
  };
  const { rerender } = render(<ProfileForm {...props} />);
  const user = userEvent.setup();
  const budget = screen.getByLabelText("Ngân sách tổng tháng (VND)");
  await user.clear(budget);
  await user.type(budget, "4000000");
  rerender(
    <ProfileForm
      {...props}
      revision={2}
      draft={{
        ...props.draft,
        area: "Quận 1",
        people: 2,
        preferences: ["quiet"],
      }}
    />,
  );
  await user.click(
    screen.getByRole("button", { name: "Áp dụng dữ liệu hội thoại" }),
  );
  expect(screen.getByLabelText("Khu vực")).toHaveValue("Quận 1");
  expect(screen.getByLabelText("Số người")).toHaveValue(2);
  expect(budget).toHaveValue(4000000);
  fireEvent.submit(
    screen
      .getByRole("button", { name: "Xác nhận & tìm phòng" })
      .closest("form")!,
  );
  await waitFor(() =>
    expect(onConfirm).toHaveBeenCalledWith(
      expect.objectContaining({
        max_monthly_cost_vnd: 4000000,
        area: "Quận 1",
        preferences: ["quiet"],
        scenario: expect.objectContaining({
          people: 2,
          electricity_kwh: "140",
        }),
      }),
    ),
  );
});
it("offers the newer conversation draft after prior confirmation even without a local edit", async () => {
  const props = {
    draft: session().draft,
    revision: 1,
    confirmed: profile,
    confirmedVersion: 1,
    busy: false,
    onConfirm: vi.fn().mockResolvedValue(true),
    onSave: vi.fn().mockResolvedValue(true),
    onDirty: vi.fn(),
  };
  const { rerender } = render(<ProfileForm {...props} />);
  rerender(
    <ProfileForm
      {...props}
      revision={2}
      draft={{
        ...props.draft,
        area: "Quận 1",
        people: 2,
        preferences: ["quiet"],
      }}
    />,
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Áp dụng dữ liệu hội thoại" }),
  );
  expect(screen.getByLabelText("Khu vực")).toHaveValue("Quận 1");
  expect(screen.getByLabelText("Số người")).toHaveValue(2);
  expect(screen.getByLabelText("Ngân sách tổng tháng (VND)")).toHaveValue(
    3500000,
  );
  expect(props.onDirty).toHaveBeenCalledWith(true);
});
it("shows the reply chips the server chose and sends one when clicked", async () => {
  const api = new Api("test");
  const current = session();
  sessionStorage.setItem("homematch.session.renter-a", current.session_id);
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path.endsWith("/results")
      ? {
          session_id: current.session_id,
          run_id: "run-1",
          status: "needs_verification",
          results: [],
          suggested_prompts: ["Nới ngân sách", "Đổi khu vực khác"],
        }
      : (current as never),
  );
  const turn = vi.spyOn(api, "turn").mockResolvedValue({
    ...current,
    intent: "find_room",
    status: "needs_verification",
    message: "Đã ghi nhận",
  } as never);
  render(
    <RenterWorkspace
      api={api}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  const chips = await screen.findByRole("group", { name: "Gợi ý trả lời" });
  expect(chips).toHaveTextContent("Nới ngân sách");
  expect(screen.queryByText("Tính tổng chi phí")).toBeNull();
  await userEvent
    .setup()
    .click(screen.getByRole("button", { name: "Đổi khu vực khác" }));
  expect(turn.mock.calls[0][1]).toMatchObject({ text: "Đổi khu vực khác" });
}, 20000);
