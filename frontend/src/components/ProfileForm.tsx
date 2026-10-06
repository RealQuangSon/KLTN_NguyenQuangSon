import { useEffect, useRef, useState } from "react";
import type { Draft, Profile, RoomType } from "../types";
import { amenities, roomTypeLabels } from "../types";
import { cityAreas, defaultDestination } from "../locations";
import { Icon, money } from "./Shared";
interface FormValues {
  city: string;
  area: string;
  room_type: RoomType;
  bedrooms: string;
  monthly: string;
  initial: string;
  income: string;
  split: boolean;
  loan: boolean;
  rate: string;
  term: string;
  maxPrincipal: string;
  people: string;
  vehicles: string;
  kwh: string;
  water: string;
  moving: string;
  setup: string;
  soft: string;
  destination: boolean;
  label: string;
  latitude: string;
  longitude: string;
  uncertainty: string;
  radius: string;
  must: string[];
  preferences: string[];
}
const initialValues = (
  draft: Draft,
  confirmed: Profile | null,
): FormValues => ({
  city: confirmed?.city || draft.city || "",
  area: confirmed?.area || draft.area || "",
  room_type: confirmed?.room_type || draft.room_type || "room",
  bedrooms: String(confirmed?.min_bedrooms ?? draft.bedrooms ?? ""),
  monthly: confirmed ? String(confirmed.max_monthly_cost_vnd) : "",
  initial:
    confirmed?.max_initial_cash_vnd == null
      ? ""
      : String(confirmed.max_initial_cash_vnd),
  income:
    confirmed?.monthly_income_vnd == null
      ? ""
      : String(confirmed.monthly_income_vnd),
  split: confirmed?.cost_split === "equal",
  loan: Boolean(confirmed?.loan),
  // Lãi suất nhập theo %/năm cho dễ đọc; gửi lên server dạng tỷ lệ (0.12).
  rate: confirmed?.loan
    ? String(Math.round(Number(confirmed.loan.annual_rate) * 10000) / 100)
    : "12",
  term: String(confirmed?.loan?.term_months ?? 6),
  maxPrincipal:
    confirmed?.loan?.max_principal_vnd == null
      ? ""
      : String(confirmed.loan.max_principal_vnd),
  people: String(confirmed?.scenario.people || draft.people || 1),
  vehicles: String(confirmed?.scenario.vehicles ?? 1),
  kwh: String(confirmed?.scenario.electricity_kwh ?? 140),
  water: String(confirmed?.scenario.water_m3 ?? 3),
  moving: String(confirmed?.scenario.moving_vnd ?? 300000),
  setup: String(confirmed?.scenario.setup_vnd ?? 200000),
  soft: confirmed?.soft_description || draft.soft_description || "",
  destination: Boolean(confirmed?.destination || draft.needs_destination),
  label: confirmed?.destination?.label || "Điểm học tập mẫu · giả lập",
  latitude: String(
    confirmed?.destination?.latitude ??
      (
        defaultDestination[confirmed?.city || draft.city || ""] ??
        defaultDestination["TP.HCM"]
      ).latitude,
  ),
  longitude: String(
    confirmed?.destination?.longitude ??
      (
        defaultDestination[confirmed?.city || draft.city || ""] ??
        defaultDestination["TP.HCM"]
      ).longitude,
  ),
  uncertainty: String(confirmed?.destination?.uncertainty_m ?? 100),
  radius: String(confirmed?.destination?.max_distance_m ?? 1500),
  must: confirmed?.must_amenities || [],
  preferences: confirmed?.preferences || draft.preferences,
});
export function ProfileForm({
  draft,
  revision,
  confirmed,
  confirmedVersion,
  busy,
  onConfirm,
  onSave,
  onDirty,
}: {
  draft: Draft;
  revision: number;
  confirmed: Profile | null;
  confirmedVersion?: number;
  busy: boolean;
  onConfirm: (profile: Profile) => Promise<boolean>;
  onSave: (values: {
    city: string;
    area: string | null;
    people: number;
    preferences: string[];
    room_type: RoomType;
    needs_destination: boolean;
    soft_description: string | null;
  }) => Promise<boolean>;
  onDirty: (dirty: boolean) => void;
}) {
  const [values, setValues] = useState(() => initialValues(draft, confirmed));
  const [dirty, setDirty] = useState(false);
  const [seenRevision, setSeenRevision] = useState(revision);
  const previousConfirmed = useRef(confirmedVersion);
  useEffect(() => {
    if (!dirty) {
      if (!confirmed || previousConfirmed.current !== confirmedVersion) {
        setValues(initialValues(draft, confirmed));
        setSeenRevision(revision);
        previousConfirmed.current = confirmedVersion;
      } else if (seenRevision !== revision) {
        // Keep confirmed finance/scenario until the renter explicitly applies
        // the conversation draft and confirms a new profile version.
        setDirty(true);
        onDirty(true);
      }
    }
  }, [
    revision,
    confirmed,
    confirmedVersion,
    dirty,
    draft,
    seenRevision,
    onDirty,
  ]);
  const set = (key: keyof FormValues, value: string | boolean | string[]) => {
    setValues((v) => ({ ...v, [key]: value }));
    setDirty(true);
    onDirty(true);
  };
  const toggle = (id: string, kind: "must" | "preferences") => {
    setValues((v) => ({
      ...v,
      [kind]: v[kind].includes(id)
        ? v[kind].filter((x) => x !== id)
        : [...v[kind], id],
      [kind === "must" ? "preferences" : "must"]: v[
        kind === "must" ? "preferences" : "must"
      ].filter((x) => x !== id),
    }));
    setDirty(true);
    onDirty(true);
  };
  const profile = (): Profile => ({
    city: values.city.trim(),
    area: values.area.trim() || null,
    room_type: values.room_type,
    min_bedrooms:
      values.room_type === "apartment" && values.bedrooms !== ""
        ? Number(values.bedrooms)
        : null,
    max_monthly_cost_vnd: Number(values.monthly),
    max_initial_cash_vnd: values.initial === "" ? null : Number(values.initial),
    monthly_income_vnd: values.income === "" ? null : Number(values.income),
    cost_split: values.split && Number(values.people) > 1 ? "equal" : "none",
    loan: values.loan
      ? {
          annual_rate: String(Number(values.rate) / 100),
          term_months: Number(values.term),
          max_principal_vnd:
            values.maxPrincipal === "" ? null : Number(values.maxPrincipal),
        }
      : null,
    must_amenities: values.must,
    preferences: values.preferences,
    soft_description: values.soft.trim() || null,
    scenario: {
      people: Number(values.people),
      vehicles: Number(values.vehicles),
      electricity_kwh: values.kwh,
      water_m3: values.water,
      moving_vnd: Number(values.moving),
      setup_vnd: Number(values.setup),
    },
    destination: values.destination
      ? {
          label: values.label,
          latitude: Number(values.latitude),
          longitude: Number(values.longitude),
          uncertainty_m: Number(values.uncertainty),
          max_distance_m: Number(values.radius),
        }
      : null,
  });
  const numberField = (
    label: string,
    key: keyof FormValues,
    min = 0,
    max?: number,
    required = true,
    step: number | string = 1,
  ) => (
    <label>
      {label}
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        required={required}
        value={values[key] as string}
        onChange={(e) => set(key, e.target.value)}
        disabled={busy}
      />
    </label>
  );
  return (
    <section className="panel profile-panel">
      <div className="section-heading">
        <div>
          <span className="eyebrow">BẠN LÀ NGƯỜI QUYẾT ĐỊNH</span>
          <h2>Hồ sơ nhu cầu</h2>
        </div>
        <span className={`badge ${confirmed && !dirty ? "success" : "muted"}`}>
          {confirmed && !dirty
            ? `Đã xác nhận · v${confirmedVersion}`
            : `Nháp · v${revision}`}
        </span>
      </div>
      <p className="subtle">
        Tiêu chí chỉ có hiệu lực sau khi bạn xác nhận. Gợi ý mới luôn cần quản
        lý duyệt.
      </p>
      {confirmed && (
        <div className="confirmed-summary">
          <Icon name="shield" size={18} />
          <div>
            <strong>Ngân sách đã xác nhận</strong>
            <span>{money(confirmed.max_monthly_cost_vnd)} / tháng</span>
            <small>
              {dirty
                ? "Bạn đang sửa nhu cầu. Xác nhận lại để cập nhật gợi ý."
                : "Gợi ý và chi phí dùng hồ sơ đã xác nhận này."}
            </small>
          </div>
        </div>
      )}
      {dirty && seenRevision !== revision && (
        <div className="notice warning">
          Hội thoại đã cập nhật nháp.{" "}
          <button
            className="text-button"
            onClick={() => {
              setValues((v) => ({
                ...v,
                city: draft.city || "",
                area: draft.area || "",
                people: draft.people == null ? "" : String(draft.people),
                preferences: draft.preferences.filter(
                  (id) => !v.must.includes(id),
                ),
                room_type: draft.room_type || v.room_type,
                bedrooms:
                  draft.bedrooms == null ? v.bedrooms : String(draft.bedrooms),
                soft: draft.soft_description || "",
                destination: draft.needs_destination,
              }));
              setSeenRevision(revision);
            }}
          >
            Áp dụng dữ liệu hội thoại
          </button>
        </div>
      )}
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          if (await onConfirm(profile())) {
            setDirty(false);
            onDirty(false);
          }
        }}
      >
        <div className="form-grid">
          <label>
            Thành phố
            <select
              required
              value={values.city}
              onChange={(e) => {
                const city = e.target.value;
                const point = defaultDestination[city];
                setValues((v) => ({
                  ...v,
                  city,
                  ...(point && !confirmed?.destination
                    ? {
                        latitude: String(point.latitude),
                        longitude: String(point.longitude),
                      }
                    : {}),
                }));
                setDirty(true);
                onDirty(true);
              }}
              disabled={busy}
            >
              <option value="">Chọn thành phố</option>
              {Object.keys(cityAreas).map((city) => (
                <option key={city} value={city}>
                  {city}
                </option>
              ))}
              {values.city && !(values.city in cityAreas) && (
                <option value={values.city}>{values.city}</option>
              )}
            </select>
          </label>
          <label>
            Khu vực
            <input
              list="area-options"
              placeholder={
                values.city === "Hà Nội" ? "Ví dụ: Cầu Giấy" : "Ví dụ: Quận 7"
              }
              value={values.area}
              onChange={(e) => set("area", e.target.value)}
              disabled={busy}
            />
            <datalist id="area-options">
              {(cityAreas[values.city] || []).map((area) => (
                <option key={area} value={area} />
              ))}
            </datalist>
          </label>
          <label>
            Loại chỗ ở
            <select
              value={values.room_type}
              onChange={(e) => set("room_type", e.target.value)}
              disabled={busy}
            >
              {Object.entries(roomTypeLabels).map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          {values.room_type === "apartment" &&
            numberField("Số phòng ngủ tối thiểu", "bedrooms", 1, 5, false)}
          {numberField("Ngân sách tổng tháng (VND)", "monthly", 1)}
          {numberField(
            "Tiền mặt sẵn có cho vào ở (VND)",
            "initial",
            0,
            undefined,
            false,
          )}
        </div>
        {draft.budget_hint_vnd != null && (
          <p className="input-hint">
            Hội thoại nhắc {money(draft.budget_hint_vnd)}. Nhập trần{" "}
            <strong>tổng tháng</strong> ở trên; tiền được nhắc chưa phải ngân
            sách đã xác nhận.
          </p>
        )}
        <fieldset>
          <legend>Năng lực tài chính</legend>
          <div className="form-grid">
            {numberField(
              "Thu nhập mỗi tháng (VND)",
              "income",
              1,
              undefined,
              false,
            )}
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={values.split}
                onChange={(e) => set("split", e.target.checked)}
                disabled={busy || Number(values.people) < 2}
              />
              Chia đều chi phí cho người ở ghép
            </label>
          </div>
          <p className="input-hint">
            Thu nhập là tùy chọn, chỉ dùng để tính tỷ lệ chi phí nhà ở. Sale chỉ
            thấy mức đánh giá (trong khuyến nghị / cần cân nhắc / vượt), không
            thấy con số này.
          </p>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={values.loan}
              onChange={(e) => set("loan", e.target.checked)}
              disabled={busy}
            />
            Nếu thiếu tiền vào ở, ước tính khoản vay ngắn hạn
          </label>
          {values.loan && (
            <div className="form-grid three">
              {numberField("Lãi suất (%/năm)", "rate", 0, 100, true, "any")}
              {numberField("Số tháng trả góp", "term", 1, 36)}
              {numberField(
                "Vay tối đa (VND)",
                "maxPrincipal",
                1,
                undefined,
                false,
              )}
            </div>
          )}
          {values.loan && (
            <p className="input-hint">
              Ước tính trả góp đều với lãi suất bạn nhập, không phải báo giá của
              tổ chức tín dụng. Khi vay, tổng tháng cộng trả góp vẫn phải trong
              ngân sách.
            </p>
          )}
        </fieldset>
        <fieldset>
          <legend>Tiện ích — bắt buộc hay chỉ ưu tiên?</legend>
          <div className="amenity-picker">
            {Object.entries(amenities).map(([id, label]) => (
              <div className="amenity-row" key={id}>
                <span>{label}</span>
                <div>
                  <button
                    type="button"
                    className={
                      values.must.includes(id) ? "choice active" : "choice"
                    }
                    aria-pressed={values.must.includes(id)}
                    onClick={() => toggle(id, "must")}
                    disabled={busy}
                  >
                    Bắt buộc
                  </button>
                  <button
                    type="button"
                    className={
                      values.preferences.includes(id)
                        ? "choice active soft"
                        : "choice"
                    }
                    aria-pressed={values.preferences.includes(id)}
                    onClick={() => toggle(id, "preferences")}
                    disabled={busy}
                  >
                    Ưu tiên
                  </button>
                </div>
              </div>
            ))}
          </div>
        </fieldset>
        <fieldset>
          <legend>Kịch bản sử dụng</legend>
          <p className="input-hint">
            Các giá trị ban đầu là giả định demo. Hãy điều chỉnh để tổng chi phí
            phản ánh mức dùng của bạn.
          </p>
          <div className="form-grid three">
            {numberField("Số người", "people", 1, 20)}
            {numberField("Số xe", "vehicles", 0, 20)}
            {numberField(
              "Điện / tháng (kWh)",
              "kwh",
              0,
              undefined,
              true,
              "any",
            )}
            {numberField(
              "Nước / tháng (m³)",
              "water",
              0,
              undefined,
              true,
              "any",
            )}
            {numberField("Chuyển nhà (VND)", "moving")}
            {numberField("Sắm sửa (VND)", "setup")}
          </div>
        </fieldset>
        <fieldset>
          <legend>Vị trí & sở thích bổ sung</legend>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={values.destination}
              onChange={(e) => set("destination", e.target.checked)}
              disabled={busy}
            />
            Bắt buộc gần điểm học tập / làm việc
          </label>
          {draft.needs_destination && !values.destination && (
            <p className="input-hint">
              Bạn đang chủ động bỏ yêu cầu khoảng cách đã nhắc trong hội thoại.
            </p>
          )}
          {values.destination && (
            <div className="destination-form">
              <p className="notice info">
                Điểm mặc định là tọa độ <strong>giả lập</strong> để thử nghiệm.
                Khoảng cách là đường thẳng có xét sai số, không phải thời gian
                di chuyển.
              </p>
              <label>
                Tên điểm đến
                <input
                  value={values.label}
                  onChange={(e) => set("label", e.target.value)}
                  required
                  maxLength={120}
                  disabled={busy}
                />
              </label>
              <div className="form-grid">
                {numberField("Vĩ độ", "latitude", -90, 90, true, "any")}
                {numberField("Kinh độ", "longitude", -180, 180, true, "any")}
                {numberField("Sai số điểm đến (m)", "uncertainty")}
                {numberField("Bán kính tối đa (m)", "radius", 1)}
              </div>
            </div>
          )}
          <label>
            Mô tả ưu tiên mềm <span className="optional">(tùy chọn)</span>
            <textarea
              placeholder="Ví dụ: có ánh sáng tự nhiên, phù hợp học tập"
              maxLength={500}
              rows={2}
              value={values.soft}
              onChange={(e) => set("soft", e.target.value)}
              disabled={busy}
            />
          </label>
        </fieldset>
        <div className="form-actions">
          <button
            type="button"
            className="button outline"
            disabled={busy || !values.city.trim()}
            onClick={() =>
              void onSave({
                city: values.city.trim(),
                area: values.area.trim() || null,
                people: Number(values.people),
                preferences: values.preferences,
                room_type: values.room_type,
                needs_destination: values.destination,
                soft_description: values.soft.trim() || null,
              })
            }
          >
            Lưu nháp
          </button>
          <button type="submit" className="button" disabled={busy}>
            <Icon name="check" size={17} />
            {busy ? "Đang xử lý…" : "Xác nhận & tìm phòng"}
          </button>
        </div>
        <p className="input-hint">
          Đổi hồ sơ hoặc kịch bản cần tạo gợi ý mới và duyệt lại. Lưu nháp chưa
          xác nhận ngân sách.
        </p>
      </form>
    </section>
  );
}
