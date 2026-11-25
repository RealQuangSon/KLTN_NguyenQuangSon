import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { RouterProvider } from "../router";
import { session } from "./fixtures";
const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
it("replaces a clicked clarification chip with the choice and a confirmation line", async () => {
  sessionStorage.clear();
  const patches: unknown[] = [];
  const chip = {
    id: "opt-0",
    label: "Trần TỔNG THÁNG (gồm phí)",
    patch: { set: { budget_scope: "total" } },
    action: "patch",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if (options?.method === "PATCH") {
        patches.push(JSON.parse(String(options.body)));
        return json({
          ...session("session-chip"),
          status: "published",
          questions: [],
        });
      }
      if (options?.method === "POST") {
        if (url.endsWith("/sessions")) return json(session("session-chip"));
        if (url.endsWith("/messages/stream"))
          return new Response(
            JSON.stringify({
              type: "done",
              data: {
                ...session("session-chip"),
                intent: "find_room",
                status: "needs_clarification",
                message: "Mức tiền bạn nêu hiểu thế nào cho đúng?",
                clarification: {
                  question: "Mức tiền bạn nêu hiểu thế nào cho đúng?",
                  options: [chip],
                  decided_by: "rules",
                },
                usage: { logical_calls: 0, tokens: null, mode: "openai" },
              },
            }) + "\n",
            {
              status: 200,
              headers: { "Content-Type": "application/x-ndjson" },
            },
          );
      }
      if (url.endsWith("/sessions/session-chip"))
        return json(session("session-chip"));
      return json([]);
    }),
  );
  render(
    <RouterProvider>
      <RenterWorkspace
        api={new Api(null)}
        actor={{ id: "renter", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText("Nhu cầu tìm phòng"),
    "Tìm phòng trọ dưới 4 triệu ở Cầu Giấy",
  );
  await user.click(screen.getByRole("button", { name: /Nhắn cho trợ lý/ }));
  await user.click(await screen.findByRole("button", { name: chip.label }));
  expect(patches).toHaveLength(1);
  // Nút đã bấm không còn; lựa chọn và dòng xác nhận nằm trong khung chat.
  expect(await screen.findByText(`Đã chọn: ${chip.label}`)).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: chip.label })).toBeNull();
  expect(screen.getByText(/Mình đã tìm lại theo lựa chọn này/)).toBeVisible();
});

it("shows the server's follow-up question and its chips when the click cannot search yet", async () => {
  // 18/11: bấm "Ở Hà Nội" khi chưa có mức tiền — máy chủ CHƯA tìm, trả câu hỏi tiếp
  // kèm nút. Giao diện không được báo "đã tìm lại" như trước.
  sessionStorage.clear();
  const cityChip = {
    id: "opt-1",
    label: "Ở Hà Nội (95 căn)",
    patch: { set: { city: "Hà Nội" } },
    action: "patch",
  };
  const budgetChip = {
    id: "opt-0",
    label: "Tổng tháng dưới 4 triệu (10 căn)",
    patch: { set: {} },
    action: "text",
    text: "tổng tháng dưới 4 triệu",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if (options?.method === "PATCH")
        return json({
          ...session("session-next"),
          status: "needs_clarification",
          questions: ["Bạn muốn chi bao nhiêu mỗi tháng?"],
          message: "Bạn muốn chi bao nhiêu mỗi tháng?",
          clarification: {
            question: "Bạn muốn chi bao nhiêu mỗi tháng?",
            options: [budgetChip],
            decided_by: "rules",
          },
        });
      if (options?.method === "POST") {
        if (url.endsWith("/sessions")) return json(session("session-next"));
        if (url.endsWith("/messages/stream"))
          return new Response(
            JSON.stringify({
              type: "done",
              data: {
                ...session("session-next"),
                intent: "find_room",
                status: "needs_clarification",
                message: "Bạn muốn thuê tại thành phố nào?",
                clarification: {
                  question: "Bạn muốn thuê tại thành phố nào?",
                  options: [cityChip],
                  decided_by: "rules",
                },
                usage: { logical_calls: 0, tokens: null, mode: "openai" },
              },
            }) + "\n",
            {
              status: 200,
              headers: { "Content-Type": "application/x-ndjson" },
            },
          );
      }
      if (url.endsWith("/sessions/session-next"))
        return json(session("session-next"));
      return json([]);
    }),
  );
  render(
    <RouterProvider>
      <RenterWorkspace
        api={new Api(null)}
        actor={{ id: "renter", role: "renter" }}
        tab="search"
      />
    </RouterProvider>,
  );
  const user = userEvent.setup();
  await user.type(
    screen.getByLabelText("Nhu cầu tìm phòng"),
    "tìm giúp mình một phòng",
  );
  await user.click(screen.getByRole("button", { name: /Nhắn cho trợ lý/ }));
  await user.click(await screen.findByRole("button", { name: cityChip.label }));
  expect(
    await screen.findByText(`Đã chọn: ${cityChip.label}`),
  ).toBeInTheDocument();
  expect(
    await screen.findByRole("button", { name: budgetChip.label }),
  ).toBeVisible();
  expect(screen.queryByText(/Mình đã tìm lại theo lựa chọn này/)).toBeNull();
});
