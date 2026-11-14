import { useEffect, useState } from "react";
import { Api, mediaSrc } from "../api";
import type { Fee, Photo, Promotion, Room, RoomType } from "../types";
import {
  amenities,
  landlordPendingNote,
  occupancyLabels,
  roomTypeLabels,
} from "../types";
import { cityAreas } from "../locations";
import { ErrorNotice, Icon, roomTitle } from "./Shared";
// Form tạo/sửa tin của chủ nhà. Máy chủ gán id, revision, chủ sở hữu và nguồn;
// sửa tin dùng expected_revision để không ghi đè thay đổi của phiên khác.
const FEE_NAMES = [
  "electricity",
  "water",
  "internet",
  "parking",
  "service",
] as const;
// FE-05: kiểm ở client chỉ để báo sớm; máy chủ vẫn quyết định khi tải lên.
const MEDIA_TYPES = ["image/jpeg", "image/png", "image/webp"];
const MEDIA_MAX_BYTES = 5 * 1024 * 1024;
// FE-06: ưu đãi 1–200 ký tự, hạn từ hôm nay tới hôm nay + 90 ngày.
const PROMO_MAX_CHARS = 200;
const PROMO_MAX_DAYS = 90;
const FEE_LABELS: Record<string, string> = {
  electricity: "Điện (đ/kWh)",
  water: "Nước",
  internet: "Internet (đ/tháng)",
  parking: "Gửi xe (đ/xe)",
  service: "Dịch vụ (đ/tháng)",
};
const DEFAULT_MODES: Record<string, Fee["mode"]> = {
  electricity: "kwh",
  water: "person",
  internet: "fixed",
  parking: "vehicle",
  service: "fixed",
};
type Values = {
  title: string;
  city: string;
  area: string;
  room_type: RoomType;
  bedrooms: string;
  capacity: string;
  area_m2: string;
  rent: string;
  deposit: string;
  advance: string;
  published: boolean;
  occupancy: string;
  fees: Record<string, { amount: string; mode: string; included: boolean }>;
  amenities: Record<string, boolean | null>;
  features: string;
  rules: string;
};
const fromRoom = (room: Room | null): Values => ({
  title: room?.title ?? "",
  city: room?.city ?? "TP.HCM",
  area: room?.area ?? "",
  room_type: room?.room_type ?? "room",
  bedrooms: String(room?.bedrooms ?? ""),
  capacity: String(room?.capacity ?? 2),
  // Tin cào thiếu diện tích thì bỏ trống, không điền sẵn số giả.
  area_m2: String(room?.area_m2 ?? ""),
  rent: String(room?.quote.rent_vnd ?? ""),
  deposit: String(room?.quote.deposit_vnd ?? ""),
  advance: String(room?.quote.advance_months ?? 1),
  published: room?.published ?? false,
  occupancy: room?.occupancy ?? "vacant",
  fees: Object.fromEntries(
    FEE_NAMES.map((name) => {
      const fee = room?.quote.fees.find((item) => item.name === name);
      return [
        name,
        {
          amount: fee?.amount_vnd == null ? "" : String(fee.amount_vnd),
          mode: fee?.mode ?? DEFAULT_MODES[name],
          included: fee?.included_in_rent ?? false,
        },
      ];
    }),
  ),
  amenities: Object.fromEntries(
    Object.keys(amenities).map((key) => [key, room?.amenities[key] ?? null]),
  ),
  features: room?.features_text ?? "",
  rules: room?.house_rules ?? "",
});
// Ngày cục bộ dạng YYYY-MM-DD cho input date (tránh lệch múi giờ của toISOString).
const isoDay = (offset: number) => {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
};
export function RoomEditor({
  api,
  room,
  onSubmit,
  onCancel,
  publishLocked = false,
}: {
  api: Api;
  room: Room | null;
  onSubmit: (body: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
  // FE-02: chủ nhà đang chờ duyệt không được bật công khai; máy chủ vẫn là nơi
  // chặn cuối (403 landlord_not_approved) nếu request vẫn lọt qua.
  publishLocked?: boolean;
}) {
  const [values, setValues] = useState<Values>(() => fromRoom(room));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  // FE-05: ảnh chỉ thao tác được khi tin đã tồn tại (có id).
  const [media, setMedia] = useState<Photo[]>(room?.photos ?? []);
  const [uploading, setUploading] = useState<{
    done: number;
    total: number;
  } | null>(null);
  // FE-06: ưu đãi hiện tại của tin (chỉ khi còn hạn, do máy chủ quyết định).
  const [promotion, setPromotion] = useState<Promotion | null>(
    room?.promotion ?? null,
  );
  const [promoText, setPromoText] = useState(promotion?.text ?? "");
  const [promoUntil, setPromoUntil] = useState(promotion?.valid_until ?? "");
  const [promoBusy, setPromoBusy] = useState(false);
  // Chi tiết tin (photos + promotion) nằm ở /landlord/rooms/{id}; nạp im lặng,
  // lỗi để máy chủ báo lại ở từng thao tác cụ thể.
  useEffect(() => {
    if (!room) return;
    let active = true;
    api
      .get<Room>(`/landlord/rooms/${room.id}`)
      .then((detail) => {
        if (!active) return;
        setMedia(detail.photos ?? []);
        setPromotion(detail.promotion ?? null);
        setPromoText(detail.promotion?.text ?? "");
        setPromoUntil(detail.promotion?.valid_until ?? "");
      })
      .catch(() => {});
    return () => {
      active = false;
    };
    // Chỉ nạp lại khi đổi tin; đối tượng room có thể được tạo lại với cùng id.
  }, [api, room?.id]);
  const set = <K extends keyof Values>(key: K, value: Values[K]) =>
    setValues((v) => ({ ...v, [key]: value }));
  // FE-05: tải lần lượt từng file để thấy tiến độ và giữ thứ tự đã chọn.
  const uploadPhotos = async (files: FileList | null) => {
    if (!room || !files?.length) return;
    const chosen = Array.from(files);
    const rejected = chosen.filter(
      (file) => file.size > MEDIA_MAX_BYTES || !MEDIA_TYPES.includes(file.type),
    );
    const acceptable = chosen.filter((file) => !rejected.includes(file));
    setError(null);
    setNotice(
      rejected.length
        ? `Đã bỏ qua ${rejected.length} tệp: chỉ nhận JPEG/PNG/WebP ≤ 5 MB (máy chủ vẫn kiểm tra lại).`
        : null,
    );
    if (!acceptable.length) return;
    setUploading({ done: 0, total: acceptable.length });
    try {
      const uploaded: Photo[] = [];
      for (const [index, file] of acceptable.entries()) {
        uploaded.push(
          await api.upload<Photo>(`/landlord/rooms/${room.id}/media`, file),
        );
        setUploading({ done: index + 1, total: acceptable.length });
      }
      setMedia((current) => [...current, ...uploaded]);
      setNotice(
        `Đã tải ${uploaded.length} ảnh. Ảnh đầu tiên là ảnh bìa của tin.`,
      );
    } catch (err) {
      // invalid_media / media_too_large / media_limit: hiện đúng message máy chủ.
      setError((err as Error).message);
    } finally {
      setUploading(null);
    }
  };
  const deletePhoto = async (photo: Photo) => {
    if (!room) return;
    setError(null);
    try {
      await api.delete(`/landlord/rooms/${room.id}/media/${photo.id}`);
      setMedia((current) => current.filter((item) => item.id !== photo.id));
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const movePhoto = async (index: number, step: -1 | 1) => {
    if (!room) return;
    const target = index + step;
    if (target < 0 || target >= media.length) return;
    const next = [...media];
    [next[index], next[target]] = [next[target], next[index]];
    setMedia(next);
    try {
      const saved = await api.patch<Photo[]>(
        `/landlord/rooms/${room.id}/media/order`,
        { media_ids: next.map((item) => item.id) },
      );
      setMedia(saved);
    } catch (err) {
      setMedia(media);
      setError((err as Error).message);
    }
  };
  // FE-06: lưu ưu đãi; giá hiển thị và thứ tự gợi ý không bị UI thay đổi.
  const savePromotion = async () => {
    if (!room) return;
    const text = promoText.trim();
    if (!text || !promoUntil) {
      setError("Nhập nội dung ưu đãi và ngày hết hạn trước khi lưu.");
      return;
    }
    setPromoBusy(true);
    setError(null);
    setNotice(null);
    try {
      const saved = await api.put<Promotion>(
        `/landlord/rooms/${room.id}/promotion`,
        { text, valid_until: promoUntil },
      );
      setPromotion(saved);
      setPromoText(saved.text);
      setPromoUntil(saved.valid_until);
      setNotice(`Đã lưu ưu đãi, hiển thị tới ${saved.valid_until}.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPromoBusy(false);
    }
  };
  const removePromotion = async () => {
    if (!room) return;
    setPromoBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.delete(`/landlord/rooms/${room.id}/promotion`);
      setPromotion(null);
      setPromoText("");
      setPromoUntil("");
      setNotice("Đã gỡ ưu đãi khỏi tin.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPromoBusy(false);
    }
  };
  const body = () => ({
    title: values.title.trim(),
    city: values.city,
    area: values.area.trim(),
    room_type: values.room_type,
    bedrooms:
      values.room_type === "apartment" && values.bedrooms
        ? Number(values.bedrooms)
        : null,
    capacity: values.capacity ? Number(values.capacity) : null,
    area_m2: Number(values.area_m2),
    published: values.published,
    occupancy: values.occupancy,
    amenities: values.amenities,
    features_text: values.features.trim() || null,
    house_rules: values.rules.trim() || null,
    latitude: room?.latitude ?? null,
    longitude: room?.longitude ?? null,
    location_accuracy: room?.location_accuracy ?? "area_only",
    uncertainty_m: room?.uncertainty_m ?? null,
    quote: {
      rent_vnd: Number(values.rent),
      deposit_vnd: values.deposit === "" ? null : Number(values.deposit),
      advance_months: values.advance === "" ? null : Number(values.advance),
      one_time_vnd: room?.quote.one_time_vnd ?? 0,
      fees: FEE_NAMES.map((name) => ({
        name,
        mode: values.fees[name].mode,
        included_in_rent: values.fees[name].included,
        // Trống = chưa biết (null), khác 0; hệ thống không tự điền 0.
        amount_vnd:
          values.fees[name].amount === "" ? null : values.fees[name].amount,
        source: `landlord-form/${name}`,
      })),
    },
    ...(room ? { expected_revision: room.revision } : {}),
  });
  return (
    <section className="panel room-editor" aria-label="Biên tập tin phòng">
      <div className="section-heading">
        <div>
          <span className="eyebrow">
            {room ? `SỬA TIN · v${room.revision}` : "TIN MỚI"}
          </span>
          <h2>{room ? "Sửa thông tin phòng" : "Thêm phòng cho thuê"}</h2>
        </div>
        <button className="text-button" onClick={onCancel} disabled={busy}>
          Đóng
        </button>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {notice && (
        <div className="notice success" role="status">
          {notice}
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError(null);
          try {
            await onSubmit(body());
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <div className="form-grid">
          <label>
            Tiêu đề tin
            <input
              required
              minLength={3}
              value={values.title}
              onChange={(e) => set("title", e.target.value)}
            />
          </label>
          <label>
            Thành phố
            <select
              value={values.city}
              onChange={(e) => set("city", e.target.value)}
            >
              {Object.keys(cityAreas).map((city) => (
                <option key={city}>{city}</option>
              ))}
            </select>
          </label>
          <label>
            Khu vực
            <input
              required
              list="room-area-options"
              value={values.area}
              onChange={(e) => set("area", e.target.value)}
            />
            <datalist id="room-area-options">
              {(cityAreas[values.city] || []).map((area) => (
                <option key={area} value={area} />
              ))}
            </datalist>
          </label>
          <label>
            Loại
            <select
              value={values.room_type}
              onChange={(e) => set("room_type", e.target.value as RoomType)}
            >
              {Object.entries(roomTypeLabels).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {values.room_type === "apartment" && (
            <label>
              Phòng ngủ
              <input
                type="number"
                min={1}
                max={5}
                value={values.bedrooms}
                onChange={(e) => set("bedrooms", e.target.value)}
              />
            </label>
          )}
          <label>
            Diện tích (m²)
            <input
              type="number"
              min={1}
              step="any"
              required
              value={values.area_m2}
              onChange={(e) => set("area_m2", e.target.value)}
            />
          </label>
          <label>
            Sức chứa (người)
            <input
              type="number"
              min={1}
              max={20}
              value={values.capacity}
              onChange={(e) => set("capacity", e.target.value)}
            />
          </label>
          <label>
            Tiền thuê (đ/tháng)
            <input
              type="number"
              min={0}
              required
              value={values.rent}
              onChange={(e) => set("rent", e.target.value)}
            />
          </label>
          <label>
            Tiền cọc (đ)
            <input
              type="number"
              min={0}
              value={values.deposit}
              onChange={(e) => set("deposit", e.target.value)}
            />
          </label>
          <label>
            Trả trước (tháng)
            <input
              type="number"
              min={1}
              max={24}
              value={values.advance}
              onChange={(e) => set("advance", e.target.value)}
            />
          </label>
          <label>
            Tình trạng
            <select
              value={values.occupancy}
              onChange={(e) => set("occupancy", e.target.value)}
            >
              {Object.entries(occupancyLabels).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <fieldset>
          <legend>Bảng phí (để trống nếu chưa rõ; khác 0)</legend>
          <div className="form-grid">
            {FEE_NAMES.map((name) => (
              <label key={name}>
                {FEE_LABELS[name]}
                <input
                  type="number"
                  min={0}
                  step="any"
                  value={values.fees[name].amount}
                  disabled={values.fees[name].included}
                  onChange={(e) =>
                    set("fees", {
                      ...values.fees,
                      [name]: { ...values.fees[name], amount: e.target.value },
                    })
                  }
                />
                <span className="checkbox-line">
                  <input
                    type="checkbox"
                    checked={values.fees[name].included}
                    onChange={(e) =>
                      set("fees", {
                        ...values.fees,
                        [name]: {
                          ...values.fees[name],
                          included: e.target.checked,
                        },
                      })
                    }
                  />
                  Đã gồm trong tiền thuê
                </span>
                {name === "water" && (
                  <select
                    aria-label="Cách tính nước"
                    value={values.fees.water.mode}
                    onChange={(e) =>
                      set("fees", {
                        ...values.fees,
                        water: { ...values.fees.water, mode: e.target.value },
                      })
                    }
                  >
                    <option value="person">Theo người</option>
                    <option value="m3">Theo m³</option>
                  </select>
                )}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Tiện ích</legend>
          <div className="amenity-picker">
            {Object.entries(amenities).map(([id, label]) => (
              <label className="amenity-row" key={id}>
                <span>{label}</span>
                <select
                  value={
                    values.amenities[id] == null
                      ? "unknown"
                      : values.amenities[id]
                        ? "yes"
                        : "no"
                  }
                  onChange={(e) =>
                    set("amenities", {
                      ...values.amenities,
                      [id]:
                        e.target.value === "unknown"
                          ? null
                          : e.target.value === "yes",
                    })
                  }
                >
                  <option value="unknown">Chưa rõ</option>
                  <option value="yes">Có</option>
                  <option value="no">Không</option>
                </select>
              </label>
            ))}
          </div>
        </fieldset>
        <label>
          Điểm nổi bật (view, ánh sáng, xung quanh; không ghi giá hay số điện
          thoại)
          <textarea
            rows={2}
            maxLength={500}
            value={values.features}
            onChange={(e) => set("features", e.target.value)}
          />
        </label>
        <label>
          Nội quy & cách tính phí (đưa vào cẩm nang cho khách)
          <textarea
            rows={3}
            maxLength={2000}
            value={values.rules}
            onChange={(e) => set("rules", e.target.value)}
          />
        </label>
        <label
          className="checkbox-line"
          title={publishLocked ? landlordPendingNote : undefined}
        >
          <input
            type="checkbox"
            checked={values.published}
            disabled={publishLocked}
            onChange={(e) => set("published", e.target.checked)}
          />
          Công khai tin cho khách tìm thấy
        </label>
        {publishLocked && (
          <small className="input-hint">{landlordPendingNote}</small>
        )}
        <div className="form-actions">
          <button
            type="button"
            className="button outline"
            onClick={onCancel}
            disabled={busy}
          >
            Hủy
          </button>
          <button className="button" disabled={busy}>
            <Icon name="check" size={16} />
            {busy ? "Đang lưu…" : room ? "Lưu thay đổi" : "Tạo tin"}
          </button>
        </div>
      </form>
      {/* FE-05/FE-06: ảnh và ưu đãi cần tin đã có id do máy chủ cấp. */}
      {room && (
        <>
          <fieldset className="media-editor">
            <legend>Ảnh tin</legend>
            <label>
              Chọn ảnh (JPEG/PNG/WebP, tối đa 5 MB mỗi ảnh)
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                disabled={Boolean(uploading)}
                onChange={(e) => {
                  void uploadPhotos(e.target.files);
                  e.target.value = "";
                }}
              />
            </label>
            {uploading && (
              <p className="input-hint" role="status">
                Đang tải ảnh {uploading.done}/{uploading.total}…
              </p>
            )}
            {media.length ? (
              <ul className="media-grid">
                {media.map((photo, index) => (
                  <li key={photo.id} className="media-item">
                    <img
                      src={mediaSrc(photo.url)}
                      alt={`Ảnh ${index + 1} của ${roomTitle(room.title)}`}
                    />
                    <div className="media-actions">
                      <button
                        type="button"
                        className="text-button"
                        aria-label={`Đưa ảnh ${index + 1} lên`}
                        disabled={index === 0 || Boolean(uploading)}
                        onClick={() => void movePhoto(index, -1)}
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        aria-label={`Đưa ảnh ${index + 1} xuống`}
                        disabled={
                          index === media.length - 1 || Boolean(uploading)
                        }
                        onClick={() => void movePhoto(index, 1)}
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        className="text-button"
                        aria-label={`Xóa ảnh ${index + 1}`}
                        disabled={Boolean(uploading)}
                        onClick={() => void deletePhoto(photo)}
                      >
                        Xóa
                      </button>
                    </div>
                    {index === 0 && (
                      <small className="input-hint">Ảnh bìa</small>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="subtle">
                Tin chưa có ảnh thật; khách thấy hình minh họa.
              </p>
            )}
          </fieldset>
          <fieldset className="promotion-editor">
            <legend>Ưu đãi</legend>
            {promotion && (
              <p className="notice" role="status">
                Đang có ưu đãi đến {promotion.valid_until}: {promotion.text}
              </p>
            )}
            <label>
              Nội dung ưu đãi (hiển thị cho khách, không đổi giá trong tin)
              <textarea
                rows={2}
                maxLength={PROMO_MAX_CHARS}
                value={promoText}
                onChange={(e) => setPromoText(e.target.value)}
              />
            </label>
            <small className="input-hint">
              {promoText.trim().length}/{PROMO_MAX_CHARS} ký tự
            </small>
            <label>
              Hết hạn vào ngày (tối đa {PROMO_MAX_DAYS} ngày tới)
              <input
                type="date"
                min={isoDay(0)}
                max={isoDay(PROMO_MAX_DAYS)}
                value={promoUntil}
                onChange={(e) => setPromoUntil(e.target.value)}
              />
            </label>
            <div className="form-actions">
              <button
                type="button"
                className="button outline"
                disabled={promoBusy}
                onClick={() => void removePromotion()}
              >
                Gỡ ưu đãi
              </button>
              <button
                type="button"
                className="button"
                disabled={promoBusy}
                onClick={() => void savePromotion()}
              >
                <Icon name="check" size={16} />
                {promoBusy ? "Đang lưu…" : "Lưu ưu đãi"}
              </button>
            </div>
          </fieldset>
        </>
      )}
    </section>
  );
}
