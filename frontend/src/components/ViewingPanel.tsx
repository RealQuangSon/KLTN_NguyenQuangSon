import { useEffect, useRef, useState } from "react";
import { Api, mutationKey } from "../api";
import type { Candidate, Viewing } from "../types";
import { Pager, usePager } from "./Pager";
export type ViewingAction =
  | "cancel"
  | "accept"
  | "choose_time"
  | "propose"
  | "confirm"
  | "decline"
  | "complete"
  | "no_show"
  | "feedback";
import { Badge, EmptyState, ErrorNotice, Icon, roomTitle } from "./Shared";
export type TimeSlot = "morning" | "afternoon" | "evening";
export const SLOT_TIMES: Record<TimeSlot, string> = {
  morning: "08:00",
  afternoon: "14:00",
  evening: "18:00",
};
const SLOT_LABELS: Record<TimeSlot, string> = {
  morning: "Sáng (8:00–12:00)",
  afternoon: "Chiều (12:00–17:00)",
  evening: "Tối (17:00–20:00)",
};
// Ngày theo giờ Việt Nam dạng YYYY-MM-DD, lệch `offsetDays` so với hôm nay.
// Cộng 7 giờ trước khi lấy phần ngày của ISO nên KHÔNG lệch UTC như
// `new Date().toISOString()` (A3: 02:00 sáng giờ VN vẫn là hôm nay, không phải hôm qua).
export function vnDate(offsetDays: number) {
  const base = new Date(Date.now() + 7 * 3600000 + offsetDays * 86400000);
  return base.toISOString().slice(0, 10);
}
export function ViewingForm({
  room,
  sessionId,
  api,
  onDone,
  onCancel,
  defaultName = "",
  defaultPhone = "",
}: {
  room: Pick<Candidate, "room_id" | "title" | "area">;
  // Null when booking straight from a published listing (filter search).
  sessionId: string | null;
  api: Api;
  onDone: () => void;
  onCancel: () => void;
  // Điền sẵn từ tài khoản khi có.
  defaultName?: string;
  defaultPhone?: string;
}) {
  const [date, setDate] = useState(() => vnDate(1));
  const [slot, setSlot] = useState<TimeSlot>("morning");
  const [mode, setMode] = useState<"offline" | "online">("offline");
  const [name, setName] = useState(defaultName);
  const [phone, setPhone] = useState(defaultPhone);
  const [consent, setConsent] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<{ time: string; key: string } | null>(
    null,
  );
  const modal = useRef<HTMLElement>(null);
  const touched = useRef({ name: false, phone: false });
  // Điền sẵn họ tên và số điện thoại từ tài khoản, không ghi đè phần đã gõ.
  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const profile = await api.get<{
          display_name?: string | null;
          contact_phone?: string | null;
        }>("/me/profile");
        if (!active) return;
        if (profile.display_name && !touched.current.name)
          setName((value) => value || profile.display_name || "");
        if (profile.contact_phone && !touched.current.phone)
          setPhone((value) => value || profile.contact_phone || "");
      } catch {
        /* không lấy được hồ sơ thì để người dùng tự điền */
      }
      // B5 (15/11): tài khoản chưa có hồ sơ (tài khoản seed) thì điền từ lần
      // đặt lịch gần nhất của CHÍNH người thuê — dữ liệu của họ qua GET
      // /viewings, không mở quyền hay dữ liệu mới nào.
      try {
        const items =
          await api.get<
            { contact_name?: string | null; contact_phone?: string | null }[]
          >("/viewings");
        if (!active) return;
        const previous = [...items]
          .reverse()
          .find((item) => item.contact_name || item.contact_phone);
        if (!previous) return;
        if (!touched.current.name)
          setName((value) => value || previous.contact_name || "");
        if (!touched.current.phone)
          setPhone((value) => value || previous.contact_phone || "");
      } catch {
        /* chưa có lịch cũ thì để trống */
      }
    })();
    return () => {
      active = false;
    };
  }, [api]);
  const close = useRef(onCancel);
  const submitting = useRef(busy);
  close.current = onCancel;
  submitting.current = busy;
  useEffect(() => {
    const panel = modal.current;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel?.querySelector<HTMLInputElement>("input")?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!submitting.current) close.current();
      }
      if (event.key !== "Tab" || !panel) return;
      const targets = [
        ...panel.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input:not(:disabled), [tabindex='0']",
        ),
      ];
      const first = targets[0];
      const last = targets[targets.length - 1];
      if (!first) {
        event.preventDefault();
        panel.focus();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    panel?.addEventListener("keydown", onKeyDown);
    return () => {
      panel?.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = overflow;
      if (previous?.isConnected) previous.focus();
    };
  }, []);
  return (
    <div className="modal-backdrop">
      <section
        className="panel modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="view-title"
        ref={modal}
        tabIndex={-1}
      >
        <button
          type="button"
          className="icon-button modal-close"
          aria-label="Đóng lịch xem"
          onClick={onCancel}
          disabled={busy}
        >
          <Icon name="close" size={19} />
        </button>
        <span className="eyebrow">LỊCH XEM PHÒNG</span>
        <h2 id="view-title">Gửi thời gian bạn muốn xem</h2>
        <p>
          {roomTitle(room.title)} · {room.area}
        </p>
        <p className="subtle">
          Đây là thời gian MONG MUỐN của bạn, chưa phải lịch đã chốt. Yêu cầu sẽ
          được chuyển cho người phụ trách tin (chủ nhà, hoặc bộ phận điều phối
          của HomeMatch với tin lấy từ tin đăng gốc).
        </p>
        <ErrorNotice error={error} />
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy) return;
            // Ghép ngày + khung giờ thành requested_at múi giờ +07:00.
            if (!date) {
              setError("Chọn ngày muốn xem.");
              return;
            }
            if (!name.trim() || !phone.trim()) {
              setError(
                "Điền họ tên và số điện thoại để bên phụ trách liên hệ.",
              );
              return;
            }
            if (!consent) {
              setError("Cần đồng ý chia sẻ thông tin liên hệ.");
              return;
            }
            const requestedAt = new Date(
              `${date}T${SLOT_TIMES[slot]}:00+07:00`,
            );
            if (
              !Number.isFinite(requestedAt.getTime()) ||
              requestedAt <= new Date()
            ) {
              setError("Chọn ngày trong tương lai.");
              return;
            }
            setBusy(true);
            setError(null);
            const stamp = `${date}|${slot}|${mode}`;
            const current =
              attempt?.time === stamp
                ? attempt
                : { time: stamp, key: mutationKey() };
            setAttempt(current);
            try {
              const base = {
                requested_at: requestedAt.toISOString(),
                idempotency_key: current.key,
                mode,
                contact_name: name.trim(),
                contact_phone: phone.trim(),
                contact_consent: true,
                time_slot: slot,
                // Ghi chú là tùy chọn; để trống thì không gửi trường này.
                ...(note.trim() ? { note: note.trim() } : {}),
              };
              await (sessionId
                ? api.post(`/sessions/${sessionId}/viewings`, {
                    ...base,
                    room_id: room.room_id,
                  })
                : api.post(`/listings/${room.room_id}/viewings`, base));
              onDone();
            } catch (err) {
              setError(
                err instanceof Error ? err.message : "Chưa gửi được yêu cầu.",
              );
            } finally {
              setBusy(false);
            }
          }}
        >
          <label>
            Ngày muốn xem
            <input
              type="date"
              required
              value={date}
              min={vnDate(0)}
              onChange={(e) => setDate(e.target.value)}
              disabled={busy}
            />
          </label>
          <fieldset>
            <legend>Khung giờ mong muốn (giờ Việt Nam)</legend>
            {(Object.keys(SLOT_LABELS) as TimeSlot[]).map((key) => (
              <label className="checkbox-line" key={key}>
                <input
                  type="radio"
                  name="viewing-slot"
                  checked={slot === key}
                  onChange={() => setSlot(key)}
                  disabled={busy}
                />
                {SLOT_LABELS[key]}
              </label>
            ))}
          </fieldset>
          <label>
            Họ tên
            <input
              required
              minLength={2}
              maxLength={80}
              value={name}
              onChange={(e) => {
                touched.current.name = true;
                setName(e.target.value);
              }}
              disabled={busy}
            />
          </label>
          <label>
            Số điện thoại
            <input
              required
              type="tel"
              inputMode="tel"
              value={phone}
              onChange={(e) => {
                touched.current.phone = true;
                setPhone(e.target.value);
              }}
              disabled={busy}
            />
          </label>
          <label className="checkbox-line">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              disabled={busy}
            />
            Tôi đồng ý để HomeMatch chia sẻ tên và số điện thoại này cho bên phụ
            trách tin để xác nhận lịch xem.
          </label>
          <fieldset>
            <legend>Hình thức xem</legend>
            <label className="checkbox-line">
              <input
                type="radio"
                name="viewing-mode"
                checked={mode === "offline"}
                onChange={() => setMode("offline")}
                disabled={busy}
              />
              Xem trực tiếp tại phòng
            </label>
            <label className="checkbox-line">
              <input
                type="radio"
                name="viewing-mode"
                checked={mode === "online"}
                onChange={() => setMode("online")}
                disabled={busy}
              />
              Xem trực tuyến (gọi video, có link phòng họp)
            </label>
          </fieldset>
          <label>
            Ghi chú cho bên phụ trách tin (không bắt buộc)
            <textarea
              rows={2}
              maxLength={300}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="VD: mình đi cùng một người bạn, muốn hỏi thêm về chỗ để xe"
              disabled={busy}
            />
          </label>
          <div className="viewing-tips">
            <strong>Lưu ý khi đi xem</strong>
            <ul>
              <li>Đến đúng khung giờ sau khi lịch được xác nhận.</li>
              <li>
                Bận đột xuất thì bấm "Hủy lịch" trong mục Lịch xem của tôi để
                bên phụ trách tin biết sớm.
              </li>
              <li>
                Chưa chuyển tiền hay đặt cọc trước khi trực tiếp xem phòng.
              </li>
            </ul>
          </div>
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
              <Icon name="calendar" size={16} />
              {busy
                ? "Đang gửi…"
                : error
                  ? "Thử gửi lại cùng yêu cầu"
                  : "Gửi yêu cầu xem"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
// A3 (15/11): form đề xuất giờ khác của bên xử lý (chủ nhà/điều phối), dùng
// chung quy ước ngày + khung giờ với form đặt lịch của khách. Bấm nút "Đề xuất
// giờ khác" chỉ MỞ form này; gọi API xảy ra khi bấm "Gửi đề xuất".
export function ProposeTimeForm({
  busy,
  onSubmit,
  onCancel,
}: {
  busy: boolean;
  // proposed_at là ISO UTC dựng từ ngày + khung giờ theo múi giờ +07:00.
  onSubmit: (proposed_at: string, reason: string) => void;
  onCancel: () => void;
}) {
  // Ngày mặc định: ngày mai tính theo giờ Việt Nam, không dùng ngày UTC.
  const [date, setDate] = useState(() => vnDate(1));
  const [slot, setSlot] = useState<TimeSlot>("morning");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="propose-form"
      onSubmit={(event) => {
        event.preventDefault();
        if (busy) return;
        if (!date) {
          setError("Chọn ngày đề xuất.");
          return;
        }
        const proposedAt = new Date(`${date}T${SLOT_TIMES[slot]}:00+07:00`);
        if (
          !Number.isFinite(proposedAt.getTime()) ||
          proposedAt <= new Date()
        ) {
          setError("Chọn thời điểm trong tương lai.");
          return;
        }
        setError(null);
        onSubmit(proposedAt.toISOString(), reason.trim());
      }}
    >
      <label>
        Ngày đề xuất
        <input
          type="date"
          required
          value={date}
          min={vnDate(0)}
          onChange={(e) => setDate(e.target.value)}
          disabled={busy}
        />
      </label>
      <fieldset>
        <legend>Khung giờ đề xuất (giờ Việt Nam)</legend>
        {(Object.keys(SLOT_LABELS) as TimeSlot[]).map((key) => (
          <label className="checkbox-line" key={key}>
            <input
              type="radio"
              name="propose-slot"
              checked={slot === key}
              onChange={() => setSlot(key)}
              disabled={busy}
            />
            {SLOT_LABELS[key]}
          </label>
        ))}
      </fieldset>
      <label>
        Lý do (không bắt buộc)
        <input
          value={reason}
          maxLength={200}
          placeholder="VD: Phòng đang dọn dẹp, mong gặp bạn buổi khác"
          onChange={(e) => setReason(e.target.value)}
          disabled={busy}
        />
      </label>
      {error && (
        <p className="notice warning" role="status">
          {error}
        </p>
      )}
      <div className="viewing-actions">
        <button
          type="button"
          className="button small outline"
          onClick={onCancel}
          disabled={busy}
        >
          Hủy
        </button>
        <button type="submit" className="button small" disabled={busy}>
          Gửi đề xuất
        </button>
      </div>
    </form>
  );
}
function FeedbackForm({
  busy,
  onSubmit,
}: {
  busy: boolean;
  onSubmit: (rating: number, note: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState<number | null>(null);
  const [note, setNote] = useState("");
  if (!open)
    return (
      <div className="viewing-actions">
        <button
          className="button small outline"
          onClick={() => setOpen(true)}
          disabled={busy}
        >
          Gửi phản hồi
        </button>
      </div>
    );
  return (
    <form
      className="viewing-feedback"
      onSubmit={(event) => {
        event.preventDefault();
        if (rating != null) onSubmit(rating, note.trim());
      }}
    >
      <fieldset>
        <legend>Bạn đánh giá buổi xem thế nào?</legend>
        {[1, 2, 3, 4, 5].map((value) => (
          <label key={value}>
            <input
              type="radio"
              name="viewing-rating"
              checked={rating === value}
              onChange={() => setRating(value)}
            />{" "}
            {value}
          </label>
        ))}
      </fieldset>
      <label>
        Ghi chú (không bắt buộc)
        <textarea
          value={note}
          maxLength={500}
          onChange={(event) => setNote(event.target.value)}
        />
      </label>
      <div className="viewing-actions">
        <button
          type="button"
          className="button small outline"
          onClick={() => setOpen(false)}
        >
          Để sau
        </button>
        <button
          type="submit"
          className="button small"
          disabled={busy || rating == null}
        >
          Gửi đánh giá
        </button>
      </div>
    </form>
  );
}
export function ViewingList({
  items,
  manager = false,
  busy = false,
  onRespond,
  onAction,
  onFeedback,
  onPropose,
}: {
  items: Viewing[];
  manager?: boolean;
  busy?: boolean;
  onRespond?: (id: string, status: "confirmed" | "declined") => void;
  // Thao tác vòng đời mới cho hai phía.
  onAction?: (id: string, action: ViewingAction) => void;
  // Phản hồi sau khi xem: khách tự chọn điểm 1–5 và ghi chú (không gửi mặc định).
  onFeedback?: (id: string, rating: number, note: string) => void;
  // A3 (15/11): đề xuất giờ khác CHỈ mở form; API gọi khi bấm "Gửi đề xuất".
  onPropose?: (id: string, proposed_at: string, reason: string) => void;
}) {
  // Lịch đang mở form đề xuất giờ (mỗi lần một lịch).
  const [proposeFor, setProposeFor] = useState<string | null>(null);
  // Lịch rời trạng thái "đã xác nhận" (đã gửi đề xuất, hủy…) thì bỏ chọn, để
  // form không tự bật lại khi khách đồng ý và lịch quay về "đã xác nhận".
  const proposeStillOpen = items.some(
    (item) =>
      item.id === proposeFor &&
      (item.status === "requested" || item.status === "confirmed"),
  );
  useEffect(() => {
    if (proposeFor && !proposeStillOpen) setProposeFor(null);
  }, [proposeFor, proposeStillOpen]);
  const paged = usePager(items);
  if (!items.length)
    return (
      <EmptyState
        title="Chưa có yêu cầu xem phòng"
        description={
          manager
            ? "Yêu cầu xem các phòng của bạn sẽ xuất hiện tại đây."
            : "Sau khi có danh sách gợi ý, bạn có thể đề xuất thời gian xem phòng."
        }
        icon="calendar"
      />
    );
  return (
    <div className="viewing-list">
      {paged.items.map((v) => (
        <article className="viewing-row" key={v.id}>
          <div className="date-icon">
            <Icon name="calendar" size={22} />
          </div>
          <div>
            {/* B1 (15/11): hiện tên phòng; chỉ dùng mã khi máy chủ không trả tên. */}
            <h3>
              {v.room_title ? roomTitle(v.room_title) : `Phòng ${v.room_id}`}
            </h3>
            <p>
              {new Intl.DateTimeFormat("vi-VN", {
                dateStyle: "medium",
                timeStyle: "short",
              }).format(new Date(v.requested_at))}
              {v.time_slot
                ? ` · ${{ morning: "Sáng", afternoon: "Chiều", evening: "Tối" }[v.time_slot]}`
                : ""}
            </p>
            <small>
              {v.mode === "online" ? "Xem trực tuyến" : "Xem trực tiếp"} ·{" "}
              {v.session_id
                ? `Phiên ${v.session_id.slice(0, 8)}`
                : "Đặt từ tin đăng"}{" "}
              · giờ {Intl.DateTimeFormat().resolvedOptions().timeZone}
            </small>
            {v.mode === "online" &&
              v.meeting_url &&
              v.status === "confirmed" && (
                <a href={v.meeting_url} target="_blank" rel="noreferrer">
                  Vào phòng xem trực tuyến
                </a>
              )}
            {v.status === "reschedule_proposed" && v.proposed_at && (
              <small>
                Giờ đề xuất mới:{" "}
                {new Intl.DateTimeFormat("vi-VN", {
                  dateStyle: "medium",
                  timeStyle: "short",
                }).format(new Date(v.proposed_at))}
              </small>
            )}
            {/* Ghi chú của khách hiện cho cả hai bên (máy chủ trả theo quyền). */}
            {v.note && (
              <small>
                {manager ? "Khách ghi" : "Ghi chú của bạn"}: {v.note}
              </small>
            )}
            {!manager && v.contact_shared && v.status !== "requested" && (
              <small>
                Liên hệ đã chia sẻ: {v.contact_name} · {v.contact_phone}
              </small>
            )}
            {!manager &&
              v.handler === "concierge" &&
              v.status === "requested" && (
                <small>
                  HomeMatch sẽ liên hệ người đăng để xác nhận; đây chưa phải
                  lịch đã chốt.
                </small>
              )}
            {!manager &&
              v.handler === "concierge" &&
              v.status === "completed" && (
                <small>
                  Tin lấy từ tin đăng gốc: hợp đồng ký trực tiếp với người đăng,
                  ngoài hệ thống HomeMatch.
                </small>
              )}
            {!manager && v.lease_id && v.lease_visible && (
              // B2 (15/11): dùng kiểu nút/link của hệ thống thay vì link trần
              // dính liền dòng "Liên hệ đã chia sẻ".
              <div className="viewing-actions">
                <a className="button small outline" href="/nguoi-thue/hop-dong">
                  Xem hợp đồng
                </a>
              </div>
            )}
          </div>
          <Badge status={v.status} />
          {manager && v.status === "requested" && (
            <div className="viewing-actions">
              <button
                className="button small"
                onClick={() => onRespond?.(v.id, "confirmed")}
                disabled={busy}
              >
                Xác nhận
              </button>
              <button
                className="button small outline"
                onClick={() => onRespond?.(v.id, "declined")}
                disabled={busy}
              >
                Từ chối
              </button>
              {/* Máy chủ cho bên xử lý đề xuất giờ khác ngay từ yêu cầu mới
                  (requested → reschedule_proposed), không buộc xác nhận trước. */}
              {onPropose && (
                <button
                  className="button small outline"
                  aria-expanded={proposeFor === v.id}
                  onClick={() =>
                    setProposeFor(proposeFor === v.id ? null : v.id)
                  }
                  disabled={busy}
                >
                  Đề xuất giờ khác
                </button>
              )}
            </div>
          )}
          {/* Chủ nhà thấy liên hệ khách từ lúc lịch đã xác nhận (máy chủ chỉ trả khi được phép). */}
          {manager && v.contact_name && (
            <small>
              Liên hệ khách: {v.contact_name}
              {v.contact_phone ? ` · ${v.contact_phone}` : ""}
            </small>
          )}
          {/* E-08: lịch đã xem xong của tin chủ nhà → soạn hợp đồng, không gõ mã tài khoản. */}
          {manager &&
            v.status === "completed" &&
            v.handler !== "concierge" &&
            (v.lease_id ? (
              <div className="viewing-actions">
                <a className="button small outline" href="/chu-nha/hop-dong">
                  Xem hợp đồng
                </a>
              </div>
            ) : (
              <div className="viewing-actions">
                <a
                  className="button small"
                  href={`/chu-nha/hop-dong?viewing=${encodeURIComponent(v.id)}&room=${encodeURIComponent(v.room_id)}`}
                >
                  Tạo hợp đồng
                </a>
              </div>
            ))}
          {/* Bên xử lý — đề xuất giờ khác, hoàn tất, vắng mặt. */}
          {manager && onAction && v.status === "confirmed" && (
            <div className="viewing-actions">
              <button
                className="button small outline"
                aria-expanded={proposeFor === v.id}
                onClick={() =>
                  // A3: bấm chỉ mở form chọn ngày + khung giờ, chưa gọi API.
                  setProposeFor(proposeFor === v.id ? null : v.id)
                }
                disabled={busy}
              >
                Đề xuất giờ khác
              </button>
              <button
                className="button small"
                onClick={() => onAction?.(v.id, "complete")}
                disabled={busy}
              >
                Hoàn tất
              </button>
              <button
                className="button small outline"
                onClick={() => onAction?.(v.id, "no_show")}
                disabled={busy}
              >
                Không có khách
              </button>
            </div>
          )}
          {/* A3: form đề xuất giờ nằm dưới thẻ lịch, rộng hết chiều ngang. */}
          {manager &&
            onPropose &&
            proposeFor === v.id &&
            (v.status === "requested" || v.status === "confirmed") && (
              <ProposeTimeForm
                busy={busy}
                onCancel={() => setProposeFor(null)}
                onSubmit={(proposedAt, reason) =>
                  onPropose(v.id, proposedAt, reason)
                }
              />
            )}
          {/* Người thuê — hủy, chấp nhận giờ mới, phản hồi. */}
          {!manager && (onAction || onFeedback) && (
            <>
              {/* Máy chủ cho người thuê hủy cả lịch đã xác nhận (confirmed →
                  cancelled); thiếu nút thì khách bận đột xuất không có lối ra. */}
              {(v.status === "requested" || v.status === "confirmed") && (
                <div className="viewing-actions">
                  <button
                    className="button small outline"
                    onClick={() => onAction?.(v.id, "cancel")}
                    disabled={busy}
                  >
                    Hủy lịch
                  </button>
                </div>
              )}
              {v.status === "reschedule_proposed" && (
                <div className="viewing-actions">
                  <button
                    className="button small"
                    onClick={() => onAction?.(v.id, "accept")}
                    disabled={busy}
                  >
                    Đồng ý giờ mới
                  </button>
                  <button
                    className="button small outline"
                    onClick={() => onAction?.(v.id, "choose_time")}
                    disabled={busy}
                  >
                    Chọn giờ khác
                  </button>
                  <button
                    className="button small outline"
                    onClick={() => onAction?.(v.id, "cancel")}
                    disabled={busy}
                  >
                    Hủy lịch
                  </button>
                </div>
              )}
              {v.status === "completed" && v.feedback_rating == null && (
                <FeedbackForm
                  busy={busy}
                  onSubmit={(rating, note) =>
                    onFeedback
                      ? onFeedback(v.id, rating, note)
                      : onAction?.(v.id, "feedback")
                  }
                />
              )}
              {v.status === "completed" && v.feedback_rating != null && (
                <small>
                  Bạn đã đánh giá {v.feedback_rating}/5
                  {v.feedback_note ? `: ${v.feedback_note}` : ""}
                </small>
              )}
            </>
          )}
        </article>
      ))}
      <Pager unit="lịch" {...paged.pagerProps} />
    </div>
  );
}
