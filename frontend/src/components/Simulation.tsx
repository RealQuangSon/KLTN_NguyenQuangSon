import { useState } from "react";
import type { Api } from "../api";
import type { Candidate, Cost, Profile } from "../types";
import { bandLabels } from "../types";
import { ErrorNotice, Icon, money, percent, roomTitle } from "./Shared";
// Mô phỏng tối đa 3 kịch bản tài chính cho một căn đã duyệt (FR-08). Chỉ đọc:
// máy chủ tính bằng engine tài chính, không đổi hồ sơ đã xác nhận hay danh sách
// đã duyệt. Muốn tìm theo kịch bản mới, khách phải xác nhận hồ sơ mới.
type LoanMode = "profile" | "none" | "custom";
interface Option {
  label: string;
  people: string;
  split: boolean;
  loan: LoanMode;
  rate: string;
  term: string;
}
const ratePercent = (rate: string | number | undefined) =>
  rate == null ? "12" : String(Math.round(Number(rate) * 10000) / 100);
const defaults = (profile: Profile): Option[] => {
  const base = {
    people: String(profile.scenario.people),
    split: profile.cost_split === "equal",
    rate: ratePercent(profile.loan?.annual_rate),
  };
  return [
    { ...base, label: "Hồ sơ hiện tại", loan: "profile", term: "6" },
    { ...base, label: "Vay 12 tháng", loan: "custom", term: "12" },
    { ...base, label: "Không vay", loan: "none", term: "6" },
  ];
};
export function SimulationPanel({
  room,
  sessionId,
  profile,
  api,
  onClose,
}: {
  room: Candidate;
  sessionId: string;
  profile: Profile;
  api: Api;
  onClose: () => void;
}) {
  const [options, setOptions] = useState<Option[]>(() => defaults(profile));
  const [results, setResults] = useState<{ label: string; cost: Cost }[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const update = (index: number, patch: Partial<Option>) =>
    setOptions((list) =>
      list.map((option, i) => (i === index ? { ...option, ...patch } : option)),
    );
  const body = () => ({
    room_id: room.room_id,
    scenarios: options.map((option) => ({
      label: option.label.trim() || "Kịch bản",
      ...(Number(option.people) !== profile.scenario.people
        ? { scenario: { ...profile.scenario, people: Number(option.people) } }
        : {}),
      cost_split: option.split && Number(option.people) > 1 ? "equal" : "none",
      ...(option.loan === "none"
        ? { loan: null }
        : option.loan === "custom"
          ? {
              loan: {
                annual_rate: String(Number(option.rate) / 100),
                term_months: Number(option.term),
                max_principal_vnd: profile.loan?.max_principal_vnd ?? null,
              },
            }
          : {}),
    })),
  });
  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      const output = await api.post<{
        items: { label: string; cost: Cost }[];
      }>(`/sessions/${sessionId}/simulate`, body());
      setResults(output.items);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const row = (label: string, value: (cost: Cost) => string) => (
    <tr>
      <th>{label}</th>
      {results.map((item, index) => (
        <td key={index}>{value(item.cost)}</td>
      ))}
    </tr>
  );
  return (
    <section className="panel simulation" aria-label="Mô phỏng tài chính">
      <div className="section-heading">
        <div>
          <span className="eyebrow">MÔ PHỎNG · KHÔNG ĐỔI HỒ SƠ</span>
          <h2>{roomTitle(room.title)}</h2>
        </div>
        <button className="text-button" onClick={onClose}>
          Đóng mô phỏng
        </button>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      <div className="simulation-options">
        {options.map((option, index) => (
          <fieldset key={index}>
            <legend>Kịch bản {index + 1}</legend>
            <label>
              Tên
              <input
                value={option.label}
                maxLength={60}
                onChange={(e) => update(index, { label: e.target.value })}
              />
            </label>
            <label>
              Số người ở
              <input
                type="number"
                min={1}
                max={20}
                value={option.people}
                onChange={(e) => update(index, { people: e.target.value })}
              />
            </label>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={option.split}
                disabled={Number(option.people) < 2}
                onChange={(e) => update(index, { split: e.target.checked })}
              />
              Chia đều chi phí
            </label>
            <label>
              Khoản vay
              <select
                value={option.loan}
                onChange={(e) =>
                  update(index, { loan: e.target.value as LoanMode })
                }
              >
                <option value="profile">Theo hồ sơ</option>
                <option value="none">Không vay</option>
                <option value="custom">Tự nhập</option>
              </select>
            </label>
            {option.loan === "custom" && (
              <div className="form-grid">
                <label>
                  Lãi %/năm
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step="any"
                    value={option.rate}
                    onChange={(e) => update(index, { rate: e.target.value })}
                  />
                </label>
                <label>
                  Số tháng
                  <input
                    type="number"
                    min={1}
                    max={36}
                    value={option.term}
                    onChange={(e) => update(index, { term: e.target.value })}
                  />
                </label>
              </div>
            )}
          </fieldset>
        ))}
      </div>
      <button className="button" onClick={() => void run()} disabled={busy}>
        <Icon name="refresh" size={16} />
        {busy ? "Đang tính…" : "Tính các kịch bản"}
      </button>
      {results.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Chỉ số</th>
                {results.map((item, index) => (
                  <th key={index}>{item.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {row("Tổng tháng", (c) => money(c.monthly_total_vnd))}
              {row("Tiền vào ở", (c) => money(c.initial_total_vnd))}
              {row("Còn thiếu khi vào ở", (c) =>
                money(c.affordability?.shortfall_vnd),
              )}
              {row("Trả góp", (c) =>
                c.affordability?.loan
                  ? `${money(c.affordability.loan.installment_vnd)} × ${c.affordability.loan.term_months} tháng`
                  : "Không vay",
              )}
              {row("Tổng lãi", (c) =>
                c.affordability?.loan
                  ? money(c.affordability.loan.total_interest_vnd)
                  : "—",
              )}
              {row("Phần của bạn mỗi tháng", (c) =>
                money(c.affordability?.renter_burden_vnd),
              )}
              {row("Khả năng chi trả", (c) =>
                c.affordability
                  ? `${bandLabels[c.affordability.band]}${
                      c.affordability.housing_ratio
                        ? ` (${percent(c.affordability.housing_ratio)})`
                        : ""
                    }`
                  : "Chưa rõ",
              )}
            </tbody>
          </table>
        </div>
      )}
      <p className="input-hint">
        Ước tính theo lãi suất bạn nhập, không phải báo giá tín dụng. Muốn tìm
        phòng theo kịch bản mới, hãy sửa và xác nhận lại hồ sơ.
      </p>
    </section>
  );
}
