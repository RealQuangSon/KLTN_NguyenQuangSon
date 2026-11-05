import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api, ApiError } from "../api";
import { LandlordWorkspace } from "../pages/LandlordWorkspace";
import type { Room } from "../types";
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
