import { useCallback, useEffect, useState } from "react";
import { Api } from "../api";
import { ErrorNotice, Icon, money, roomTitle } from "../components/Shared";
import { LoadingState } from "../components/LoadingState";
import { Link } from "../router";
// Trang cá nhân của người thuê: căn đã lưu + căn đã xem (tham chiếu "Tin đã
// lưu / Phòng đã xem"). Căn đã xem do máy chủ ghi khi mở chi tiết tin.
type Card = {
  id: string;
  room_id?: string;
  title: string;
  area: string;
  city: string;
  room_type?: string | null;
  cost?: { monthly_total_vnd: number | null } | null;
};
function PersonalRow({
  item,
  action,
}: {
  item: Card;
  action?: React.ReactNode;
}) {
  const id = item.room_id ?? item.id;
  return (
    <div className="personal-row">
      <div className="personal-row-main">
        <Link to={`/tin/${encodeURIComponent(id)}`} className="personal-title">
          {roomTitle(item.title)}
        </Link>
        <small>
          {item.area} · {item.city}
          {item.cost?.monthly_total_vnd != null &&
            ` · tổng tháng ${money(item.cost.monthly_total_vnd)}`}
        </small>
      </div>
      {action}
    </div>
  );
}
export function SavedPage({ api }: { api: Api }) {
  const [saved, setSaved] = useState<Card[]>([]);
  const [viewed, setViewed] = useState<Card[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [savedItems, viewedItems] = await Promise.all([
        api.get<Card[]>("/rooms/saved"),
        api.get<Card[]>("/rooms/viewed"),
      ]);
      setSaved(savedItems);
      setViewed(viewedItems);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }, [api]);
  useEffect(() => {
    void load();
  }, [load]);
  const unsave = async (roomId: string) => {
    setSaved((items) =>
      items.filter((item) => (item.room_id ?? item.id) !== roomId),
    );
    try {
      await api.delete(`/rooms/${encodeURIComponent(roomId)}/save`);
    } catch (err) {
      setError((err as Error).message);
      void load();
    }
  };
  return (
    <>
      <div className="page-heading">
        <span className="eyebrow">KHÔNG GIAN CỦA BẠN</span>
        <h1>Căn đã lưu &amp; đã xem</h1>
        <p>
          Căn bạn đã lưu để so sánh sau, và căn bạn đã mở chi tiết. Nhu cầu tìm
          nhà nằm ở nút “Nhu cầu của tôi” trên màn trợ lý.
        </p>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {loading ? (
        <section className="panel">
          <LoadingState label="Đang đọc danh sách cá nhân…" />
        </section>
      ) : (
        <>
          <section className="panel">
            <div className="section-heading">
              <h2>
                <Icon name="heart" size={17} /> Đã lưu ({saved.length})
              </h2>
            </div>
            {saved.length === 0 ? (
              <p className="subtle">
                Chưa có căn nào. Bấm “Lưu” trên thẻ phòng trong khung đề xuất để
                giữ lại đây.
              </p>
            ) : (
              <div className="personal-list">
                {saved.map((item) => (
                  <PersonalRow
                    key={item.room_id ?? item.id}
                    item={item}
                    action={
                      <button
                        className="button small outline"
                        onClick={() => void unsave(item.room_id ?? item.id)}
                      >
                        Bỏ lưu
                      </button>
                    }
                  />
                ))}
              </div>
            )}
          </section>
          <section className="panel">
            <div className="section-heading">
              <h2>
                <Icon name="eye" size={17} /> Đã xem ({viewed.length})
              </h2>
            </div>
            {viewed.length === 0 ? (
              <p className="subtle">
                Chưa mở chi tiết căn nào. Lịch sử xem chỉ ghi khi bạn đăng nhập.
              </p>
            ) : (
              <div className="personal-list">
                {viewed.map((item) => (
                  <PersonalRow key={item.room_id ?? item.id} item={item} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </>
  );
}
