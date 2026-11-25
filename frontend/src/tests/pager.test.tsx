import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";
import { Pager, usePager } from "../components/Pager";

const numbers = (count: number) =>
  Array.from({ length: count }, (_, i) => i + 1);

function List({ count, resetKey = "a" }: { count: number; resetKey?: string }) {
  const paged = usePager(numbers(count), resetKey);
  return (
    <>
      <ul>
        {paged.items.map((n) => (
          <li key={n}>mục {n}</li>
        ))}
      </ul>
      <Pager unit="mục" {...paged.pagerProps} />
    </>
  );
}

it("shows one page of 10 and moves between pages", async () => {
  const user = userEvent.setup();
  render(<List count={25} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(10);
  expect(screen.getByText("1–10 / 25 mục")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Trước" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Sau" }));
  expect(screen.getByText("11–20 / 25 mục")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Sau" }));
  expect(screen.getAllByRole("listitem")).toHaveLength(5);
  expect(screen.getByRole("button", { name: "Sau" })).toBeDisabled();
});

it("switches to 20 per page and returns to the first page", async () => {
  const user = userEvent.setup();
  render(<List count={45} />);
  await user.click(screen.getByRole("button", { name: "Sau" }));
  await user.selectOptions(screen.getByLabelText("Số dòng mỗi trang"), "20");
  expect(screen.getAllByRole("listitem")).toHaveLength(20);
  expect(screen.getByText("1–20 / 45 mục")).toBeInTheDocument();
  expect(screen.getByText("Trang 1/3")).toBeInTheDocument();
});

it("hides the pager when everything fits on one page", () => {
  render(<List count={8} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(8);
  expect(screen.queryByRole("navigation", { name: "Phân trang" })).toBeNull();
});

it("goes back to the first page when the reset key changes", async () => {
  const user = userEvent.setup();
  const view = render(<List count={30} resetKey="a" />);
  await user.click(screen.getByRole("button", { name: "Sau" }));
  expect(screen.getByText("11–20 / 30 mục")).toBeInTheDocument();
  view.rerender(<List count={30} resetKey="b" />);
  expect(screen.getByText("1–10 / 30 mục")).toBeInTheDocument();
});
