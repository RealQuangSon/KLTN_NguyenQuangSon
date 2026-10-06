import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { InboxPage, OPEN_CONVERSATION_KEY } from "../pages/Inbox";
import { AdminWorkspace } from "../pages/AdminWorkspace";
const conversation = {
  id: "c1",
  renter_id: "renter-a",
  landlord_id: "owner-a",
  room_id: "r1",
  last_message_at: "2026-10-05T10:00:00Z",
  unread: 1,
  context: {
    room: {
      id: "r1",
      title: "Studio Q7",
      area: "Quận 7",
      city: "TP.HCM",
      rent_vnd: 5000000,
    },
    needs: {
      area: "Quận 7",
      people: 2,
      max_monthly_cost_vnd: 7000000,
      preferences: ["window"],
    },
    affordability_band: "can_nhac",
    recent_ai_chat: [{ speaker: "user", text: "gọi [SĐT đã che]" }],
  },
};
it("shows the landlord the handover context (band only) and sends a reply", async () => {
  sessionStorage.setItem(OPEN_CONVERSATION_KEY, "c1");
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/conversations"
      ? ([conversation] as never)
      : ({
          messages: [
            {
              id: "m1",
              sender_id: "system",
              sender_role: "system",
              body: "Khách chuyển từ trợ lý AI",
              created_at: "2026-10-05T10:00:00Z",
            },
            {
              id: "m2",
              sender_id: "renter-a",
              sender_role: "renter",
              body: "Còn phòng không?",
              created_at: "2026-10-05T10:01:00Z",
            },
          ],
        } as never),
  );
  const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
  const user = userEvent.setup();
  render(<InboxPage api={api} role="owner" />);
  expect(await screen.findByText("Còn phòng không?")).toBeInTheDocument();
  expect(screen.getByText(/trần tổng tháng 7\.000\.000/)).toBeInTheDocument();
  expect(screen.getByText(/Cần cân nhắc/)).toBeInTheDocument();
  expect(screen.queryByText(/thu nhập 2/)).toBeNull();
  expect(screen.getByText("1 mới")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Tin nhắn"), "Còn bạn nhé");
  await user.click(screen.getByRole("button", { name: "Gửi" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith("/conversations/c1/messages", {
      body: "Còn bạn nhé",
    }),
  );
  expect(sessionStorage.getItem(OPEN_CONVERSATION_KEY)).toBeNull();
});
it("lets the admin open a masked transcript and see landlord response rates", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path === "/admin/transcripts")
      return [
        {
          session_id: "s1",
          user_id: "renter-a",
          turns: 2,
          started_at: "2026-10-05T10:00:00Z",
          last_at: "2026-10-05T10:00:00Z",
          flagged: 0,
        },
      ] as never;
    if (path === "/admin/transcripts/s1")
      return {
        session_id: "s1",
        turns: [
          {
            speaker: "user",
            text: "gọi [SĐT đã che]",
            intent: "find_room",
            agent: "needs",
            created_at: "2026-10-05T10:00:00Z",
          },
        ],
      } as never;
    return {
      landlords: [
        {
          landlord_id: "owner-a",
          conversations: 2,
          answered: 1,
          response_rate: 0.5,
          median_response_minutes: 12,
        },
      ],
    } as never;
  });
  const user = userEvent.setup();
  const { unmount } = render(<AdminWorkspace api={api} section="hoi-thoai" />);
  await user.click(await screen.findByRole("button", { name: /renter-a/ }));
  expect(await screen.findByText("gọi [SĐT đã che]")).toBeInTheDocument();
  unmount();
  render(<AdminWorkspace api={api} section="chuyen-giao" />);
  expect(await screen.findByText("50%")).toBeInTheDocument();
  expect(screen.getByText("12 phút")).toBeInTheDocument();
});
