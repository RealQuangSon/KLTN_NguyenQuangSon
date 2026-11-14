import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RenterWorkspace } from "../pages/RenterWorkspace";
import { session } from "./fixtures";
// Kịch bản kho rỗng kiểu workspace tham chiếu: máy chủ trả no_match kèm
// diagnostics_summary (số tin bị loại theo tiêu chí) + steps pipeline thật;
// khung chat phải nói lại nhu cầu, nêu tiêu chí loại và đề nghị nới MỘT tiêu
// chí — không tự nới, không bịa căn.
const emptyResult = {
  session_id: "session-1",
  run_id: "run-empty",
  status: "no_match",
  profile_version: 1,
  results: [],
  suggestions: [
    "Mở rộng khu vực: bỏ giới hạn quận hoặc xem quận lân cận trong cùng thành phố.",
  ],
  diagnostics_summary: {
    scanned: 13,
    kept: 0,
    rejected: { monthly_budget: 7, area: 5 },
    verification: { location: 1 },
  },
  steps: [
    "Quét 13 tin đã công bố trong kho",
    "Lọc điều kiện cứng — loại 12 tin; giữ 1 tin chờ xác minh số liệu",
    "Xếp hạng theo phương pháp baseline của engine deterministic",
    "Không còn căn nào khớp — bạn có thể nới một tiêu chí để tìm lại",
  ],
};
const current = session("session-1");
const apiWithEmpty = () => {
  const api = new Api("t");
  sessionStorage.setItem("homematch.session.renter-a", "session-1");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path.endsWith("/results") ? (emptyResult as never) : (current as never),
  );
  return api;
};
it("announces the empty-kho playbook in chat with per-criterion counts", async () => {
  render(
    <RenterWorkspace
      api={apiWithEmpty()}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  // Nói lại nhu cầu đã nắm từ hồ sơ đã xác nhận.
  expect(
    await screen.findByText(/Nhu cầu mình đã nắm: khu Quận 7, TP\.HCM/),
  ).toBeInTheDocument();
  // Số liệu tổng hợp thật của máy chủ, không bịa.
  expect(screen.getByText(/quét 13 tin trong kho/)).toBeInTheDocument();
  expect(screen.getByText(/trần tổng tháng \(7 tin\)/)).toBeInTheDocument();
  // Đề nghị nới đúng một tiêu chí, cam kết không tự nới.
  expect(screen.getByText(/nới MỘT tiêu chí nào trước/)).toBeInTheDocument();
  expect(
    screen.getByText(/chỉ nới đúng tiêu chí bạn chọn/),
  ).toBeInTheDocument();
  // D-12: không còn khái niệm tin bị giữ chờ xác minh trong thông báo.
  expect(screen.queryByText(/bị giữ/)).toBeNull();
});
it("discloses the real pipeline steps on request", async () => {
  render(
    <RenterWorkspace
      api={apiWithEmpty()}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  const toggle = await screen.findByRole("button", {
    name: /Đã xử lý qua 4 bước/,
  });
  // Thu gọn mặc định: nội dung bước chưa hiện.
  expect(
    screen.queryByText(
      "Lọc điều kiện cứng — loại 12 tin; giữ 1 tin chờ xác minh số liệu",
    ),
  ).not.toBeInTheDocument();
  const user = userEvent.setup();
  await user.click(toggle);
  expect(
    screen.getByText("Quét 13 tin đã công bố trong kho"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      "Xếp hạng theo phương pháp baseline của engine deterministic",
    ),
  ).toBeInTheDocument();
});
it("voice input states the truth on unsupported browsers instead of pretending", async () => {
  render(
    <RenterWorkspace
      api={apiWithEmpty()}
      actor={{ id: "renter-a", role: "renter" }}
      tab="search"
    />,
  );
  const mic = await screen.findAllByRole("button", {
    name: "Nhập bằng giọng nói",
  });
  expect(mic.length).toBeGreaterThanOrEqual(1);
  const user = userEvent.setup();
  await user.click(mic[0]);
  // jsdom không có Web Speech API: phải nói thẳng, không giả trạng thái đang nghe.
  expect(
    await screen.findByText(/chưa hỗ trợ nhập giọng nói/),
  ).toBeInTheDocument();
});
