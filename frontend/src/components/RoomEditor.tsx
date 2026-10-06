import { useState } from "react";
import type { Fee, Room, RoomType } from "../types";
import { amenities, occupancyLabels, roomTypeLabels } from "../types";
import { cityAreas } from "../locations";
import { ErrorNotice, Icon } from "./Shared";
// Form tạo/sửa tin của chủ nhà. Máy chủ gán id, revision, chủ sở hữu và nguồn;
// sửa tin dùng expected_revision để không ghi đè thay đổi của phiên khác.
const FEE_NAMES = [
  "electricity",
  "water",
  "internet",
  "parking",
  "service",
] as const;
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
  area_m2: String(room?.area_m2 ?? 20),
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
export function RoomEditor({
  room,
  onSubmit,
  onCancel,
}: {
  room: Room | null;
  onSubmit: (body: Record<string, unknown>) => Promise<void>;
  onCancel: () => void;
}) {
  const [values, setValues] = useState<Values>(() => fromRoom(room));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof Values>(key: K, value: Values[K]) =>
    setValues((v) => ({ ...v, [key]: value }));
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
        <label className="checkbox-line">
          <input
            type="checkbox"
            checked={values.published}
            onChange={(e) => set("published", e.target.checked)}
          />
          Công khai tin cho khách tìm thấy
        </label>
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
    </section>
  );
}
