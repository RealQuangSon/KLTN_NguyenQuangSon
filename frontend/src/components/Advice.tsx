import { Icon } from "./Shared";
// Ưu/nhược điểm và đề xuất do máy chủ tính từ dữ liệu chi phí và tin đăng;
// giao diện chỉ hiển thị, không tự xếp hạng.
export interface Advice {
  recommended_room_id: string | null;
  summary: string;
  rooms: { room_id: string; title: string; pros: string[]; cons: string[] }[];
}
export function AdviceBox({ advice }: { advice: Advice }) {
  return (
    <div className="advice" aria-label="Tư vấn so sánh">
      <p className="notice info">
        <Icon name="shield" size={16} /> {advice.summary}
      </p>
      <div className="advice-grid">
        {advice.rooms.map((room) => (
          <article
            key={room.room_id}
            className={
              room.room_id === advice.recommended_room_id
                ? "advice-card recommended"
                : "advice-card"
            }
          >
            <h3>
              {room.title}
              {room.room_id === advice.recommended_room_id && (
                <span className="badge success">Đề xuất</span>
              )}
            </h3>
            <strong>Ưu điểm</strong>
            <ul>
              {room.pros.length ? (
                room.pros.map((text) => <li key={text}>{text}</li>)
              ) : (
                <li>Không có điểm nổi bật so với các phòng còn lại</li>
              )}
            </ul>
            <strong>Nhược điểm</strong>
            <ul>
              {room.cons.length ? (
                room.cons.map((text) => <li key={text}>{text}</li>)
              ) : (
                <li>Không có nhược điểm rõ ràng</li>
              )}
            </ul>
          </article>
        ))}
      </div>
    </div>
  );
}
