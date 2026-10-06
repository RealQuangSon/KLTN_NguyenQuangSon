import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RoomCard } from "../components/Shared";
import { LandlordWorkspace } from "../pages/LandlordWorkspace";
import type { Candidate, Recommendation } from "../types";
import { cost, profile, room } from "./fixtures";
const withAffordability = (
  id: string,
  ratio: string | null,
  band: "phu_hop" | "can_nhac" | "vuot" | "chua_ro",
): Candidate => ({
  ...room(id),
  room_type: "apartment",
  bedrooms: 2,
  cost: {
    ...cost,
    affordability: {
      shortfall_vnd: 5500000,
      loan: {
        principal_vnd: 5500000,
        installment_vnd: 949016,
        total_interest_vnd: 194096,
        term_months: 6,
        annual_rate: "0.12",
        exceeds_max_principal: false,
      },
      burden_vnd: 8019016,
      renter_burden_vnd: 8019016,
      housing_ratio: ratio,
      band,
      thresholds: { phu_hop: "0.30", can_nhac: "0.40" },
    },
  },
});
it("shows the renter their band, ratio and loan estimate on a room card", () => {
  render(<RoomCard item={withAffordability("a", "0.3208", "can_nhac")} />);
  expect(screen.getByText(/Cần cân nhắc · 32,1% thu nhập/)).toBeInTheDocument();
  expect(screen.getByText(/trả góp 949\.016 ₫/)).toBeInTheDocument();
  expect(screen.getByText(/Căn hộ 2PN/)).toBeInTheDocument();
});
it("requires an override reason when the sale drops or reorders the agent ranking and never shows income", async () => {
  const api = new Api("test");
  const draft: Recommendation = {
    run_id: "r1",
    session_id: "s1",
    status: "pending_review",
    profile_version: 1,
    catalog_version: "catalog-1",
    // The server strips income from the sale DTO; the UI must not need it.
    profile: { ...profile, loan: { annual_rate: "0.12", term_months: 6 } },
    items: [
      withAffordability("first", null, "can_nhac"),
      withAffordability("second", null, "phu_hop"),
    ],
    diagnostics: { rejected: {}, verification: {} },
    decision: null,
  };
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/landlord/recommendations" ? [draft] : (draft as never),
  );
  const post = vi
    .spyOn(api, "post")
    .mockResolvedValue({ ...draft, status: "published" });
  render(<LandlordWorkspace api={api} tab="review" />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /Phiên s1/ }));
  expect(screen.queryByText(/thu nhập/i, { selector: ".badge" })).toBeNull();
  expect(
    screen.getByText(/Thu nhập của khách không hiển thị/),
  ).toBeInTheDocument();
  await user.type(screen.getByLabelText("Lý do quyết định"), "Đã kiểm tra.");
  await user.click(
    screen.getByRole("button", { name: "Đưa Phòng riêng second lên" }),
  );
  const overrideBox = screen.getByLabelText(/Lý do khác đề xuất của trợ lý/);
  await user.click(screen.getByRole("button", { name: "Duyệt 2 phòng" }));
  expect(post).not.toHaveBeenCalled();
  // The browser blocks submit on the required field; the server rejects it too (422).
  expect(overrideBox).toBeRequired();
  await user.type(overrideBox, "Khách ưu tiên gần trường.");
  await user.click(screen.getByRole("button", { name: "Duyệt 2 phòng" }));
  expect(post).toHaveBeenCalledTimes(1);
  expect(post.mock.calls[0][1]).toMatchObject({
    keep_room_ids: ["second", "first"],
    override_reason: "Khách ưu tiên gần trường.",
  });
}, 20000);
