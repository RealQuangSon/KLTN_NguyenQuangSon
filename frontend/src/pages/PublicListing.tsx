import { useEffect, useState } from "react";
import { Api } from "../api";
import type { Cost, Room } from "../types";
import { addressLine, postedAgoLabel, roomTypeLabels } from "../types";
import { goongApiKey } from "../map";
import { Brand } from "../components/Brand";
import {
  AmenityChips,
  ContactInfo,
  CostBreakdown,
  DescriptionText,
  EmptyState,
  PosterBadge,
  PromotionBadge,
  TermsBlock,
  roomTitle,
} from "../components/Shared";
import { MapView } from "../components/MapView";
import { PhotoGallery } from "../components/PhotoGallery";
// Trang tin công khai (đích của link chia sẻ đa kênh). Không cần đăng nhập để
// xem; đặt lịch và chat với chủ nhà cần đăng nhập.
export function PublicListing({ roomId }: { roomId: string }) {
  const [room, setRoom] = useState<
    (Room & { cost: Cost; house_rules?: string | null }) | null
  >(null);
  const [error, setError] = useState<string | null>(null);
  // Bản đồ nạp muộn (lazy): mỗi lần mount là 1 map load của Goong — chỉ nạp
  // khi người dùng bấm xem, đỡ đốt quota 1.000 map loads/tháng.
  const [mapOpen, setMapOpen] = useState(false);
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
            <h1>
              {roomTitle(room.title)}{" "}
              <PosterBadge posterKind={room.poster_kind} />
            </h1>
            {/* LF-05: địa chỉ chi tiết và ngày đăng; thiếu phần nào bỏ phần đó. */}
            {addressLine(room) && <p>{addressLine(room)}</p>}
            {postedAgoLabel(room.posted_at) && (
              <small>{postedAgoLabel(room.posted_at)}</small>
            )}
            {room.promotion && (
              <PromotionBadge promotion={room.promotion} withText />
            )}
            <PhotoGallery photos={room.photos} title={roomTitle(room.title)} />
            {room.features_text && <p>{room.features_text}</p>}
            <DescriptionText description={room.description} />
            <p>{room.area_m2} m²</p>
            <AmenityChips amenities={room.amenities} />
            <TermsBlock room={room} />
            <CostBreakdown cost={room.cost} />
            {/* Bản đồ theo kiểu workspace tham chiếu: bản đồ nhúng kèm liên hệ
                đi đường; tin chỉ biết tới khu vực không đặt marker. */}
            <h2>Vị trí trên bản đồ</h2>
            {mapOpen ? (
              <>
                <MapView
                  pins={[
                    {
                      ...room,
                      monthly: room.cost.monthly_total_vnd,
                    },
                  ]}
                />
                {room.latitude != null &&
                  room.longitude != null &&
                  room.location_accuracy !== "area_only" && (
                    <p className="listing-map-links">
                      <a
                        href={`https://map.goong.io/?lat=${room.latitude}&lng=${room.longitude}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Mở trong Goong Maps ↗
                      </a>
                      {/* Xem đường đi bằng deep-link: không gọi Directions API,
                          không tốn quota. Google Maps có URL chuẩn và app di động. */}
                      <a
                        href={`https://www.google.com/maps/dir/?api=1&destination=${room.latitude},${room.longitude}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Xem đường đi ↗
                      </a>
                      {!goongApiKey() && (
                        <small>
                          Chưa cấu hình key Goong — bản đồ dùng tile dự phòng.
                        </small>
                      )}
                    </p>
                  )}
              </>
            ) : (
              <button
                type="button"
                className="button outline small"
                onClick={() => setMapOpen(true)}
              >
                Xem bản đồ gần đúng
              </button>
            )}
            <ContactInfo contact={room.contact} />
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
