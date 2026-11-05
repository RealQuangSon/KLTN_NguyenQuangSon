import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { profileUpdateFromChat } from "../profile";
import type { Draft, Profile } from "../types";
import { profile, room, session } from "./fixtures";
// Kho Chợ Tốt hầu như không ghi sức chứa: run đầu chỉ ra needs_verification
// rỗng. Người thuê nhắn "chấp nhận dữ liệu ước tính" thì phải có vòng tìm mới,
// nếu không trợ lý hứa "kết quả sẽ tự hiện" mà khung phải và bản đồ vẫn trống.
const base = session().draft;
const withChat = (
  patch: Partial<Draft>,
  evidence: Record<string, string>,
): Draft => ({
  ...base,
  ...patch,
  evidence_ref: { ...base.evidence_ref, ...evidence },
});
it("applies only the fields the chat turn changed onto the confirmed profile", () => {
  const next = profileUpdateFromChat(
    profile,
    base,
    withChat(
      { accept_estimated_data: true },
      { accept_estimated_data: "chat:r4" },
    ),
  );
  expect(next).toEqual({ ...profile, accept_estimated_data: true });
  // Giá trị chỉ nhập ở form được giữ nguyên.
  expect(next?.max_initial_cash_vnd).toBe(6500000);
});
it("never re-confirms a chat budget, form edits or values the chat merely repeated", () => {
  expect(
    profileUpdateFromChat(
      profile,
      base,
      withChat({ budget_hint_vnd: 1000000 }, { budget_hint: "chat:r4" }),
    ),
  ).toBeNull();
  expect(
    profileUpdateFromChat(
      profile,
      base,
      withChat({ area: "Quận 1" }, { area: "form:r4" }),
    ),
  ).toBeNull();
  expect(
    profileUpdateFromChat(
      profile,
      base,
      withChat({}, { city: "chat:r4", area: "chat:r4" }),
    ),
  ).toBeNull();
});
it("re-runs the search after a chat turn accepts estimated data on a confirmed session", async () => {
  const confirmed: Profile = { ...profile, accept_estimated_data: false };
  const restored = {
    ...session(),
    draft_revision: 3,
    confirmed_profile: confirmed,
  };
  const held = {
    session_id: "session-1",
    run_id: "run-1",
    status: "needs_verification",
    profile_version: 1,
    results: [],
    diagnostics_summary: {
      scanned: 5,
      kept: 0,
      rejected: {},
      verification: { availability_or_capacity: 5 },
    },
  };
  const published = {
    ...held,
    run_id: "run-2",
    status: "published",
    profile_version: 2,
    results: [room()],
  };
  let state = restored;
  let latest: unknown = held;
  const api = new Api("t");
  sessionStorage.setItem("homematch.session.renter-a", "session-1");
  vi.spyOn(api, "get").mockImplementation(
    async (path) => (path.endsWith("/results") ? latest : state) as never,
  );
  const post = vi.spyOn(api, "post").mockImplementation(async (path, body) => {
    if (path.endsWith("/messages")) {
      state = {
        ...restored,
        draft_revision: 4,
        draft: withChat(
          { accept_estimated_data: true },
          { accept_estimated_data: "chat:r4" },
        ),
      };
      return state as never;
    }
    if (path.endsWith("/confirm")) {
      const sent = (body as { profile: Profile }).profile;
      state = {
        ...state,
        draft_revision: 5,
        profile_version: 2,
        confirmed_profile: sent,
        active_run_id: "run-2",
      };
      latest = published;
      return published as never;
    }
    return {} as never;
  });
  render(
    <RenterWorkspace
      api={api}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  const composer = await screen.findByPlaceholderText(
    "Nhắn cho HomeMatch Agent…",
  );
  // Khôi phục phiên đã xác nhận: không tự chạy lại vòng tìm.
  expect(post).not.toHaveBeenCalled();
  const user = userEvent.setup();
  await user.type(composer, "Chấp nhận dữ liệu ước tính{Enter}");
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith("/sessions/session-1/confirm", {
      expected_draft_revision: 4,
      profile: { ...confirmed, accept_estimated_data: true },
    }),
  );
  expect(await screen.findByText("Phòng riêng room-1")).toBeInTheDocument();
});

it("AG-02: chỉ áp budget_hint vào trần khi máy chủ trả budget_explicit", () => {
  const withBudget = (evidence: string): Draft => ({
    ...base,
    budget_hint_vnd: 4500000,
    evidence_ref: { ...base.evidence_ref, budget_hint: evidence },
  });
  // Có cờ + evidence chat + mức đổi → áp vào trần tổng tháng.
  expect(
    profileUpdateFromChat(profile, base, withBudget("chat:r4"), true),
  ).toEqual({ ...profile, max_monthly_cost_vnd: 4500000 });
  // Không có cờ (bug cũ "nới thêm 1 triệu") → không đổi gì.
  expect(
    profileUpdateFromChat(profile, base, withBudget("chat:r4"), false),
  ).toBeNull();
  // Mức tiền nhập form (evidence form:) không bao giờ tự áp qua chat.
  expect(
    profileUpdateFromChat(profile, base, withBudget("form:r4"), true),
  ).toBeNull();
});
