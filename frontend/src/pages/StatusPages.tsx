import { Link } from "../router";
import { EmptyState, Icon } from "../components/Shared";
// 404/403 trình bày đúng nguyên nhân (UI_SPEC mục 5): không lộ bản ghi, có
// bước tiếp theo theo quyền hiện có.
export function NotFound() {
  return (
    <main className="status-page">
      <section className="panel">
        <EmptyState
          title="Không tìm thấy trang"
          description="Địa chỉ bạn mở không tồn tại hoặc chưa được triển khai. Các màn trong kế hoạch v1 sẽ được thêm dần theo API tương ứng."
          icon="search"
        />
        <p className="empty-footnote center">
          <Link className="text-button" to="/">
            <Icon name="arrow" size={14} /> Về trang chủ
          </Link>
        </p>
      </section>
    </main>
  );
}
export function Forbidden({
  homePath,
  homeLabel,
}: {
  homePath: string;
  homeLabel: string;
}) {
  return (
    <main className="status-page">
      <section className="panel">
        <EmptyState
          title="Bạn không có quyền truy cập khu vực này"
          description="Mỗi vai trò chỉ thấy cổng làm việc của mình; quyền do máy chủ cấp và kiểm tra lại ở từng tài nguyên, không thể mở rộng từ đường dẫn."
          icon="shield"
        />
        <p className="empty-footnote center">
          <Link className="text-button" to={homePath}>
            <Icon name="arrow" size={14} /> {homeLabel}
          </Link>
        </p>
      </section>
    </main>
  );
}
