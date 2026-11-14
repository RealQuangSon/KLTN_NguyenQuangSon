import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import {
  RoomCard,
  assumptionText,
  evidenceText,
  reasonChips,
} from "../components/Shared";
import { room } from "./fixtures";

// UX-08: lý do/đánh đổi tới người thuê là tiếng Việt, không khóa tiếng Anh.
const BANNED =
  /deposit|first_rent|one_time|electricity|air_conditioning|structured_baseline|kịch bản đã xác nhận|giả định chuẩn/;

it("humanizes backend reason and tradeoff strings", () => {
  const lines = [
    "Tổng tháng 2,220,000 VND trong kịch bản đã xác nhận.",
    "Đáp ứng sở thích air_conditioning theo nguồn tin.",
    "Sở thích kitchen: thiếu bằng chứng hoặc không có.",
    "Tiền ban đầu chưa đầy đủ: deposit, first_rent, one_time",
    "Phí electricity, water, internet, service đang theo giả định chuẩn vì tin không ghi — cần xác minh lại khi xem.",
  ].map(evidenceText);
  for (const line of lines) expect(line).not.toMatch(BANNED);
  expect(lines[0]).toContain("2.220.000 ₫");
  expect(lines[1]).toContain("Máy lạnh");
});

it("formats the cost assumptions as a sentence", () => {
  expect(
    assumptionText({
      people: 2,
      vehicles: 1,
      electricity_kwh: 140,
      water_m3: 3,
      moving_vnd: 300000,
    }),
  ).toBe(
    "2 người, 1 xe, 140 kWh điện, 3 m³ nước mỗi tháng; một lần: chuyển nhà 300.000 ₫",
  );
});

it("limits chips to 2 reasons and 1 caution, and folds unknown amenities", () => {
  const base = room("r1");
  const item = {
    ...base,
    reasons: [
      "Tổng tháng 2,220,000 VND trong kịch bản đã xác nhận.",
      "Có air_conditioning theo nguồn tin.",
      "Có wifi theo nguồn tin.",
      "Có kitchen theo nguồn tin.",
    ],
    tradeoffs: ["Sở thích loft: thiếu bằng chứng hoặc không có."],
    verification: ["amenity_unknown:loft", "amenity_unknown:camera"],
  };
  const chips = reasonChips(item);
  expect(chips.reasons).toHaveLength(2);
  expect(chips.reasons[0]).toBe("Có Máy lạnh theo nguồn tin");
  expect(chips.caution).toBe("Tin chưa ghi Gác lửng");
  render(<RoomCard item={item} />);
  expect(screen.getByText(/Tin chưa ghi 2 tiện ích/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(
    /structured_baseline|Phiên bản/,
  );
});
