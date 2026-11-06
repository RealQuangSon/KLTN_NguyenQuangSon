import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api, ApiError } from "../api";
import {
  AdminWorkspace,
  OPEN_ADMIN_SESSION_KEY,
} from "../pages/AdminWorkspace";
import { RouterProvider } from "../router";
// FE-03: màn ticket hỗ trợ /quan-tri/ho-tro (hợp đồng README §7.2) và FE-04:
// thẻ "Chi phí AI ước tính" ở section van-hanh (hợp đồng README §7.3).
// Mock theo mẫu inbox-admin.test.tsx: new Api("t") + vi.spyOn(api, "get").
const tickets = [
  {
    id: "t1",
    session_id: "sess-aaaa",
    status: "requested",
    assignee: null,
    note: null,
    created_at: "2026-10-06T09:00:00Z",
    updated_at: "2026-10-06T09:00:00Z",
    resolved_at: null,
  },
  {
    id: "t2",
    session_id: "sess-bbbb",
    status: "resolved",
    assignee: "admin-a",
    note: "Đã gọi điện hỗ trợ khách",
    created_at: "2026-10-05T08:00:00Z",
    updated_at: "2026-10-05T10:00:00Z",
    resolved_at: "2026-10-05T10:00:00Z",
  },
];
const renderTickets = (api: Api) =>
  render(
    <RouterProvider>
      <AdminWorkspace api={api} section="ho-tro" />
    </RouterProvider>,
  );
it("renders the ticket list with status, assignee and note columns", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue(tickets as never);
  renderTickets(api);
  const table = await screen.findByRole("table");
  expect(within(table).getByText("sess-aaa")).toBeInTheDocument();
  expect(within(table).getByText("sess-bbb")).toBeInTheDocument();
  expect(
    within(table).getByText("Đã gọi điện hỗ trợ khách"),
  ).toBeInTheDocument();
  expect(within(table).getByText("admin-a")).toBeInTheDocument();
  expect(within(table).getByText("Chưa có")).toBeInTheDocument();
  // Nhãn trạng thái thật xuất hiện ở cả chip lọc và ô trạng thái trong bảng.
  expect(screen.getAllByText("Chờ xử lý").length).toBeGreaterThanOrEqual(2);
  expect(screen.getAllByText("Đã giải quyết").length).toBeGreaterThanOrEqual(2);
});
it("filters the table by status chips", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue(tickets as never);
  const user = userEvent.setup();
  renderTickets(api);
  expect(await screen.findByText("sess-aaa")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Đang xử lý" }));
  expect(screen.queryByText("sess-aaa")).not.toBeInTheDocument();
  expect(
    screen.getByText(/Không có ticket ở trạng thái này/),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Đã giải quyết" }));
  expect(screen.getByText("sess-bbb")).toBeInTheDocument();
  expect(screen.queryByText("sess-aaa")).not.toBeInTheDocument();
});
it("claims a ticket with PATCH in_progress and reloads the list", async () => {
  const api = new Api("t");
  const get = vi.spyOn(api, "get").mockResolvedValue(tickets as never);
  const patch = vi.spyOn(api, "patch").mockResolvedValue({} as never);
  const user = userEvent.setup();
  renderTickets(api);
  await user.click(await screen.findByRole("button", { name: "Nhận xử lý" }));
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith("/admin/support-tickets/t1", {
      status: "in_progress",
    }),
  );
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
});
it("requires a note before resolving and sends PATCH with the note", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue(tickets as never);
  const patch = vi.spyOn(api, "patch").mockResolvedValue({} as never);
  const user = userEvent.setup();
  renderTickets(api);
  // Nút trong dòng ticket, không phải chip lọc trùng tên.
  const table = await screen.findByRole("table");
  await user.click(
    within(table).getByRole("button", { name: "Đã giải quyết" }),
  );
  const dialog = screen.getByRole("dialog", {
    name: "Đánh dấu đã giải quyết",
  });
  expect(dialog).toBeInTheDocument();
  const confirm = screen.getByRole("button", {
    name: "Xác nhận đã giải quyết",
  });
  expect(confirm).toBeDisabled();
  await user.click(confirm);
  expect(patch).not.toHaveBeenCalled();
  await user.type(
    screen.getByLabelText("Ghi chú cách xử lý"),
    "Đã hỗ trợ qua điện thoại",
  );
  await user.click(confirm);
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith("/admin/support-tickets/t1", {
      status: "resolved",
      note: "Đã hỗ trợ qua điện thoại",
    }),
  );
});
it("reopens a resolved ticket with PATCH in_progress", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue(tickets as never);
  const patch = vi.spyOn(api, "patch").mockResolvedValue({} as never);
  const user = userEvent.setup();
  renderTickets(api);
  await user.click(await screen.findByRole("button", { name: "Mở lại" }));
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith("/admin/support-tickets/t2", {
      status: "in_progress",
    }),
  );
});
it("shows the 409 ticket_state message and reloads the list", async () => {
  const api = new Api("t");
  const get = vi.spyOn(api, "get").mockResolvedValue(tickets as never);
  const patch = vi
    .spyOn(api, "patch")
    .mockRejectedValue(
      new ApiError(
        409,
        "ticket_state",
        "Ticket đã đổi trạng thái; danh sách dưới đây là trạng thái mới nhất.",
      ),
    );
  const user = userEvent.setup();
  renderTickets(api);
  await user.click(await screen.findByRole("button", { name: "Nhận xử lý" }));
  expect(
    await screen.findByText(
      "Ticket đã đổi trạng thái; danh sách dưới đây là trạng thái mới nhất.",
    ),
  ).toBeInTheDocument();
  await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
});
it("opens the linked session in the transcript section via sessionStorage, not the URL", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue(tickets as never);
  const user = userEvent.setup();
  renderTickets(api);
  const link = await screen.findByRole("link", {
    name: "Mở phiên sess-aaa trong hội thoại AI",
  });
  expect(link).toHaveAttribute("href", "/quan-tri/hoi-thoai");
  await user.click(link);
  // Lưu id đầy đủ để section hoi-thoai gọi đúng /admin/transcripts/{session_id}.
  expect(sessionStorage.getItem(OPEN_ADMIN_SESSION_KEY)).toBe("sess-aaaa");
  expect(window.location.pathname).toBe("/quan-tri/hoi-thoai");
  expect(window.location.search).toBe("");
});
it("auto-opens the stored session once when the transcript section loads", async () => {
  sessionStorage.setItem(OPEN_ADMIN_SESSION_KEY, "sess-aaaa");
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path === "/admin/transcripts")
      return [
        {
          session_id: "sess-aaaa",
          user_id: "renter-a",
          turns: 1,
          started_at: "2026-10-06T09:00:00Z",
          last_at: "2026-10-06T09:00:00Z",
          flagged: 0,
        },
      ] as never;
    if (path === "/admin/transcripts/sess-aaaa")
      return {
        session_id: "sess-aaaa",
        turns: [
          {
            speaker: "user",
            text: "tôi muốn gặp người thật",
            intent: "handover",
            agent: null,
            created_at: "2026-10-06T09:00:00Z",
          },
        ],
      } as never;
    return {} as never;
  });
  render(<AdminWorkspace api={api} section="hoi-thoai" />);
  expect(
    await screen.findByText("tôi muốn gặp người thật"),
  ).toBeInTheDocument();
  // Đã tiêu thụ xong thì xóa để F5 không tự mở lại phiên cũ.
  expect(sessionStorage.getItem(OPEN_ADMIN_SESSION_KEY)).toBeNull();
});
// FE-04: chi phí AI quy ra VND, cả hai trường hợp của hợp đồng §7.3.
const renderOps = async (
  metrics: Record<string, unknown>,
  agentTurns?: Record<string, unknown>,
) => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path === "/admin/metrics") return metrics as never;
    if (path === "/admin/agent-turns")
      return (agentTurns ?? {
        turns: [],
        count: 0,
        p50_ms: null,
        p95_ms: null,
        fallback_ratio: null,
        cost_usd: 0,
        cost_usd_per_day: 0,
      }) as never;
    return [] as never;
  });
  render(<AdminWorkspace api={api} section="van-hanh" />);
};
it("shows the estimated AI cost with the price date when available", async () => {
  await renderOps({
    cost: {
      estimated_cost_vnd: 12345,
      price_effective_date: "2026-10-01",
      missing: [],
      basis: { input_tokens: 100 },
    },
  });
  expect(
    await screen.findByText(/≈ 12\.345 đ \(bảng giá ngày 01\/10\/2026\)/),
  ).toBeInTheDocument();
});
it("shows what is missing instead of an amount when cost is unknown and never shows 0", async () => {
  await renderOps({
    cost: {
      estimated_cost_vnd: null,
      price_effective_date: null,
      missing: ["token_price", "usage_log"],
      basis: {},
    },
  });
  expect(
    await screen.findByText("Chưa tính được — thiếu: token_price, usage_log"),
  ).toBeInTheDocument();
  expect(screen.queryByText(/0\s*đ/)).toBeNull();
});

// HN-05: bảng lượt agent với p50/p95, tỉ lệ fallback và chi phí phiên.
it("shows recent agent turns with latency and cost aggregates", async () => {
  await renderOps(
    {
      cost: {
        estimated_cost_vnd: null,
        price_effective_date: null,
        missing: [],
        basis: {},
      },
    },
    {
      turns: [
        {
          turn_id: "t1",
          session_id: "12345678-abcdef",
          started_at: "2026-11-06T09:30:00+00:00",
          duration_ms: 2100,
          agent_mode: "loop",
          llm_calls: 2,
          input_tokens: 900,
          output_tokens: 210,
          cost_usd: 0.0004,
          decided_by: "jev",
          outcome: "answered",
          error_code: null,
        },
        {
          turn_id: "t2",
          session_id: "12345678-abcdef",
          started_at: "2026-11-06T09:31:00+00:00",
          duration_ms: 3200,
          agent_mode: "graph_fallback",
          llm_calls: 0,
          input_tokens: null,
          output_tokens: null,
          cost_usd: null,
          decided_by: null,
          outcome: "error",
          error_code: "ai_unavailable",
        },
      ],
      count: 2,
      p50_ms: 2100,
      p95_ms: 3200,
      fallback_ratio: 0.5,
      cost_usd: 0.0004,
      cost_usd_per_day: 0.0004,
    },
  );
  expect(
    await screen.findByText(
      /2 lượt · p50 2\.100 ms · p95 3\.200 ms · fallback 50\.0%/,
    ),
  ).toBeInTheDocument();
  expect(screen.getByText("loop")).toBeInTheDocument();
  expect(screen.getByText(/answered/)).toBeInTheDocument();
  expect(screen.getByText(/error · ai_unavailable/)).toBeInTheDocument();
  expect(screen.getByText("chưa báo")).toBeInTheDocument();
});
it("shows an empty note when no agent turns exist yet", async () => {
  await renderOps({
    cost: {
      estimated_cost_vnd: null,
      price_effective_date: null,
      missing: [],
      basis: {},
    },
  });
  expect(
    await screen.findByText("Chưa có lượt agent nào được ghi."),
  ).toBeInTheDocument();
});
