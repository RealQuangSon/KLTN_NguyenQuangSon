import { useEffect, useRef, useState } from "react";
import { Api, mutationKey } from "../api";
import type { Candidate, Viewing } from "../types";
import { Badge, EmptyState, ErrorNotice, Icon, roomTitle } from "./Shared";
export function ViewingForm({
  room,
  sessionId,
  api,
  onDone,
  onCancel,
}: {
  room: Pick<Candidate, "room_id" | "title" | "area">;
  // Null when booking straight from a published listing (filter search).
  sessionId: string | null;
  api: Api;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [time, setTime] = useState("");
  const [mode, setMode] = useState<"offline" | "online">("offline");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState<{ time: string; key: string } | null>(
    null,
  );
  const modal = useRef<HTMLElement>(null);
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
          Chủ nhà của phòng sẽ phản hồi. Gửi yêu cầu chưa có nghĩa lịch đã được
          xác nhận.
        </p>
        <ErrorNotice error={error} />
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            if (busy) return;
            const date = new Date(time);
            if (
              !time ||
              !Number.isFinite(date.getTime()) ||
              date <= new Date()
            ) {
              setError("Chọn thời điểm trong tương lai.");
              return;
            }
            setBusy(true);
            setError(null);
            const current =
              attempt?.time === `${time}|${mode}`
                ? attempt
                : { time: `${time}|${mode}`, key: mutationKey() };
            setAttempt(current);
            try {
              const base = {
                requested_at: date.toISOString(),
                idempotency_key: current.key,
                mode,
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
            Thời gian xem (giờ trên thiết bị của bạn)
            <input
              type="datetime-local"
              required
              value={time}
              onChange={(e) => setTime(e.target.value)}
              disabled={busy}
            />
          </label>
          <p className="input-hint">
            Múi giờ: {Intl.DateTimeFormat().resolvedOptions().timeZone}. Máy chủ
            nhận thời điểm UTC.
          </p>
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
export function ViewingList({
  items,
  manager = false,
  busy = false,
  onRespond,
}: {
  items: Viewing[];
  manager?: boolean;
  busy?: boolean;
  onRespond?: (id: string, status: "confirmed" | "declined") => void;
}) {
  if (!items.length)
    return (
      <EmptyState
        title="Chưa có yêu cầu xem phòng"
        description={
          manager
            ? "Yêu cầu xem các phòng của bạn sẽ xuất hiện tại đây."
            : "Sau khi nhận danh sách đã duyệt, bạn có thể đề xuất thời gian xem phòng."
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
        </article>
      ))}
    </div>
  );
}
