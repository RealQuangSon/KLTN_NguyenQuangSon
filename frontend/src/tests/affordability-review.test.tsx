import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { RoomCard } from "../components/Shared";
import type { Candidate } from "../types";
import { cost, room } from "./fixtures";
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
