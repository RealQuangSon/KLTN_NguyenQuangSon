import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { CostBreakdown, PublishedResults } from "../components/Shared";
import { cost, room } from "./fixtures";
describe("Public recommendation projection", () => {
  it.each(["pending_review", "reviewed", "invalidated", "generation_failed"])(
    "never renders room data for %s even if a malformed DTO contains items",
    (status) => {
      render(
        <PublishedResults
          result={{ session_id: "s", run_id: "r", status, results: [room()] }}
          selected={[]}
          onSelect={vi.fn()}
          onViewing={vi.fn()}
        />,
      );
      expect(screen.queryByText("Phòng riêng room-1")).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "So sánh" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: "Yêu cầu xem" }),
      ).not.toBeInTheDocument();
    },
  );
  it("shows approved rooms and marks synthetic source", () => {
    render(
      <PublishedResults
        result={{
          session_id: "s",
          run_id: "r",
          status: "published",
          results: [room()],
        }}
        selected={[]}
        onSelect={vi.fn()}
        onViewing={vi.fn()}
      />,
    );
    expect(screen.getByText("Phòng riêng room-1")).toBeVisible();
    expect(screen.getByText("Dữ liệu giả lập")).toBeVisible();
  });
  it("distinguishes included zero from unknown fees and incomplete totals", () => {
    render(<CostBreakdown cost={cost} />);
    expect(screen.getByText("0 ₫")).toBeVisible();
    expect(screen.getAllByText("Chưa xác định").length).toBeGreaterThanOrEqual(
      3,
    );
    expect(screen.getByText(/Đã biết 2.500.000 ₫/)).toBeVisible();
    expect(
      screen.getByText(/Phần đã biết chưa phải tổng đầy đủ/),
    ).toBeVisible();
    expect(screen.getByText("Đã gồm trong tiền thuê")).toBeVisible();
  });
});
