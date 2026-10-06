import { useEffect, useState } from "react";
import { Api } from "../api";
import type { Cost, Room } from "../types";
import { amenities, roomTypeLabels } from "../types";
import { Brand } from "../components/Brand";
import { CostBreakdown, EmptyState, roomTitle } from "../components/Shared";
// Trang tin công khai (đích của link chia sẻ đa kênh). Không cần đăng nhập để
// xem; đặt lịch và chat với chủ nhà cần đăng nhập.
export function PublicListing({ roomId }: { roomId: string }) {
  const [room, setRoom] = useState<
    (Room & { cost: Cost; house_rules?: string | null }) | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    new Api(null, () => {})
      .get<Room & { cost: Cost }>(`/listings/${encodeURIComponent(roomId)}`)
      .then(setRoom)
      .catch((err) => setError((err as Error).message));
  }, [roomId]);
  return (
    <main className="public-listing">
      <header className="topbar">
        <Brand />
        <a className="button small" href="/dang-nhap">
          Đăng nhập để đặt lịch xem
        </a>
      </header>
      <section className="panel">
        {error ? (
          <EmptyState
            title="Không tìm thấy tin"
            description="Tin có thể đã ẩn hoặc không còn cho thuê."
            icon="home"
          />
        ) : !room ? (
          <p>Đang tải tin…</p>
        ) : (
          <>
            <span className="eyebrow">
              {room.area} · {room.city} ·{" "}
              {roomTypeLabels[room.room_type ?? "room"]}
              {room.bedrooms ? ` ${room.bedrooms}PN` : ""}
            </span>
            <h1>{roomTitle(room.title)}</h1>
            {room.features_text && <p>{room.features_text}</p>}
            <p>
              {room.area_m2} m² ·{" "}
              {Object.entries(room.amenities)
                .filter(([, value]) => value === true)
                .map(([key]) => amenities[key] || key)
                .join(", ")}
            </p>
            <CostBreakdown cost={room.cost} />
            {room.house_rules && (
              <>
                <h2>Nội quy</h2>
                <p>{room.house_rules}</p>
              </>
            )}
            <p className="input-hint">
              Vị trí công khai là gần đúng. Chi phí là ước tính cho 1 người, 1
              xe.
              {room.synthetic ? " Dữ liệu giả lập phục vụ nghiên cứu." : ""}
            </p>
          </>
        )}
      </section>
    </main>
  );
}
