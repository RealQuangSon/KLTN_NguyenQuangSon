import { useEffect, useState } from "react";
import type { Photo } from "../types";
import { mediaSrc } from "../api";
import { RoomIllustration } from "./RoomIllustration";
// FE-05: gallery ảnh thật của tin (README §7.5). Ảnh tin là công khai nên
// <img> trỏ thẳng /api/media/{id}; không có ảnh thì giữ hình minh họa như cũ.
// CA-06: tin cào Chợ Tốt thêm ảnh ngoài (source_images) — ảnh chủ nhà đứng
// trước, ảnh ngoài giữ URL nguyên bản (không qua mediaSrc), không tải file.
export type DisplayPhoto = { url: string; external: boolean };
export type PhotoItem = {
  photos?: Photo[] | null;
  source_images?: string[] | null;
  source_videos?: { url: string; thumbnail: string | null }[] | null;
  source?: string | null;
};
const alt = (title: string, index: number, total: number) =>
  `Ảnh ${index + 1}/${total} — ${title}`;
export function displayPhotos(
  item: PhotoItem | undefined | null,
): DisplayPhoto[] {
  const own = (item?.photos ?? []).map((photo) => ({
    url: photo.url,
    external: false,
  }));
  const crawled = (item?.source_images ?? [])
    .filter(
      (url) =>
        typeof url === "string" && url.startsWith("https://cdn.chotot.com/"),
    )
    .map((url) => ({ url, external: true }));
  return [...own, ...crawled];
}
const imageSrc = (photo: DisplayPhoto) =>
  photo.external ? photo.url : mediaSrc(photo.url);
export function CoverPhoto({
  item,
  title,
  className = "",
}: {
  item: PhotoItem | undefined | null;
  title: string;
  className?: string;
}) {
  const photos = displayPhotos(item);
  const first = photos[0];
  // Ảnh lỗi (link chết khi tin hết hạn) → về hình minh họa, không hiện ảnh hỏng.
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [first?.url]);
  if (first && !broken)
    return (
      <img
        className={`card-photo ${className}`}
        src={imageSrc(first)}
        alt={alt(title, 0, photos.length)}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
      />
    );
  return (
    <div className={`card-photo empty ${className}`} aria-hidden="true">
      <RoomIllustration />
    </div>
  );
}
export function PhotoGallery({
  item,
  title,
  source,
}: {
  item: PhotoItem | undefined | null;
  title: string;
  // Link tin gốc Chợ Tốt cho chú thích ảnh ngoài (CA-06).
  source?: string | null;
}) {
  const photos = displayPhotos(item);
  const [index, setIndex] = useState(0);
  // Ảnh lỗi bị bỏ khỏi danh sách: giữ mốc "đã bỏ" theo URL, reset khi ảnh đổi.
  const [removed, setRemoved] = useState<string[]>([]);
  useEffect(() => {
    setIndex((current) => (current < photos.length ? current : 0));
    setRemoved([]);
    // item được coi là bất biến theo từng lần tải chi tiết.
  }, [item]);
  const items = photos.filter((photo) => !removed.includes(photo.url));
  if (!items.length)
    return (
      <figure className="photo-gallery empty" aria-hidden="true">
        <RoomIllustration />
        <figcaption>Hình minh họa — tin chưa có ảnh thật</figcaption>
      </figure>
    );
  const safe = Math.min(index, items.length - 1);
  const move = (step: -1 | 1) =>
    setIndex((current) => {
      const base = Math.min(current, items.length - 1);
      return (base + step + items.length) % items.length;
    });
  const drop = (url: string) => setRemoved((current) => [...current, url]);
  return (
    <figure
      className="photo-gallery"
      aria-label={`Ảnh của ${title}`}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          move(-1);
        }
        if (event.key === "ArrowRight") {
          event.preventDefault();
          move(1);
        }
      }}
    >
      <div className="photo-gallery-main">
        <img
          src={imageSrc(items[safe])}
          alt={alt(title, safe, items.length)}
          referrerPolicy="no-referrer"
          onError={() => drop(items[safe].url)}
        />
        {items.length > 1 && (
          <>
            <button
              type="button"
              className="photo-nav"
              aria-label="Ảnh trước"
              onClick={() => move(-1)}
            >
              ‹
            </button>
            <button
              type="button"
              className="photo-nav"
              aria-label="Ảnh sau"
              onClick={() => move(1)}
            >
              ›
            </button>
            <span className="photo-count">
              {safe + 1}/{items.length}
            </span>
          </>
        )}
      </div>
      {items.length > 1 && (
        <div className="photo-thumbs" role="group" aria-label="Chọn ảnh">
          {items.map((photo, i) => (
            <button
              type="button"
              key={photo.url}
              className={`photo-thumb ${i === safe ? "active" : ""}`}
              aria-label={`Xem ảnh ${i + 1}`}
              aria-current={i === safe}
              onClick={() => setIndex(i)}
            >
              <img
                src={imageSrc(photo)}
                alt=""
                loading="lazy"
                referrerPolicy="no-referrer"
                onError={() => drop(photo.url)}
              />
            </button>
          ))}
        </div>
      )}
      {items.some((photo) => photo.external) && (
        <figcaption className="photo-source-caption">
          Ảnh từ tin gốc Chợ Tốt
          {source?.startsWith("https://") && (
            <>
              {" · "}
              <a href={source} target="_blank" rel="noopener noreferrer">
                Xem tin gốc
              </a>
            </>
          )}
        </figcaption>
      )}
      <figcaption className="visually-hidden">
        Dùng phím mũi tên trái/phải để đổi ảnh.
      </figcaption>
    </figure>
  );
}
// crawl.md B-3: video Cloudflare Stream của tin gốc, URL .m3u8 không phát
// trực tiếp được trên đa số trình duyệt. ĐÃ THỬ nhúng iframe Cloudflare Stream
// (UID từ URL thật) trên trình duyệt 07/11/2026: player trả "This video has
// not been configured to be allowed on this domain" — Chợ Tốt không cho phép
// nhúng domain khác. Theo đúng plan, hiển thị ảnh thumbnail kèm link
// "Xem video trên tin gốc"; không dùng thư viện ngoài.
export function VideoEmbed({
  video,
  source,
}: {
  video: { url: string; thumbnail: string | null };
  source?: string | null;
}) {
  const origin = source?.startsWith("https://") ? source : null;
  if (!video.thumbnail) return null;
  return (
    <figure className="video-embed fallback">
      <img
        src={video.thumbnail}
        alt="Video của phòng (từ tin gốc Chợ Tốt)"
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={(event) => {
          event.currentTarget.closest("figure")?.remove();
        }}
      />
      <figcaption>
        {origin ? (
          <a href={origin} target="_blank" rel="noopener noreferrer">
            Xem video trên tin gốc
          </a>
        ) : (
          "Video từ tin gốc Chợ Tốt"
        )}
      </figcaption>
    </figure>
  );
}
// Cột media của trang chi tiết: gallery ảnh (ảnh chủ nhà trước, ảnh tin gốc
// Chợ Tốt sau) rồi các video của tin.
export function ListingMedia({
  item,
  title,
}: {
  item: PhotoItem;
  title: string;
}) {
  return (
    <div className="listing-media">
      <PhotoGallery item={item} title={title} source={item.source} />
      {(item.source_videos ?? []).map((video) => (
        <VideoEmbed key={video.url} video={video} source={item.source} />
      ))}
    </div>
  );
}
