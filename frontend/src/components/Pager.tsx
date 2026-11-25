import { useEffect, useState } from "react";

// Thanh phân trang cho bảng/danh sách dài: chọn số dòng mỗi trang (10 hoặc 20),
// nút Trước/Sau và vị trí hiện tại. Dữ liệu vẫn nằm đủ trong trình duyệt; chỉ
// phần hiển thị bị cắt thành từng trang.
export const PAGE_SIZES = [10, 20] as const;

// Cắt một danh sách thành trang. resetKey đổi (từ khóa, bộ lọc…) thì về trang
// đầu; danh sách ngắn đi thì trang hiện tại tự co lại cho khớp.
export function usePager<T>(items: readonly T[], resetKey: unknown = null) {
  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState<number>(PAGE_SIZES[0]);
  useEffect(() => setPage(0), [resetKey]);
  const lastPage = Math.max(0, Math.ceil(items.length / pageSize) - 1);
  const current = Math.min(page, lastPage);
  return {
    items: items.slice(current * pageSize, (current + 1) * pageSize),
    pagerProps: {
      total: items.length,
      page: current,
      pageSize,
      onPage: setPage,
      onPageSize: (size: number) => {
        setPageSize(size);
        setPage(0);
      },
    },
  };
}
export function Pager({
  total,
  page,
  pageSize,
  onPage,
  onPageSize,
  unit = "mục",
}: {
  unit?: string;
  total: number;
  page: number;
  pageSize: number;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
}) {
  if (total <= PAGE_SIZES[0]) return null;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(page, pages - 1);
  const from = total === 0 ? 0 : current * pageSize + 1;
  const to = Math.min(total, (current + 1) * pageSize);
  return (
    <nav className="pager" aria-label="Phân trang">
      <span className="pager-range">
        {from}–{to} / {total} {unit}
      </span>
      <label className="pager-size">
        Số dòng
        <select
          aria-label="Số dòng mỗi trang"
          value={pageSize}
          onChange={(event) => onPageSize(Number(event.target.value))}
        >
          {PAGE_SIZES.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
      </label>
      <div className="pager-nav">
        <button
          type="button"
          className="button small outline"
          disabled={current <= 0}
          onClick={() => onPage(current - 1)}
        >
          Trước
        </button>
        <span className="pager-page">
          Trang {current + 1}/{pages}
        </span>
        <button
          type="button"
          className="button small outline"
          disabled={current >= pages - 1}
          onClick={() => onPage(current + 1)}
        >
          Sau
        </button>
      </div>
    </nav>
  );
}
