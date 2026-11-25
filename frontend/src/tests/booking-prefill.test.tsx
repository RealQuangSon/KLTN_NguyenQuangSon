import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Api } from "../api";
import { ViewingForm } from "../components/ViewingPanel";

const room = {
  room_id: "demo-01",
  title: "Phòng giả lập 01",
  area: "Quận 7",
};

// B5 (15/11): form đặt lịch điền sẵn họ tên và SĐT từ tài khoản khi có dữ liệu;
// người dùng vẫn sửa được và vẫn phải tự tích ô đồng ý.
it("điền sẵn họ tên và SĐT từ /me/profile khi tài khoản có dữ liệu", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/me/profile"
      ? ({ display_name: "Trần Thị B", contact_phone: "0912345678" } as never)
      : ({} as never),
  );
  render(
    <ViewingForm
      room={room}
      sessionId={null}
      api={api}
      onDone={() => {}}
      onCancel={() => {}}
    />,
  );
  await waitFor(() => {
    expect(screen.getByLabelText("Họ tên")).toHaveValue("Trần Thị B");
  });
  await waitFor(() => {
    expect(screen.getByLabelText("Số điện thoại")).toHaveValue("0912345678");
  });
  // Ô đồng ý KHÔNG được tích sẵn.
  expect(screen.getByRole("checkbox")).not.toBeChecked();
  // Người dùng vẫn sửa được.
  const user = userEvent.setup();
  await user.clear(screen.getByLabelText("Họ tên"));
  await user.type(screen.getByLabelText("Họ tên"), "Trần Thị C");
  expect(screen.getByLabelText("Họ tên")).toHaveValue("Trần Thị C");
});

it("tài khoản không có dữ liệu thì giữ trống để người dùng tự điền", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/me/profile"
      ? ({ display_name: null, contact_phone: null } as never)
      : ({} as never),
  );
  render(
    <ViewingForm
      room={room}
      sessionId={null}
      api={api}
      onDone={() => {}}
      onCancel={() => {}}
    />,
  );
  await waitFor(() => expect(api.get).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText("Họ tên")).toHaveValue("");
  expect(screen.getByLabelText("Số điện thoại")).toHaveValue("");
});

// B5: tài khoản seed chưa có hồ sơ → điền từ lần đặt lịch gần nhất của chính
// người thuê (GET /viewings chỉ trả liên hệ của chính họ).
it("không có hồ sơ tài khoản thì điền từ lịch xem gần nhất của người thuê", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/me/profile"
      ? ({ display_name: null, contact_phone: null } as never)
      : path === "/viewings"
        ? ([
            { id: "v1", contact_name: "Lê Thị D", contact_phone: "0987654321" },
            {
              id: "v2",
              contact_name: "Trần Văn E",
              contact_phone: "0901112222",
            },
          ] as never)
        : ({} as never),
  );
  render(
    <ViewingForm
      room={room}
      sessionId={null}
      api={api}
      onDone={() => {}}
      onCancel={() => {}}
    />,
  );
  await waitFor(() => {
    expect(screen.getByLabelText("Họ tên")).toHaveValue("Trần Văn E");
  });
  await waitFor(() => {
    expect(screen.getByLabelText("Số điện thoại")).toHaveValue("0901112222");
  });
  // Vẫn phải tự tích ô đồng ý.
  expect(screen.getByRole("checkbox")).not.toBeChecked();
});

// Hồ sơ tài khoản có dữ liệu thì ưu tiên hồ sơ, không đè bằng lịch cũ.
it("có hồ sơ tài khoản thì ưu tiên hồ sơ thay vì lịch cũ", async () => {
  const api = new Api("t");
  vi.spyOn(api, "get").mockImplementation(async (path) =>
    path === "/me/profile"
      ? ({ display_name: "Trần Thị B", contact_phone: "0912345678" } as never)
      : path === "/viewings"
        ? ([
            { id: "v1", contact_name: "Lê Thị D", contact_phone: "0987654321" },
          ] as never)
        : ({} as never),
  );
  render(
    <ViewingForm
      room={room}
      sessionId={null}
      api={api}
      onDone={() => {}}
      onCancel={() => {}}
    />,
  );
  await waitFor(() => {
    expect(screen.getByLabelText("Họ tên")).toHaveValue("Trần Thị B");
  });
  expect(screen.getByLabelText("Số điện thoại")).toHaveValue("0912345678");
});
