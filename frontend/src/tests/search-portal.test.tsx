import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { SearchPage } from "../pages/SearchPage";
import { HandbookPage } from "../pages/Handbook";
import { cost } from "./fixtures";
const listing = (id: string, monthly: number) => ({
  id,
  revision: 1,
  title: `Căn ${id}. mô tả`,
  city: "Hà Nội",
  area: "Quận Cầu Giấy",
  room_type: "apartment",
  bedrooms: 1,
  published: true,
  available: true,
  occupancy: "vacant",
  area_m2: 45,
  source: "synthetic://x",
  synthetic: true,
  amenities: { window: true },
  quote: { rent_vnd: monthly - 500000, deposit_vnd: 1, fees: [] },
  latitude: 21.03,
  longitude: 105.79,
  uncertainty_m: 100,
  location_accuracy: "approximate",
  cost: { ...cost, monthly_total_vnd: monthly, initial_total_vnd: monthly * 2 },
});
it("searches with filters, previews a listing, compares with advice and books from the listing", async () => {
  const api = new Api("t");
  const get = vi.spyOn(api, "get").mockImplementation(async (path) => {
    if (path.startsWith("/listings?"))
      return {
        total: 2,
        items: [listing("a", 9000000), listing("b", 11000000)],
      } as never;
    return {
      ...listing("a", 9000000),
      house_rules: "Cổng đóng 23:00. Gửi xe máy miễn phí.",
    } as never;
  });
  const post = vi.spyOn(api, "post").mockImplementation(async (path) => {
    if (path === "/listings/compare")
      return {
        items: [listing("a", 9000000), listing("b", 11000000)],
        advice: {
          recommended_room_id: "a",
          summary: "Đề xuất Căn a: tổng tháng thấp nhất.",
          rooms: [
            {
              room_id: "a",
              title: "Căn a",
              pros: ["Tổng tháng thấp nhất"],
              cons: [],
            },
            {
              room_id: "b",
              title: "Căn b",
              pros: [],
              cons: ["Tổng tháng cao nhất"],
            },
          ],
        },
      } as never;
    if (path === "/handbook/ask")
      return {
        answers: [],
        house_rules: ["Gửi xe máy miễn phí."],
        disclaimer: "Tham khảo",
        found: true,
      } as never;
    return { id: "v1" } as never;
  });
  const user = userEvent.setup();
  render(<SearchPage api={api} />);
  await screen.findByText("Căn a");
  await user.selectOptions(screen.getByLabelText("Thành phố"), "Hà Nội");
  await user.click(screen.getByRole("button", { name: "Máy giặt" }));
  await user.click(screen.getByRole("button", { name: /^Tìm$/ }));
  await waitFor(() =>
    expect(
      get.mock.calls.some(
        ([path]) =>
          path.includes("city=H%C3%A0+N%E1%BB%99i") &&
          path.includes("amenities=washing_machine"),
      ),
    ).toBe(true),
  );
  await user.click(screen.getAllByRole("button", { name: "Xem nhanh" })[0]);
  expect(await screen.findByText(/Cổng đóng 23:00/)).toBeInTheDocument();
  await user.type(
    screen.getByLabelText("Hỏi cẩm nang về phòng này"),
    "gửi xe?",
  );
  await user.click(screen.getByRole("button", { name: "Hỏi" }));
  expect(await screen.findByText(/Theo nội quy chủ nhà/)).toBeInTheDocument();
  const compareButtons = screen.getAllByRole("button", { name: "So sánh" });
  await user.click(compareButtons[0]);
  await user.click(screen.getAllByRole("button", { name: "So sánh" })[0]);
  await user.click(screen.getByRole("button", { name: /So sánh & tư vấn/ }));
  expect(await screen.findByText(/Đề xuất Căn a/)).toBeInTheDocument();
  expect(screen.getByText("Đề xuất")).toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Đặt lịch xem" })[0]);
  expect(screen.getByText(/Xem trực tuyến/)).toBeInTheDocument();
}, 20000);
it("lists handbook entries and answers a question by retrieval", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue([
    { id: "deposit", title: "Tiền cọc và hoàn cọc", answer: "Tiền cọc là..." },
  ] as never);
  vi.spyOn(api, "post").mockResolvedValue({
    answers: [
      {
        id: "deposit",
        title: "Tiền cọc và hoàn cọc",
        answer: "Hoàn sau bàn giao.",
      },
    ],
    disclaimer: "Thông tin tham khảo chung",
    found: true,
  } as never);
  const user = userEvent.setup();
  render(<HandbookPage api={api} />);
  expect(await screen.findByText("Tiền cọc và hoàn cọc")).toBeInTheDocument();
  await user.type(screen.getByLabelText("Câu hỏi của bạn"), "hoàn cọc?");
  await user.click(screen.getByRole("button", { name: /Hỏi/ }));
  expect(await screen.findByText("Hoàn sau bàn giao.")).toBeInTheDocument();
  expect(screen.getByText("Thông tin tham khảo chung")).toBeInTheDocument();
});
