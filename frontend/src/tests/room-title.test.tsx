import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { AdminWorkspace } from "../pages/AdminWorkspace";
import { ViewingList } from "../components/ViewingPanel";
import type { Viewing } from "../types";

const base: Viewing = {
  id: "v1",
  session_id: null,
  run_id: null,
  room_id: "synthetic-room-083",
  requested_at: "2026-11-15T01:00:00Z",
  status: "requested",
  mode: "offline",
};

// B1 (15/11): danh sách lịch hiện tên phòng; chỉ dùng mã khi không có tên.
it("hiện tên phòng trong danh sách lịch thay vì mã phòng", () => {
  render(
    <ViewingList
      items={[{ ...base, room_title: "Phòng giả lập 083. Phòng yên tĩnh" }]}
    />,
  );
  expect(screen.getByText("Phòng giả lập 083")).toBeInTheDocument();
  expect(screen.queryByText("Phòng synthetic-room-083")).toBeNull();
});

it("không có tên phòng thì dùng mã như cũ", () => {
  render(<ViewingList items={[{ ...base, room_title: null }]} />);
  expect(screen.getByText("Phòng synthetic-room-083")).toBeInTheDocument();
});

it("hàng đợi điều phối của admin hiện tên phòng", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/admin/viewings"
      ? ([
          {
            ...base,
            handler: "concierge",
            room_title:
              "Studio 2 Ban Công Full Nội Thất 40m2 Trần Xuân Soạn Q7",
            source_url: null,
          },
        ] as never)
      : ({} as never),
  );
  render(<AdminWorkspace api={api} section="dieu-phoi" />);
  expect(
    await screen.findByText(
      "Studio 2 Ban Công Full Nội Thất 40m2 Trần Xuân Soạn Q7",
    ),
  ).toBeInTheDocument();
  expect(screen.queryByText("Phòng synthetic-room-083")).toBeNull();
  expect(await screen.findByText("Không có link tin gốc")).toBeInTheDocument();
});
