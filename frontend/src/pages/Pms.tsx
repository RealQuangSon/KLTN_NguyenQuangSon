import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api";
import type { Room } from "../types";
import { EmptyState, ErrorNotice, Icon, money } from "../components/Shared";
import { DocumentViewer } from "../components/DocumentViewer";
// Quản lý vận hành (PMS & CRM): hợp đồng, hóa đơn/công nợ, sửa chữa, khách
// tiềm năng, tổng quan và báo cáo. Mọi con số do máy chủ tính; giao diện chỉ
// hiển thị và gửi thao tác có kiểm tra quyền ở máy chủ.
type Side = "landlord" | "renter";
interface Lease {
  id: string;
  landlord_id: string;
  renter_id: string;
  room_id: string;
  start_date: string;
  end_date: string;
  rent_vnd: number;
  deposit_vnd: number;
  payment_day: number;
  occupants: number;
  vehicles: number;
  status: string;
  version: number;
  renter_accepted_version: number | null;
  renewal_of: string | null;
  settlement_note: string | null;
}
interface InvoiceLine {
  label: string;
  quantity: string;
  unit_price: string;
  amount_vnd: number;
}
interface Invoice {
  id: string;
  lease_id: string;
  period: string;
  total_vnd: number;
  paid_vnd: number;
  balance_vnd: number;
  payment_status: "unpaid" | "partially_paid" | "paid";
  overdue: boolean;
  due_date: string;
  room_id: string;
  renter_id: string;
  lines: InvoiceLine[];
  payments?: { receipt_no: string; amount_vnd: number; recorded_at: string }[];
}
interface Claim {
  id: string;
  invoice_id: string;
  amount_vnd: number;
  reference: string | null;
  status: string;
  period: string;
  room_id: string;
}
interface Ticket {
  id: string;
  room_id: string;
  renter_id: string;
  title: string;
  description: string;
  priority: string;
  status: string;
  assignee: string | null;
  cost_vnd: number | null;
  timeline: { at: string; by: string; status: string; note: string | null }[];
}
interface Lead {
  id: string;
  renter_id: string;
  room_id: string;
  stage: string;
  score: number;
  interest: "hot" | "warm" | "cold";
  sources: string[];
  notes: string | null;
}
const leaseStatus: Record<string, string> = {
  draft: "Bản nháp",
  sent: "Đã gửi khách",
  accepted: "Khách đã chấp thuận",
  active: "Đang hiệu lực",
  ended: "Đã kết thúc",
  terminated: "Đã thanh lý",
};
const payStatus: Record<string, string> = {
  unpaid: "Chưa thanh toán",
  partially_paid: "Thanh toán một phần",
  paid: "Đã thanh toán",
};
const ticketStatus: Record<string, string> = {
  submitted: "Mới gửi",
  assigned: "Đã phân công",
  in_progress: "Đang xử lý",
  resolved: "Đã xử lý, chờ xác nhận",
  closed: "Đã đóng",
  reopened: "Mở lại",
};
const stageLabels: Record<string, string> = {
  new: "Mới quan tâm",
  contacted: "Đã trao đổi",
  viewing: "Hẹn xem",
  negotiating: "Đang thương lượng",
  won: "Đã thuê",
  lost: "Không thành",
};
const interestLabels = {
  hot: "Rất quan tâm",
  warm: "Quan tâm",
  cold: "Mới xem",
};
function useLoad<T>(load: () => Promise<T>, initial: T) {
  const [data, setData] = useState<T>(initial);
  const [error, setError] = useState<string | null>(null);
  const refresh = useCallback(async () => {
    setError(null);
    try {
      setData(await load());
    } catch (err) {
      setError((err as Error).message);
    }
  }, [load]);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const act = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      await refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  return { data, error, setError, refresh, act };
}
function Heading({
  eyebrow,
  title,
  text,
}: {
  eyebrow: string;
  title: string;
  text: string;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{text}</p>
      </div>
    </div>
  );
}
// ------------------------------------------------------------ dashboard
export function LandlordDashboard({ api }: { api: Api }) {
  const load = useCallback(
    async () => ({
      dashboard: await api.get<Record<string, number | string | null>>(
        "/landlord/dashboard",
      ),
      analytics: await api.get<{
        rooms: {
          room_id: string;
          title: string;
          views: number;
          viewings_requested: number;
          leases_won: number;
          revenue_vnd: number;
          view_to_viewing: number | null;
          viewing_to_lease: number | null;
        }[];
      }>("/landlord/analytics"),
    }),
    [api],
  );
  const { data, error, setError } = useLoad(
    load,
    null as null | Awaited<ReturnType<typeof load>>,
  );
  const d = data?.dashboard;
  const pct = (value: number | null | undefined) =>
    value == null ? "—" : `${Math.round(value * 100)}%`;
  return (
    <>
      <Heading
        eyebrow="BẢNG ĐIỀU KHIỂN"
        title="Sức khỏe vận hành"
        text="Tỷ lệ lấp đầy, doanh thu thực thu, công nợ và hiệu quả từng phòng, tính từ dữ liệu trong hệ thống."
      />
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {d && (
        <div className="stat-grid">
          {[
            ["Tỷ lệ lấp đầy", pct(d.occupancy_rate as number | null), "home"],
            [
              "Phòng trống / đã cọc / đã thuê",
              `${d.vacant} / ${d.deposited} / ${d.rented}`,
              "grid",
            ],
            [
              `Thực thu ${d.month}`,
              money(d.revenue_month_vnd as number),
              "check",
            ],
            ["Công nợ tồn đọng", money(d.outstanding_vnd as number), "clock"],
            ["Hóa đơn quá hạn", String(d.overdue_invoices), "shield"],
            ["Lịch xem 7 ngày tới", String(d.upcoming_viewings), "calendar"],
            ["Sự cố đang mở", String(d.open_tickets), "refresh"],
            [
              "Hợp đồng hết hạn 30 ngày",
              String(d.leases_ending_30d),
              "compare",
            ],
          ].map(([label, value, icon]) => (
            <div className="stat-card" key={label}>
              <span className="stat-icon">
                <Icon name={icon} size={20} />
              </span>
              <div>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            </div>
          ))}
        </div>
      )}
      <section className="panel">
        <h2>Báo cáo & phân tích theo phòng</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Phòng</th>
                <th>Lượt xem</th>
                <th>Yêu cầu xem</th>
                <th>Xem → hẹn</th>
                <th>Hẹn → thuê</th>
                <th>Đã thuê</th>
                <th>Doanh thu</th>
              </tr>
            </thead>
            <tbody>
              {(data?.analytics.rooms ?? []).map((row) => (
                <tr key={row.room_id}>
                  <td>{row.title}</td>
                  <td>{row.views}</td>
                  <td>{row.viewings_requested}</td>
                  <td>{pct(row.view_to_viewing)}</td>
                  <td>{pct(row.viewing_to_lease)}</td>
                  <td>{row.leases_won}</td>
                  <td>{money(row.revenue_vnd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
// ------------------------------------------------------------ leases
export function LeasesPage({ api, side }: { api: Api; side: Side }) {
  const load = useCallback(async () => {
    const leases = await api.get<Lease[]>("/leases");
    const rooms =
      side === "landlord"
        ? (await api.get<{ rooms: Room[] }>("/landlord/rooms")).rooms
        : [];
    return { leases, rooms };
  }, [api, side]);
  const { data, error, setError, act } = useLoad(load, {
    leases: [] as Lease[],
    rooms: [] as Room[],
  });
  const [doc, setDoc] = useState<{ title: string; html: string } | null>(null);
  const [form, setForm] = useState({
    renter_id: "",
    room_id: "",
    start_date: "",
    end_date: "",
    occupants: "1",
    vehicles: "1",
  });
  const show = (lease: Lease) =>
    act(async () => {
      const result = await api.get<{ html: string }>(
        `/leases/${lease.id}/document`,
      );
      setDoc({ title: `Hợp đồng ${lease.room_id}`, html: result.html });
    });
  return (
    <>
      <Heading
        eyebrow="HỢP ĐỒNG"
        title={
          side === "landlord" ? "Hợp đồng & khách thuê" : "Hợp đồng của tôi"
        }
        text={
          side === "landlord"
            ? "Soạn hợp đồng → gửi khách chấp thuận đúng phiên bản → kích hoạt (phòng chuyển sang đã thuê) → gia hạn hoặc thanh lý."
            : "Đọc kỹ và chấp thuận đúng phiên bản chủ nhà gửi. Chấp thuận trong ứng dụng không thay thế chữ ký số có giá trị pháp lý."
        }
      />
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {side === "landlord" && (
        <form
          className="panel inline-form"
          aria-label="Tạo hợp đồng"
          onSubmit={(e) => {
            e.preventDefault();
            void act(() =>
              api.post("/landlord/leases", {
                ...form,
                occupants: Number(form.occupants),
                vehicles: Number(form.vehicles),
              }),
            );
          }}
        >
          <label>
            Người thuê (tài khoản)
            <input
              required
              value={form.renter_id}
              onChange={(e) => setForm({ ...form, renter_id: e.target.value })}
            />
          </label>
          <label>
            Phòng
            <select
              required
              value={form.room_id}
              onChange={(e) => setForm({ ...form, room_id: e.target.value })}
            >
              <option value="">Chọn phòng</option>
              {data.rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.title.split(". ")[0]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Bắt đầu
            <input
              type="date"
              required
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
          </label>
          <label>
            Kết thúc
            <input
              type="date"
              required
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
          </label>
          <label>
            Số người
            <input
              type="number"
              min={1}
              value={form.occupants}
              onChange={(e) => setForm({ ...form, occupants: e.target.value })}
            />
          </label>
          <label>
            Số xe
            <input
              type="number"
              min={0}
              value={form.vehicles}
              onChange={(e) => setForm({ ...form, vehicles: e.target.value })}
            />
          </label>
          <button className="button">Soạn hợp đồng</button>
        </form>
      )}
      <section className="panel">
        {!data.leases.length ? (
          <EmptyState
            title="Chưa có hợp đồng"
            description="Hợp đồng sẽ xuất hiện tại đây."
            icon="compare"
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Phòng</th>
                  <th>{side === "landlord" ? "Người thuê" : "Chủ nhà"}</th>
                  <th>Thời hạn</th>
                  <th>Giá thuê / cọc</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {data.leases.map((lease) => (
                  <tr key={lease.id}>
                    <td>
                      {lease.room_id}
                      {lease.renewal_of && <small>Gia hạn</small>}
                    </td>
                    <td>
                      {side === "landlord"
                        ? lease.renter_id
                        : lease.landlord_id}
                    </td>
                    <td>
                      {lease.start_date} → {lease.end_date}
                    </td>
                    <td>
                      {money(lease.rent_vnd)} / {money(lease.deposit_vnd)}
                    </td>
                    <td>
                      {leaseStatus[lease.status] || lease.status} · v
                      {lease.version}
                    </td>
                    <td className="inline-actions">
                      <button
                        className="text-button"
                        onClick={() => void show(lease)}
                      >
                        Xem văn bản
                      </button>
                      {side === "landlord" && lease.status === "draft" && (
                        <button
                          className="text-button"
                          onClick={() =>
                            void act(() =>
                              api.post(`/landlord/leases/${lease.id}/send`, {}),
                            )
                          }
                        >
                          Gửi khách
                        </button>
                      )}
                      {side === "landlord" && lease.status === "accepted" && (
                        <button
                          className="text-button"
                          onClick={() =>
                            void act(() =>
                              api.post(
                                `/landlord/leases/${lease.id}/activate`,
                                {},
                              ),
                            )
                          }
                        >
                          Kích hoạt
                        </button>
                      )}
                      {side === "landlord" && lease.status === "active" && (
                        <>
                          <button
                            className="text-button"
                            onClick={() => {
                              const end = new Date(lease.end_date);
                              end.setMonth(end.getMonth() + 6);
                              void act(() =>
                                api.post(`/landlord/leases/${lease.id}/renew`, {
                                  end_date: end.toISOString().slice(0, 10),
                                }),
                              );
                            }}
                          >
                            Gia hạn 6 tháng
                          </button>
                          <button
                            className="text-button"
                            onClick={() =>
                              void act(() =>
                                api.post(
                                  `/landlord/leases/${lease.id}/terminate`,
                                  {
                                    end_date: new Date()
                                      .toISOString()
                                      .slice(0, 10),
                                    settlement_note:
                                      "Thanh lý theo thỏa thuận; quyết toán cọc theo biên bản bàn giao.",
                                  },
                                ),
                              )
                            }
                          >
                            Thanh lý
                          </button>
                        </>
                      )}
                      {side === "renter" && lease.status === "sent" && (
                        <button
                          className="button small"
                          onClick={() =>
                            void act(() =>
                              api.post(`/leases/${lease.id}/accept`, {
                                expected_version: lease.version,
                              }),
                            )
                          }
                        >
                          Chấp thuận phiên bản {lease.version}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {doc && (
        <DocumentViewer
          title={doc.title}
          html={doc.html}
          onClose={() => setDoc(null)}
        />
      )}
    </>
  );
}
// ------------------------------------------------------------ billing
export function BillingPage({ api, side }: { api: Api; side: Side }) {
  const load = useCallback(async () => {
    const [invoices, claims] = await Promise.all([
      api.get<Invoice[]>("/invoices"),
      api.get<Claim[]>("/payment-claims"),
    ]);
    const leases =
      side === "landlord"
        ? (await api.get<Lease[]>("/leases")).filter(
            (l) => l.status === "active",
          )
        : [];
    const summary =
      side === "landlord"
        ? await api.get<{
            periods: {
              period: string;
              billed_vnd: number;
              collected_vnd: number;
              outstanding_vnd: number;
              overdue_invoices: number;
            }[];
          }>("/landlord/billing/summary")
        : { periods: [] };
    return { invoices, claims, leases, summary };
  }, [api, side]);
  const { data, error, setError, act } = useLoad(load, {
    invoices: [] as Invoice[],
    claims: [] as Claim[],
    leases: [] as Lease[],
    summary: { periods: [] } as {
      periods: {
        period: string;
        billed_vnd: number;
        collected_vnd: number;
        outstanding_vnd: number;
        overdue_invoices: number;
      }[];
    },
  });
  const [doc, setDoc] = useState<{ title: string; html: string } | null>(null);
  const [period, setPeriod] = useState(new Date().toISOString().slice(0, 7));
  const [reading, setReading] = useState<
    Record<
      string,
      { e_start: string; e_end: string; w_start: string; w_end: string }
    >
  >({});
  const open = (invoice: Invoice, receipt?: string) =>
    act(async () => {
      const result = await api.get<{ html: string }>(
        `/invoices/${invoice.id}/document${receipt ? `?receipt_no=${encodeURIComponent(receipt)}` : ""}`,
      );
      setDoc({
        title: receipt ? `Biên lai ${receipt}` : `Hóa đơn ${invoice.period}`,
        html: result.html,
      });
    });
  const openDetail = (invoice: Invoice) =>
    act(async () => {
      const detail = await api.get<Invoice>(`/invoices/${invoice.id}`);
      const last = detail.payments?.[detail.payments.length - 1];
      if (last) await open(detail, last.receipt_no);
    });
  const num = (value: string) => (value === "" ? null : value);
  return (
    <>
      <Heading
        eyebrow="TÀI CHÍNH & CÔNG NỢ"
        title={
          side === "landlord"
            ? "Hóa đơn, thu tiền & đối soát"
            : "Hóa đơn của tôi"
        }
        text={
          side === "landlord"
            ? "Chốt chỉ số công tơ → lập hóa đơn (không sửa sau phát hành) → ghi nhận tiền hoặc xác nhận báo chuyển của khách → biên lai."
            : "Báo đã chuyển tiền chỉ thành 'đã thanh toán' khi chủ nhà xác nhận đã nhận; khi đó bạn nhận biên lai."
        }
      />
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {side === "landlord" && (
        <section className="panel">
          <h2>Chốt số & lập hóa đơn</h2>
          <label className="inline-form">
            Kỳ
            <input
              type="month"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            />
          </label>
          {data.leases.length === 0 && (
            <p className="subtle">Chưa có hợp đồng đang hiệu lực.</p>
          )}
          {data.leases.map((lease) => {
            const values = reading[lease.id] || {
              e_start: "",
              e_end: "",
              w_start: "",
              w_end: "",
            };
            const set = (key: string, value: string) =>
              setReading({
                ...reading,
                [lease.id]: { ...values, [key]: value },
              });
            return (
              <form
                key={lease.id}
                className="inline-form"
                aria-label={`Chốt số ${lease.room_id}`}
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(async () => {
                    await api.post(`/landlord/leases/${lease.id}/readings`, {
                      period,
                      electricity_start: num(values.e_start),
                      electricity_end: num(values.e_end),
                      water_start: num(values.w_start),
                      water_end: num(values.w_end),
                    });
                    await api.post(`/landlord/leases/${lease.id}/invoices`, {
                      period,
                    });
                  });
                }}
              >
                <strong>
                  {lease.room_id} · {lease.renter_id}
                </strong>
                <label>
                  Điện đầu kỳ
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={values.e_start}
                    onChange={(e) => set("e_start", e.target.value)}
                    placeholder="tự lấy kỳ trước"
                  />
                </label>
                <label>
                  Điện cuối kỳ
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={values.e_end}
                    onChange={(e) => set("e_end", e.target.value)}
                  />
                </label>
                <label>
                  Nước đầu kỳ
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={values.w_start}
                    onChange={(e) => set("w_start", e.target.value)}
                  />
                </label>
                <label>
                  Nước cuối kỳ
                  <input
                    type="number"
                    min={0}
                    step="any"
                    value={values.w_end}
                    onChange={(e) => set("w_end", e.target.value)}
                  />
                </label>
                <button className="button small">Chốt số & lập hóa đơn</button>
              </form>
            );
          })}
        </section>
      )}
      {data.claims.some((claim) => claim.status === "pending") && (
        <section className="panel">
          <h2>
            {side === "landlord"
              ? "Khách báo đã chuyển tiền (cần đối soát)"
              : "Báo chuyển tiền đang chờ"}
          </h2>
          <ul className="memory-list">
            {data.claims
              .filter((claim) => claim.status === "pending")
              .map((claim) => (
                <li key={claim.id}>
                  <span>
                    Kỳ {claim.period} · {claim.room_id} ·{" "}
                    {money(claim.amount_vnd)} ·{" "}
                    {claim.reference || "không ghi nội dung"}
                  </span>
                  {side === "landlord" && (
                    <span className="inline-actions">
                      <button
                        className="button small"
                        onClick={() =>
                          void act(() =>
                            api.post(
                              `/landlord/payment-claims/${claim.id}/confirm`,
                              {},
                            ),
                          )
                        }
                      >
                        Đã nhận
                      </button>
                      <button
                        className="button small outline"
                        onClick={() =>
                          void act(() =>
                            api.post(
                              `/landlord/payment-claims/${claim.id}/reject`,
                              {},
                            ),
                          )
                        }
                      >
                        Chưa thấy tiền
                      </button>
                    </span>
                  )}
                </li>
              ))}
          </ul>
        </section>
      )}
      <section className="panel">
        <h2>Hóa đơn</h2>
        {!data.invoices.length ? (
          <EmptyState
            title="Chưa có hóa đơn"
            description="Hóa đơn kỳ thuê xuất hiện tại đây."
            icon="clock"
          />
        ) : (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Kỳ</th>
                  <th>Phòng</th>
                  <th>Tổng</th>
                  <th>Đã thu</th>
                  <th>Còn lại</th>
                  <th>Hạn</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {data.invoices.map((invoice) => (
                  <tr key={invoice.id}>
                    <td>{invoice.period}</td>
                    <td>{invoice.room_id}</td>
                    <td>{money(invoice.total_vnd)}</td>
                    <td>{money(invoice.paid_vnd)}</td>
                    <td>{money(invoice.balance_vnd)}</td>
                    <td>{invoice.due_date}</td>
                    <td>
                      {payStatus[invoice.payment_status]}
                      {invoice.overdue && (
                        <span className="badge"> Quá hạn</span>
                      )}
                    </td>
                    <td className="inline-actions">
                      <button
                        className="text-button"
                        onClick={() => void open(invoice)}
                      >
                        Hóa đơn
                      </button>
                      {invoice.paid_vnd > 0 && (
                        <button
                          className="text-button"
                          onClick={() => void openDetail(invoice)}
                        >
                          Biên lai
                        </button>
                      )}
                      {invoice.balance_vnd > 0 && side === "landlord" && (
                        <button
                          className="text-button"
                          onClick={() =>
                            void act(() =>
                              api.post(
                                `/landlord/invoices/${invoice.id}/payments`,
                                {
                                  amount_vnd: invoice.balance_vnd,
                                  method: "cash",
                                },
                              ),
                            )
                          }
                        >
                          Thu đủ tiền mặt
                        </button>
                      )}
                      {invoice.balance_vnd > 0 && side === "renter" && (
                        <button
                          className="button small"
                          onClick={() =>
                            void act(() =>
                              api.post(`/invoices/${invoice.id}/claims`, {
                                amount_vnd: invoice.balance_vnd,
                                reference: `Chuyển khoản kỳ ${invoice.period}`,
                              }),
                            )
                          }
                        >
                          Báo đã chuyển {money(invoice.balance_vnd)}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {side === "landlord" && data.summary.periods.length > 0 && (
        <section className="panel">
          <h2>Đối soát theo kỳ</h2>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Kỳ</th>
                  <th>Phải thu</th>
                  <th>Đã thu</th>
                  <th>Còn nợ</th>
                  <th>Quá hạn</th>
                </tr>
              </thead>
              <tbody>
                {data.summary.periods.map((row) => (
                  <tr key={row.period}>
                    <td>{row.period}</td>
                    <td>{money(row.billed_vnd)}</td>
                    <td>{money(row.collected_vnd)}</td>
                    <td>{money(row.outstanding_vnd)}</td>
                    <td>{row.overdue_invoices}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      {doc && (
        <DocumentViewer
          title={doc.title}
          html={doc.html}
          onClose={() => setDoc(null)}
        />
      )}
    </>
  );
}
// ------------------------------------------------------------ maintenance
export function MaintenancePage({ api, side }: { api: Api; side: Side }) {
  const load = useCallback(async () => {
    const tickets = await api.get<Ticket[]>("/maintenance");
    const leases =
      side === "renter"
        ? (await api.get<Lease[]>("/leases")).filter(
            (l) => l.status === "active",
          )
        : [];
    return { tickets, leases };
  }, [api, side]);
  const { data, error, setError, act } = useLoad(load, {
    tickets: [] as Ticket[],
    leases: [] as Lease[],
  });
  const [form, setForm] = useState({
    room_id: "",
    title: "",
    description: "",
    priority: "normal",
  });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const update = (ticket: Ticket, body: Record<string, unknown>) =>
    act(() =>
      api.patch(`/maintenance/${ticket.id}`, {
        ...body,
        note: notes[ticket.id] || null,
      }),
    );
  return (
    <>
      <Heading
        eyebrow="SỬA CHỮA & BẢO TRÌ"
        title={
          side === "landlord"
            ? "Yêu cầu sửa chữa"
            : "Báo hỏng & theo dõi sửa chữa"
        }
        text={
          side === "landlord"
            ? "Tiếp nhận, phân công kỹ thuật, ghi chi phí và cập nhật tiến độ; khách xác nhận hoàn tất hoặc mở lại."
            : "Chỉ người đang thuê phòng mới gửi được yêu cầu. Trường hợp khẩn, chọn mức Khẩn để chủ nhà nhận thông báo ngay."
        }
      />
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {side === "renter" && (
        <form
          className="panel inline-form"
          aria-label="Báo hỏng"
          onSubmit={(e) => {
            e.preventDefault();
            void act(() => api.post("/maintenance", form));
          }}
        >
          <label>
            Phòng
            <select
              required
              value={form.room_id}
              onChange={(e) => setForm({ ...form, room_id: e.target.value })}
            >
              <option value="">Chọn phòng đang thuê</option>
              {data.leases.map((lease) => (
                <option key={lease.id} value={lease.room_id}>
                  {lease.room_id}
                </option>
              ))}
            </select>
          </label>
          <label>
            Vấn đề
            <input
              required
              minLength={3}
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
            />
          </label>
          <label>
            Mô tả
            <input
              required
              minLength={3}
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
            />
          </label>
          <label>
            Mức độ
            <select
              value={form.priority}
              onChange={(e) => setForm({ ...form, priority: e.target.value })}
            >
              <option value="low">Thấp</option>
              <option value="normal">Bình thường</option>
              <option value="urgent">Khẩn</option>
            </select>
          </label>
          <button className="button">Gửi yêu cầu</button>
        </form>
      )}
      <section className="panel">
        {!data.tickets.length ? (
          <EmptyState
            title="Chưa có yêu cầu"
            description="Yêu cầu sửa chữa xuất hiện tại đây."
            icon="refresh"
          />
        ) : (
          data.tickets.map((ticket) => (
            <article key={ticket.id} className="lead-card">
              <strong>
                {ticket.priority === "urgent" ? "KHẨN · " : ""}
                {ticket.title} · {ticket.room_id}
              </strong>
              <span>{ticket.description}</span>
              <span>
                {ticketStatus[ticket.status] || ticket.status}
                {ticket.assignee ? ` · ${ticket.assignee}` : ""}
                {ticket.cost_vnd != null
                  ? ` · chi phí ${money(ticket.cost_vnd)}`
                  : ""}
              </span>
              <details>
                <summary>Lịch sử ({ticket.timeline.length})</summary>
                {ticket.timeline.map((entry, index) => (
                  <p key={index}>
                    {entry.at.slice(0, 16).replace("T", " ")} · {entry.by} ·{" "}
                    {ticketStatus[entry.status] || entry.status}
                    {entry.note ? ` · ${entry.note}` : ""}
                  </p>
                ))}
              </details>
              <div className="inline-form">
                <label>
                  Ghi chú
                  <input
                    value={notes[ticket.id] || ""}
                    onChange={(e) =>
                      setNotes({ ...notes, [ticket.id]: e.target.value })
                    }
                  />
                </label>
                {side === "landlord" &&
                  ["submitted", "reopened"].includes(ticket.status) && (
                    <button
                      className="button small"
                      onClick={() =>
                        void update(ticket, {
                          status: "assigned",
                          assignee: notes[ticket.id] || "Kỹ thuật",
                        })
                      }
                    >
                      Phân công
                    </button>
                  )}
                {side === "landlord" &&
                  ["submitted", "assigned", "reopened"].includes(
                    ticket.status,
                  ) && (
                    <button
                      className="button small outline"
                      onClick={() =>
                        void update(ticket, { status: "in_progress" })
                      }
                    >
                      Bắt đầu xử lý
                    </button>
                  )}
                {side === "landlord" &&
                  ["submitted", "assigned", "in_progress", "reopened"].includes(
                    ticket.status,
                  ) && (
                    <button
                      className="button small outline"
                      onClick={() =>
                        void update(ticket, { status: "resolved" })
                      }
                    >
                      Đã xử lý
                    </button>
                  )}
                {side === "renter" && ticket.status === "resolved" && (
                  <>
                    <button
                      className="button small"
                      onClick={() => void update(ticket, { status: "closed" })}
                    >
                      Xác nhận xong
                    </button>
                    <button
                      className="button small outline"
                      onClick={() =>
                        void update(ticket, { status: "reopened" })
                      }
                    >
                      Mở lại (cần ghi chú)
                    </button>
                  </>
                )}
              </div>
            </article>
          ))
        )}
      </section>
    </>
  );
}
// ------------------------------------------------------------ CRM leads
export function LeadsPage({ api }: { api: Api }) {
  const load = useCallback(() => api.get<Lead[]>("/landlord/leads"), [api]);
  const { data, error, setError, act } = useLoad(load, [] as Lead[]);
  return (
    <>
      <Heading
        eyebrow="CRM KHÁCH HÀNG"
        title="Khách tiềm năng"
        text="Tự cập nhật từ lượt xem tin, chat, yêu cầu xem và hợp đồng. Mức quan tâm theo điểm tương tác; bạn có thể chuyển giai đoạn và ghi chú."
      />
      <ErrorNotice error={error} onClose={() => setError(null)} />
      <div className="pipeline">
        {Object.entries(stageLabels).map(([stage, label]) => (
          <section key={stage} className="pipeline-column" aria-label={label}>
            <strong>
              {label} ({data.filter((lead) => lead.stage === stage).length})
            </strong>
            {data
              .filter((lead) => lead.stage === stage)
              .map((lead) => (
                <article key={lead.id} className="lead-card">
                  <strong>{lead.renter_id}</strong>
                  <span>Phòng {lead.room_id}</span>
                  <span className={`interest-${lead.interest}`}>
                    {interestLabels[lead.interest]} · {lead.score} điểm
                  </span>
                  {lead.notes && <small>{lead.notes}</small>}
                  <select
                    aria-label={`Giai đoạn ${lead.renter_id}`}
                    value={lead.stage}
                    onChange={(e) =>
                      void act(() =>
                        api.patch(`/landlord/leads/${lead.id}`, {
                          stage: e.target.value,
                        }),
                      )
                    }
                  >
                    {Object.entries(stageLabels).map(([value, text]) => (
                      <option key={value} value={value}>
                        {text}
                      </option>
                    ))}
                  </select>
                </article>
              ))}
          </section>
        ))}
      </div>
    </>
  );
}
