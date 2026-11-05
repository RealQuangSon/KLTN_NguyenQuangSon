import { useEffect, useState } from "react";
import type { Photo } from "../types";
import { mediaSrc } from "../api";
import { RoomIllustration } from "./RoomIllustration";
// FE-05: gallery ảnh thật của tin (README §7.5). Ảnh tin là công khai nên
// <img> trỏ thẳng /api/media/{id}; không có ảnh thì giữ hình minh họa như cũ.
const alt = (title: string, index: number, total: number) =>
  `Ảnh ${index + 1}/${total} — ${title}`;
export function CoverPhoto({
  photos,
  title,
  className = "",
}: {
  photos: Photo[] | undefined;
  title: string;
  className?: string;
}) {
  const first = photos?.[0];
  return first ? (
    <img
      className={`card-photo ${className}`}
      src={mediaSrc(first.url)}
      alt={alt(title, 0, photos?.length ?? 1)}
      loading="lazy"
    />
  ) : (
    <div className={`card-photo empty ${className}`} aria-hidden="true">
      <RoomIllustration />
    </div>
  );
}
export function PhotoGallery({
  photos,
  title,
}: {
  photos: Photo[] | undefined;
  title: string;
}) {
  const items = photos ?? [];
  const [index, setIndex] = useState(0);
  // Danh sách ảnh co lại sau khi xóa: giữ chỉ số trong phạm vi.
  useEffect(() => {
    setIndex((current) => (current < items.length ? current : 0));
    // items được coi là bất biến theo từng lần tải chi tiết.
  }, [items.length]);
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
          src={mediaSrc(items[safe].url)}
          alt={alt(title, safe, items.length)}
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
              key={photo.id}
              className={`photo-thumb ${i === safe ? "active" : ""}`}
              aria-label={`Xem ảnh ${i + 1}`}
              aria-current={i === safe}
              onClick={() => setIndex(i)}
            >
              <img src={mediaSrc(photo.url)} alt="" loading="lazy" />
            </button>
          ))}
        </div>
      )}
      <figcaption className="visually-hidden">
        Dùng phím mũi tên trái/phải để đổi ảnh.
      </figcaption>
    </figure>
  );
}
