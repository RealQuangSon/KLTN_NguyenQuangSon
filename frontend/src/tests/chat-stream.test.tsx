import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Api, ApiError } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { RouterProvider } from "../router";
import type { Session } from "../types";
import { cost, room, session } from "./fixtures";

// WS-02: luồng chat ưu tiên stream bước xử lý (NDJSON); hiển thị "Đã xử lý qua
// N bước" theo bước thật; đứt luồng → thử lại → fallback endpoint cũ.

function ndjsonResponse(lines: unknown[]): Response {
  const body = lines.map((line) => JSON.stringify(line) + "\n").join("");
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "application/x-ndjson" },
  });
}

const baseSession = session();
const doneData = {
  ...baseSession,
  intent: "find_room",
  status: "needs_clarification",
  questions: null,
  message:
    "Mình hiểu HUST ở Đại Cồ Việt, Hai Bà Trưng; kết quả đã hiện bên phải.",
  usage: { logical_calls: 2, tokens: 10, mode: "openai" },
  steps: [
    "find_place: điểm mốc Đại học Bách Khoa Hà Nội (Hà Nội)",
    "search_rooms: 3 căn khớp",
  ],
} as unknown as Session & { steps: string[] };

describe("Api.streamTurn", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("parses step events and resolves the done payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        ndjsonResponse([
          {
            type: "step",
            step: {
              name: "route",
              kind: "router",
              detail: "AI phân tích nhu cầu",
            },
          },
          {
            type: "step",
            step: { name: "find_place", kind: "tool", detail: "điểm mốc HUST" },
          },
          { type: "done", data: doneData },
        ]),
      ),
    );
    const api = new Api("token");
    const seen: string[] = [];
    const data = await api.streamTurn<typeof doneData>(
      "/sessions/s/messages/stream",
      {},
      (step) => seen.push(`${step.name}: ${step.detail}`),
    );
    expect(seen).toEqual([
      "route: AI phân tích nhu cầu",
      "find_place: điểm mốc HUST",
    ]);
    expect(data.steps).toHaveLength(2);
  });

  it("throws a friendly ApiError when the stream breaks before done", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        ndjsonResponse([
          {
            type: "step",
            step: { name: "route", kind: "router", detail: "x" },
          },
        ]),
      ),
    );
    const api = new Api("token");
    await expectAsyncError(api.streamTurn("/sessions/s/messages/stream", {}));
  });
});

describe("Api.turn retry policy", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("retries a broken stream once and then falls back to the plain POST", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("không phải ndjson", { status: 200 }))
      .mockRejectedValueOnce(new TypeError("connection reset"));
    vi.stubGlobal("fetch", fetchMock);
    const api = new Api("token");
    const post = vi
      .spyOn(api, "post")
      .mockResolvedValue(doneData as unknown as never);
    const data = await api.turn<typeof doneData>(
      "/sessions/s/messages/stream",
      {},
    );
    expect(data.steps).toHaveLength(2);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(post).toHaveBeenCalledTimes(1);
  });

  it("does not retry a 4xx business error", async () => {
    const fetchMock = vi.fn(async () =>
      Response.json(
        { error: { code: "budget_exceeded", message: "Hết ngân sách phiên." } },
        { status: 429 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);
    const api = new Api("token");
    const post = vi.spyOn(api, "post");
    await expectAsyncError(api.turn("/sessions/s/messages", {}));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(post).not.toHaveBeenCalled();
  });
});

it("renders the real step list under the assistant reply", async () => {
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
        : baseSession) as never,
  );
  const turnSpy = vi
    .spyOn(api, "turn")
    .mockImplementation(async (_path, _body, onStep) => {
      onStep?.({ name: "find_place", kind: "tool", detail: "điểm mốc HUST" });
      return doneData as unknown as never;
    });
  render(
    <RouterProvider>
      <RenterWorkspace
        api={api}
        actor={{ id: "renter-a", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  const composer = await screen.findByPlaceholderText(
    "Nhắn cho HomeMatch Agent…",
  );
  const user = userEvent.setup();
  await user.type(composer, "gần HUST");
  await user.keyboard("{Enter}");
  expect(turnSpy).toHaveBeenCalled();
  await screen.findByText(/Mình hiểu/);
  const disclosure = await screen.findByRole("button", {
    name: /Đã xử lý qua 2 bước/,
  });
  await user.click(disclosure);
  await screen.findByText(/find_place: điểm mốc Đại học Bách Khoa Hà Nội/);
  expect(screen.getByText(/search_rooms: 3 căn khớp/)).toBeInTheDocument();
}, 20000);

async function expectAsyncError(promise: Promise<unknown>) {
  await expect(promise).rejects.toSatisfy(
    (error: unknown) =>
      error instanceof ApiError &&
      ["stream_broken", "budget_exceeded"].includes(error.code),
  );
}

it("sends the workspace context and applies the agent-selected view", async () => {
  const api = new Api("token");
  sessionStorage.setItem("homematch.session.renter-a", "session-1");
  vi.spyOn(api, "get").mockImplementation(
    async (path) =>
      (path.endsWith("/results")
        ? {
            session_id: "session-1",
            run_id: "run-1",
            status: "published",
            profile_version: 1,
            results: [
              {
                ...room("room-1"),
                cost: { ...cost, monthly_total_vnd: 3230000 },
                components: { location: 0.4 },
              },
            ],
          }
        : baseSession) as never,
  );
  const turnSpy = vi
    .spyOn(api, "turn")
    .mockImplementation(async (_path, body, onStep) => {
      onStep?.({
        name: "confirm_and_search",
        kind: "tool",
        detail: "3 căn khớp",
      });
      return {
        ...doneData,
        message: "Kết quả đã hiện ở khung bên phải.",
        view: "detail",
        view_payload: { room_id: "room-1" },
        anchor: {
          label: "Đại học Bách Khoa Hà Nội",
          latitude: 21.004,
          longitude: 105.8431,
          uncertainty_m: 300,
        },
        turn_id: "turn-1",
      } as unknown as never;
    });
  render(
    <RouterProvider>
      <RenterWorkspace
        api={api}
        actor={{ id: "renter-a", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  const composer = await screen.findByPlaceholderText(
    "Nhắn cho HomeMatch Agent…",
  );
  const user = userEvent.setup();
  await user.type(composer, "căn này thế nào");
  await user.keyboard("{Enter}");
  // Workspace context gửi kèm mỗi lượt (căn chọn/≤30 căn hiện/≤4 căn chú ý).
  expect(turnSpy.mock.calls[0][1]).toMatchObject({
    text: "căn này thế nào",
    workspace: {
      view: null,
      visible_room_ids: ["room-1"],
      focus_room_ids: [],
    },
  });
  // View do agent chọn: detail → panel chi tiết căn xuất hiện, nút về bố cục thường.
  const panel = await screen.findByLabelText("Chi tiết căn đang chọn");
  await user.click(
    within(panel).getByRole("button", { name: /Bố cục thường/ }),
  );
  await waitFor(() =>
    expect(
      screen.queryByText("CHI TIẾT CĂN ĐANG CHỌN"),
    ).not.toBeInTheDocument(),
  );
}, 20000);

it("AG-11: chip làm rõ render trên đầu câu trả lời và gửi PATCH clarify", async () => {
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
        : baseSession) as never,
  );
  vi.spyOn(api, "turn").mockResolvedValue({
    ...doneData,
    message: "Mình tìm được vài căn gần Phú Mỹ Hưng.",
    clarification: {
      id: "clarify-destination",
      field: "destination",
      question: "Bạn muốn ở gần điểm đến trong bán kính nào?",
      options: [
        {
          id: "opt-0",
          label: "2 km · 12 căn",
          detail: "",
          probability: 0.4,
          patch: { set: { destination_radius_m: 2000 } },
        },
        {
          id: "opt-1",
          label: "5 km · 31 căn",
          detail: "",
          probability: 0.6,
          patch: { set: { destination_radius_m: 5000 } },
        },
      ],
      decided_by: "rules",
    },
  } as unknown as never);
  const patch = vi.spyOn(api, "patch").mockResolvedValue({} as never);
  render(
    <RouterProvider>
      <RenterWorkspace
        api={api}
        actor={{ id: "renter-a", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  const composer = await screen.findByPlaceholderText(
    "Nhắn cho HomeMatch Agent…",
  );
  const user = userEvent.setup();
  await user.type(composer, "gần Phú Mỹ Hưng");
  await user.keyboard("{Enter}");
  const group = await screen.findByRole("group", { name: "Lựa chọn làm rõ" });
  await user.click(
    within(group).getByRole("button", { name: /5 km · 31 căn/ }),
  );
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith(
      "/sessions/session-1/draft",
      expect.objectContaining({
        set: { destination_radius_m: 5000 },
        source: "clarify",
      }),
    ),
  );
}, 20000);
