import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api, ApiError } from "../api";
import { LandlordWorkspace } from "../pages/LandlordWorkspace";
import type { Room, Recommendation } from "../types";
import { deferred, profile, room } from "./fixtures";
const catalog = (revision: number, published = true): Room => ({
  id: "room-1",
  revision,
  title: "Phòng kiểm thử CAS",
  city: "TP.HCM",
  area: "Quận 7",
  published,
  available: true,
  area_m2: 21,
  source: "demo://test",
  synthetic: true,
  amenities: {},
  quote: { rent_vnd: 2500000, deposit_vnd: null, fees: [] },
});
it("does not let a delayed catalog refresh overwrite the revision returned after a CAS mutation", async () => {
  const api = new Api("test");
  const late = deferred<{ rooms: Room[] }>();
  const get = vi
    .spyOn(api, "get")
    .mockResolvedValueOnce({ rooms: [catalog(1)] })
    .mockImplementationOnce(() => late.promise as never)
    .mockResolvedValue({ rooms: [catalog(2, false)] });
  const patch = vi
    .spyOn(api, "patch")
    .mockResolvedValue({ room: catalog(2, false) });
  render(<LandlordWorkspace api={api} tab="catalog" />);
  await screen.findByText("Phòng kiểm thử CAS");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Đọc lại" }));
  await user.click(screen.getByRole("button", { name: "Ẩn tin room-1" }));
  await waitFor(() => expect(get).toHaveBeenCalledTimes(3));
  await screen.findByRole("button", { name: "Duyệt tin room-1" });
  await act(async () => {
    late.resolve({ rooms: [catalog(1)] });
    await late.promise;
  });
  await user.click(screen.getByRole("button", { name: "Duyệt tin room-1" }));
  expect(patch.mock.calls[1][1]).toEqual({
    expected_revision: 2,
    published: true,
  });
}, 20000);
it("reads the catalog again after a stale CAS failure before allowing another mutation", async () => {
  const api = new Api("test");
  vi.spyOn(api, "get")
    .mockResolvedValueOnce({ rooms: [catalog(1)] })
    .mockResolvedValue({ rooms: [catalog(3, false)] });
  const patch = vi
    .spyOn(api, "patch")
    .mockRejectedValueOnce(new ApiError(409, "stale_revision", "Kho đã đổi"))
    .mockResolvedValue({});
  render(<LandlordWorkspace api={api} tab="catalog" />);
  await screen.findByText("Phòng kiểm thử CAS");
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Ẩn tin room-1" }));
  await screen.findByText("Kho đã đổi");
  await user.click(screen.getByRole("button", { name: "Duyệt tin room-1" }));
  expect(patch.mock.calls[1][1]).toEqual({
    expected_revision: 3,
    published: true,
  });
}, 20000);
it("retains the review payload/key after a lost response and only publishes the server decision", async () => {
  const api = new Api("test");
  const draft: Recommendation = {
    run_id: "r1",
    session_id: "s1",
    status: "pending_review",
    profile_version: 1,
    catalog_version: "catalog-1",
    profile,
    items: [room()],
    diagnostics: { rejected: {}, verification: {} },
    decision: null,
  };
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/landlord/recommendations" ? [draft] : (draft as never),
  );
  const post = vi
    .spyOn(api, "post")
    .mockRejectedValueOnce(new ApiError(0, "network_error", "Mất phản hồi"))
    .mockResolvedValueOnce({ ...draft, status: "published" });
  render(<LandlordWorkspace api={api} tab="review" />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /Phiên s1/ }));
  await user.type(
    await screen.findByLabelText("Lý do quyết định"),
    "Đã kiểm tra chi phí và nguồn.",
  );
  await user.click(screen.getByRole("button", { name: "Duyệt 1 phòng" }));
  await screen.findByText("Mất phản hồi");
  expect(screen.queryByText(/Đã công bố đúng/)).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Duyệt 1 phòng" }));
  await screen.findByText(
    "Đã công bố đúng danh sách được duyệt cho người thuê.",
  );
  expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
  expect(post).toHaveBeenCalledTimes(2);
}, 20000);
