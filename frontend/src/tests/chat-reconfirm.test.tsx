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
// UX-02: ca "chat đổi nhu cầu → chạy lại vòng tìm" nay do BACKEND làm trong cùng lượt
// (backend/tests/test_ux_batch1.py::test_chat_turn_confirms_and_ranks_in_the_same_turn).
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
