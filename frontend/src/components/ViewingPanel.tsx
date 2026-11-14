import { useEffect, useRef, useState } from "react";
import { Api, mutationKey } from "../api";
import type { Candidate, Viewing } from "../types";
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
function vnDate(offsetDays: number) {
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
  // crawl.md E-07: điền sẵn từ tài khoản khi có.
  defaultName?: string;
  defaultPhone?: string;
}) {
  const [date, setDate] = useState(() => vnDate(1));
  const [slot, setSlot] = useState<TimeSlot>("morning");
  const [mode, setMode] = useState<"offline" | "online">("offline");
  const [name, setName] = useState(defaultName);
  const [phone, setPhone] = useState(defaultPhone);
  const [consent, setConsent] = useState(false);
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
            // crawl.md E-07: ghép ngày + khung giờ thành requested_at múi giờ +07:00.
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
}: {
  items: Viewing[];
  manager?: boolean;
  busy?: boolean;
  onRespond?: (id: string, status: "confirmed" | "declined") => void;
  // crawl.md E-01/E-07: thao tác vòng đời mới cho hai phía.
  onAction?: (id: string, action: ViewingAction) => void;
  // Phản hồi sau khi xem: khách tự chọn điểm 1–5 và ghi chú (không gửi mặc định).
  onFeedback?: (id: string, rating: number, note: string) => void;
}) {
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
      {items.map((v) => (
        <article className="viewing-row" key={v.id}>
          <div className="date-icon">
            <Icon name="calendar" size={22} />
          </div>
          <div>
            <h3>Phòng {v.room_id}</h3>
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
            {!manager && v.lease_id && v.lease_visible && (
              <a href="/nguoi-thue/hop-dong">Xem hợp đồng</a>
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
          {/* crawl.md E-01.4: bên xử lý — đề xuất giờ khác, hoàn tất, vắng mặt. */}
          {manager && onAction && v.status === "confirmed" && (
            <div className="viewing-actions">
              <button
                className="button small outline"
                onClick={() => onAction?.(v.id, "propose")}
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
          {/* crawl.md E-01.3: người thuê — hủy, chấp nhận giờ mới, phản hồi. */}
          {!manager && (onAction || onFeedback) && (
            <>
              {v.status === "requested" && (
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
    </div>
  );
}
