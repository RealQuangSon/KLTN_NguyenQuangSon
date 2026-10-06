import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { Comparison } from "../components/Shared";
import { SimulationPanel } from "../components/Simulation";
import { AccountPage } from "../pages/Account";
import type { Candidate } from "../types";
import { cost, profile, room } from "./fixtures";
const priced = (id: string, monthly: number, area: number): Candidate => ({
  ...room(id),
  area_m2: area,
  cost: { ...cost, monthly_total_vnd: monthly, initial_total_vnd: monthly * 2 },
});
it("marks best values in words, never for unknown totals, and draws cost bars", () => {
  render(
    <Comparison
      items={[priced("a", 3000000, 20), priced("b", 4000000, 30)]}
      onClose={() => {}}
    />,
  );
  expect(screen.getAllByText("Tốt nhất")).toHaveLength(3);
  expect(screen.getByLabelText("Biểu đồ chi phí")).toBeInTheDocument();
  render(
    <Comparison
      items={[{ ...room("c"), cost }, priced("d", 3500000, 20)]}
      onClose={() => {}}
    />,
  );
  // One monthly total is unknown: no "best" is claimed for that row.
  expect(screen.getAllByText("Tốt nhất")).toHaveLength(3);
});
it("sends read-only what-if scenarios with explicit no-loan and custom loan", async () => {
  const api = new Api("test");
  const post = vi.spyOn(api, "post").mockResolvedValue({
    items: [
      { label: "Hồ sơ hiện tại", cost },
      { label: "Vay 12 tháng", cost },
      { label: "Không vay", cost },
    ],
  });
  render(
    <SimulationPanel
      room={room("r1")}
      sessionId="s1"
      profile={{ ...profile, loan: { annual_rate: "0.1", term_months: 6 } }}
      api={api}
      onClose={() => {}}
    />,
  );
  await userEvent.click(
    screen.getByRole("button", { name: /Tính các kịch bản/ }),
  );
  expect(post).toHaveBeenCalledWith("/sessions/s1/simulate", {
    room_id: "r1",
    scenarios: [
      { label: "Hồ sơ hiện tại", cost_split: "none" },
      {
        label: "Vay 12 tháng",
        cost_split: "none",
        loan: { annual_rate: "0.1", term_months: 12, max_principal_vnd: null },
      },
      { label: "Không vay", cost_split: "none", loan: null },
    ],
  });
  expect(
    await screen.findByRole("columnheader", { name: "Vay 12 tháng" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/không thay đổi hồ sơ|không phải báo giá/i),
  ).toBeInTheDocument();
});
it("shows remembered preferences without money and lets the renter delete them", async () => {
  const api = new Api("test");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/me/profile"
      ? ({
          id: "renter-a",
          display_name: null,
          email: null,
          consents: { remember_sessions: true, save_history: false },
        } as never)
      : ({
          consented: true,
          memory: {
            fields: {
              city: "Hà Nội",
              area: "Quận Cầu Giấy",
              preferences: ["window"],
            },
            source_session: "s0",
            updated_at: "2026-10-05T00:00:00Z",
          },
        } as never),
  );
  const del = vi.spyOn(api, "delete").mockResolvedValue({});
  render(
    <AccountPage
      actor={{ id: "renter-a", role: "renter" }}
      section="ho-so"
      api={api}
    />,
  );
  const item = (await screen.findByText(/Quận Cầu Giấy/)).closest("li")!;
  expect(screen.getByText(/Cửa sổ, thoáng sáng/)).toBeInTheDocument();
  expect(screen.queryByText(/₫/)).toBeNull();
  await userEvent.click(within(item).getByRole("button", { name: "Xóa" }));
  expect(del).toHaveBeenCalledWith("/me/memory/area");
});
