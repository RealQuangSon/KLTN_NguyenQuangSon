import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { RoomEditor } from "../components/RoomEditor";
import { CoverPhoto, PhotoGallery } from "../components/PhotoGallery";
import { MaintenancePage } from "../pages/Pms";
import type { Photo, Room } from "../types";
// FE-05: upload ảnh tin (hợp đồng README §7.5), gallery bàn phím, minh họa khi
// không có ảnh, ảnh sự cố tải bằng token. Mock theo mẫu inbox-admin.test.tsx.
const room: Room = {
  id: "room-1",
  revision: 3,
  title: "Studio Q7. Gần lô B",
  city: "TP.HCM",
  area: "Quận 7",
  room_type: "studio",
  bedrooms: null,
  capacity: 2,
  published: false,
  available: null,
  occupancy: "vacant",
  area_m2: 22,
  source: "demo://room",
  synthetic: true,
  amenities: {},
  quote: {
    rent_vnd: 4500000,
    deposit_vnd: null,
    advance_months: 1,
    one_time_vnd: 0,
    fees: [],
  },
  photos: [],
  promotion: null,
};
const png = (name = "anh.png", bytes = 10) =>
  new File([new ArrayBuffer(bytes)], name, { type: "image/png" });
it("uploads with multipart FormData, bearer token and no manual Content-Type", async () => {
  const calls: { url: string; options?: RequestInit }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      calls.push({ url, options });
      return new Response(
        JSON.stringify({
          id: "m1",
          url: "/media/m1",
          content_type: "image/png",
          size_bytes: 1,
          position: 1,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    }),
  );
  const media = await new Api("tok").upload(
    "/landlord/rooms/room-1/media",
    png(),
  );
  // Đúng hợp đồng README §7.5: máy chủ trả đủ id, url, content_type, size_bytes, position.
  expect(media).toEqual({
    id: "m1",
    url: "/media/m1",
    content_type: "image/png",
    size_bytes: 1,
    position: 1,
  });
  const call = calls[0];
  expect(call.url.endsWith("/landlord/rooms/room-1/media")).toBe(true);
  const headers = call.options?.headers as Record<string, string>;
  expect(headers.Authorization).toBe("Bearer tok");
  // Trình duyệt tự đặt Content-Type multipart kèm boundary.
  expect(headers["Content-Type"]).toBeUndefined();
  expect(call.options?.body).toBeInstanceOf(FormData);
  expect((call.options?.body as FormData).get("file")).toBeInstanceOf(File);
});
it("sends picked files to the room media path one by one with progress", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue({
    ...room,
    photos: [],
  } as never);
  const upload = vi.spyOn(api, "upload").mockImplementation(async (path) => {
    expect(path).toBe("/landlord/rooms/room-1/media");
    return { id: `m-${path}-${Math.random()}`, url: "/media/m1" };
  });
  const user = userEvent.setup();
  render(
    <RoomEditor api={api} room={room} onSubmit={vi.fn()} onCancel={vi.fn()} />,
  );
  const input = await screen.findByLabelText(/Chọn ảnh/);
  await user.upload(input, [png("a.png"), png("b.png")]);
  await waitFor(() => expect(upload).toHaveBeenCalledTimes(2));
  expect(
    await screen.findByText(/Đã tải 2 ảnh\. Ảnh đầu tiên là ảnh bìa/),
  ).toBeInTheDocument();
  expect(screen.getAllByAltText(/^Ảnh 1 của Studio Q7/).length).toBeGreaterThan(
    0,
  );
});
it("blocks a 6MB file on the client before any upload call", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue({ ...room, photos: [] } as never);
  const upload = vi.spyOn(api, "upload").mockResolvedValue({
    id: "m1",
    url: "/media/m1",
  });
  const user = userEvent.setup();
  render(
    <RoomEditor api={api} room={room} onSubmit={vi.fn()} onCancel={vi.fn()} />,
  );
  await user.upload(
    await screen.findByLabelText(/Chọn ảnh/),
    png("big.png", 6 * 1024 * 1024),
  );
  expect(
    await screen.findByText(/Đã bỏ qua 1 tệp: chỉ nhận JPEG\/PNG\/WebP ≤ 5 MB/),
  ).toBeInTheDocument();
  expect(upload).not.toHaveBeenCalled();
});
it("shows the media editor only for a saved listing (with id)", () => {
  const api = new Api("t");
  render(
    <RoomEditor api={api} room={null} onSubmit={vi.fn()} onCancel={vi.fn()} />,
  );
  expect(screen.queryByLabelText(/Chọn ảnh/)).toBeNull();
  expect(screen.queryByText("Ưu đãi")).toBeNull();
});
it("deletes a photo and reorders via PATCH media/order", async () => {
  const api = new Api("t");
  const photos: Photo[] = [
    { id: "m1", url: "/media/m1" },
    { id: "m2", url: "/media/m2" },
  ];
  vi.spyOn(api, "get").mockResolvedValue({ ...room, photos } as never);
  const del = vi.spyOn(api, "delete").mockResolvedValue(null as never);
  const patch = vi
    .spyOn(api, "patch")
    .mockResolvedValue([photos[1], photos[0]] as never);
  const user = userEvent.setup();
  render(
    <RoomEditor api={api} room={room} onSubmit={vi.fn()} onCancel={vi.fn()} />,
  );
  await user.click(
    await screen.findByRole("button", { name: "Đưa ảnh 1 xuống" }),
  );
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith("/landlord/rooms/room-1/media/order", {
      media_ids: ["m2", "m1"],
    }),
  );
  await user.click(screen.getByRole("button", { name: "Xóa ảnh 1" }));
  await waitFor(() =>
    expect(del).toHaveBeenCalledWith("/landlord/rooms/room-1/media/m2"),
  );
});
it("renders the gallery, navigates with the right arrow key and shows the illustration without photos", async () => {
  const photos: Photo[] = [
    { id: "m1", url: "/media/m1" },
    { id: "m2", url: "/media/m2" },
  ];
  const { rerender } = render(
    <PhotoGallery photos={photos} title="Studio Q7" />,
  );
  expect(screen.getByAltText("Ảnh 1/2 — Studio Q7")).toHaveAttribute(
    "src",
    "/api/media/m1",
  );
  const user = userEvent.setup();
  const gallery = screen.getByRole("figure", { name: "Ảnh của Studio Q7" });
  await user.type(gallery, "{ArrowRight}");
  expect(screen.getByAltText("Ảnh 2/2 — Studio Q7")).toBeInTheDocument();
  // Không có ảnh: giữ hình minh họa thay vì ô trống.
  rerender(<PhotoGallery photos={[]} title="Studio Q7" />);
  expect(
    document.querySelector(".photo-gallery.empty .room-illustration"),
  ).toBeTruthy();
  // Ảnh bìa thẻ phòng: ảnh đầu hoặc minh họa.
  const { container } = render(
    <CoverPhoto photos={undefined} title="Studio Q7" />,
  );
  expect(
    container.querySelector(".card-photo .room-illustration"),
  ).toBeTruthy();
});
const lease = {
  id: "l1",
  landlord_id: "owner-a",
  renter_id: "renter-a",
  room_id: "demo-01",
  start_date: "2026-10-01",
  end_date: "2027-04-01",
  rent_vnd: 2500000,
  deposit_vnd: 2500000,
  payment_day: 5,
  occupants: 1,
  vehicles: 1,
  status: "active",
  version: 1,
  renter_accepted_version: 1,
  renewal_of: null,
  settlement_note: null,
};
it("uploads maintenance photos only after the ticket has been created", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/leases" ? [lease] : ([] as never),
  );
  const post = vi
    .spyOn(api, "post")
    .mockResolvedValue({ id: "tk1", room_id: "demo-01" } as never);
  const upload = vi.spyOn(api, "upload").mockResolvedValue({
    id: "m1",
    url: "/media/m1",
  });
  const user = userEvent.setup();
  render(<MaintenancePage api={api} side="renter" />);
  await user.selectOptions(await screen.findByLabelText("Phòng"), "demo-01");
  await user.type(screen.getByLabelText("Vấn đề"), "Máy nước nóng hỏng");
  await user.type(
    screen.getByLabelText("Mô tả"),
    "Không có nước nóng ba ngày nay",
  );
  await user.upload(screen.getByLabelText(/Ảnh đính kèm/), png("su-co.png"));
  expect(post).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Gửi yêu cầu" }));
  await waitFor(() =>
    expect(post).toHaveBeenCalledWith("/maintenance", {
      room_id: "demo-01",
      title: "Máy nước nóng hỏng",
      description: "Không có nước nóng ba ngày nay",
      priority: "normal",
    }),
  );
  await waitFor(() =>
    expect(upload).toHaveBeenCalledWith(
      "/maintenance/tk1/media",
      expect.any(File),
    ),
  );
});
it("loads ticket photos with the token as object URLs and revokes them on unmount", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockResolvedValue([
    {
      id: "tk1",
      room_id: "demo-01",
      renter_id: "renter-a",
      title: "Vỡ kính cửa sổ",
      description: "Kính vỡ nguy hiểm",
      priority: "urgent",
      status: "submitted",
      assignee: null,
      cost_vnd: null,
      timeline: [],
      photos: [{ id: "m9", url: "/media/m9" }],
    },
  ] as never);
  // jsdom không cung cấp URL.revokeObjectURL: gắn hàm rỗng trước khi spy để
  // kiểm đúng hợp đồng "hủy object URL khi unmount".
  URL.revokeObjectURL = URL.revokeObjectURL ?? (() => {});
  const revoke = vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  const blobUrl = vi
    .spyOn(api, "blobUrl")
    .mockResolvedValue("blob:token-protected");
  const view = render(<MaintenancePage api={api} side="landlord" />);
  expect(
    await screen.findByAltText("Ảnh sự cố Vỡ kính cửa sổ"),
  ).toHaveAttribute("src", "blob:token-protected");
  expect(blobUrl).toHaveBeenCalledWith("/media/m9");
  view.unmount();
  expect(revoke).toHaveBeenCalledWith("blob:token-protected");
});
