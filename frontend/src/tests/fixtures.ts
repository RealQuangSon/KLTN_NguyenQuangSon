import type { Candidate, Cost, Profile, Session } from "../types";
export const cost: Cost = {
  monthly_known_vnd: 2500000,
  monthly_total_vnd: null,
  initial_known_vnd: 0,
  initial_total_vnd: null,
  missing_monthly: ["electricity"],
  missing_initial: ["deposit"],
  lines: [
    {
      name: "internet",
      amount_vnd: 0,
      period: "monthly",
      source: "demo://included",
      included_in_rent: true,
    },
    {
      name: "electricity",
      amount_vnd: null,
      period: "monthly",
      source: "demo://missing",
      included_in_rent: false,
    },
  ],
  assumptions: { people: 1, vehicles: 0 },
};
export const room = (id = "room-1"): Candidate => ({
  room_id: id,
  room_revision: 1,
  title: `Phòng riêng ${id}`,
  city: "TP.HCM",
  area: "Quận 7",
  area_m2: 20,
  cost,
  score: 0.7,
  components: { cost: 0.7 },
  reasons: ["Có cửa sổ theo nguồn"],
  tradeoffs: ["Chưa xác định tiền cọc"],
  source: "demo://room",
  synthetic: true,
  algorithm: "structured_baseline_v1",
});
export const profile: Profile = {
  city: "TP.HCM",
  area: "Quận 7",
  room_type: "room",
  max_monthly_cost_vnd: 3500000,
  max_initial_cash_vnd: 6500000,
  must_amenities: [],
  preferences: ["window"],
  scenario: {
    people: 1,
    vehicles: 1,
    electricity_kwh: "140",
    water_m3: "3",
    moving_vnd: 300000,
    setup_vnd: 200000,
  },
  destination: null,
};
export const session = (id = "session-1"): Session => ({
  session_id: id,
  draft_revision: 1,
  draft: {
    city: "TP.HCM",
    area: "Quận 7",
    people: 1,
    preferences: ["window"],
    budget_hint_vnd: 3500000,
    needs_destination: false,
  },
  profile_version: 1,
  confirmed_profile: profile,
  active_run_id: "run-1",
});
export function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (value: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
