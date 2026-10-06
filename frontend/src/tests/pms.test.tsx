import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import {
  BillingPage,
  LandlordDashboard,
  LeadsPage,
  LeasesPage,
} from "../pages/Pms";
const lease = (status: string) => ({
  id: "l1",
  landlord_id: "owner-a",
  renter_id: "renter-a",
  room_id: "demo-01",
  start_date: "2026-10-01",
  end_date: "2027-04-01",
  rent_vnd: 2500000,
  deposit_vnd: 2500000,
  payment_day: 5,
  occupants: 2,
  vehicles: 1,
  status,
  version: 2,
  renter_accepted_version: null,
  renewal_of: null,
  settlement_note: null,
});
it("lets the renter accept exactly the version the landlord sent", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue([lease("sent")] as never);
  const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
  render(<LeasesPage api={api} side="renter" />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Chấp thuận phiên bản 2" }),
  );
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith("/leases/l1/accept", {
      expected_version: 2,
    }),
  );
  expect(screen.getByText(/không thay thế chữ ký số/)).toBeInTheDocument();
});
it("shows the landlord unpaid invoices and confirms a renter's transfer claim", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path === "/invoices")
      return [
        {
          id: "i1",
          lease_id: "l1",
          period: "2026-10",
          total_vnd: 3360000,
          paid_vnd: 0,
          balance_vnd: 3360000,
          payment_status: "unpaid",
          overdue: true,
          due_date: "2026-10-05",
          room_id: "demo-01",
          renter_id: "renter-a",
          lines: [],
        },
      ] as never;
    if (path === "/payment-claims")
      return [
        {
          id: "c1",
          invoice_id: "i1",
          amount_vnd: 3360000,
          reference: "CK",
          status: "pending",
          period: "2026-10",
          room_id: "demo-01",
        },
      ] as never;
    if (path === "/leases") return [lease("active")] as never;
    return {
      periods: [
        {
          period: "2026-10",
          billed_vnd: 3360000,
          collected_vnd: 0,
          outstanding_vnd: 3360000,
          overdue_invoices: 1,
        },
      ],
    } as never;
  });
  const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
  render(<BillingPage api={api} side="landlord" />);
  expect((await screen.findAllByText(/Quá hạn/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText("3.360.000 ₫").length).toBeGreaterThan(0);
  await userEvent.click(screen.getByRole("button", { name: "Đã nhận" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith(
      "/landlord/payment-claims/c1/confirm",
      {},
    ),
  );
});
it("lets the renter report a transfer instead of marking the invoice paid", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/invoices"
      ? ([
          {
            id: "i1",
            lease_id: "l1",
            period: "2026-10",
            total_vnd: 1000000,
            paid_vnd: 0,
            balance_vnd: 1000000,
            payment_status: "unpaid",
            overdue: false,
            due_date: "2026-10-05",
            room_id: "demo-01",
            renter_id: "renter-a",
            lines: [],
          },
        ] as never)
      : ([] as never),
  );
  const post = vi.spyOn(api, "post").mockResolvedValue({} as never);
  render(<BillingPage api={api} side="renter" />);
  await userEvent.click(
    await screen.findByRole("button", { name: /Báo đã chuyển/ }),
  );
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith("/invoices/i1/claims", {
      amount_vnd: 1000000,
      reference: "Chuyển khoản kỳ 2026-10",
    }),
  );
  expect(screen.getByText("Chưa thanh toán")).toBeInTheDocument();
});
it("renders the dashboard and the lead pipeline by stage and interest", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path === "/landlord/dashboard")
      return {
        occupancy_rate: 0.5,
        vacant: 1,
        deposited: 0,
        rented: 1,
        month: "2026-10",
        revenue_month_vnd: 3360000,
        outstanding_vnd: 0,
        overdue_invoices: 0,
        upcoming_viewings: 2,
        open_tickets: 1,
        leases_ending_30d: 0,
      } as never;
    if (path === "/landlord/analytics")
      return {
        rooms: [
          {
            room_id: "demo-01",
            title: "Phòng 01",
            views: 10,
            viewings_requested: 2,
            leases_won: 1,
            revenue_vnd: 3360000,
            view_to_viewing: 0.2,
            viewing_to_lease: 0.5,
          },
        ],
      } as never;
    return [
      {
        id: "lead1",
        renter_id: "renter-a",
        room_id: "demo-01",
        stage: "contacted",
        score: 4,
        interest: "warm",
        sources: ["view", "chat"],
        notes: null,
      },
    ] as never;
  });
  const patch = vi.spyOn(api, "patch").mockResolvedValue({} as never);
  const { unmount } = render(<LandlordDashboard api={api} />);
  expect((await screen.findAllByText("50%")).length).toBe(2); // occupancy + viewing→lease
  expect(screen.getByText("20%")).toBeInTheDocument();
  unmount();
  render(<LeadsPage api={api} />);
  expect(await screen.findByText(/Quan tâm · 4 điểm/)).toBeInTheDocument();
  await userEvent.selectOptions(
    screen.getByLabelText("Giai đoạn renter-a"),
    "viewing",
  );
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith("/landlord/leads/lead1", {
      stage: "viewing",
    }),
  );
});
