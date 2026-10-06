import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api";
import type { Room } from "../types";
import { roleNames } from "../types";
import {
  EmptyState,
  ErrorNotice,
  Icon,
  money,
  roomTitle,
} from "../components/Shared";
// Admin Console: giám sát hội thoại AI (đã che PII, mỗi lần mở được ghi audit),
// đánh giá chuyển giao AI → chủ nhà, người dùng, kiểm duyệt tin và vận hành.
export type AdminSection =
  | "hoi-thoai"
  | "chuyen-giao"
  | "tai-khoan"
  | "tin-dang"
  | "van-hanh";
const titles: Record<AdminSection, [string, string]> = {
  "hoi-thoai": [
    "Giám sát hội thoại AI",
    "Lịch sử chat giữa trợ lý và người dùng, đã che số điện thoại, email, số tài khoản. Lưu tối đa 90 ngày; mỗi lần mở được ghi audit.",
  ],
  "chuyen-giao": [
    "Chuyển giao AI → chủ nhà",
    "Tỷ lệ phản hồi và thời gian phản hồi đầu tiên của từng chủ nhà sau khi khách chuyển sang live chat.",
  ],
  "tai-khoan": [
    "Người dùng & vai trò",
    "Vai trò do máy chủ cấp; trạng thái tài khoản.",
  ],
  "tin-dang": [
    "Kiểm duyệt tin đăng",
    "Toàn bộ tin của các chủ nhà; quản trị viên có thể ẩn tin sai hoặc vi phạm.",
  ],
  "van-hanh": [
    "Vận hành",
    "Số liệu tiến trình hiện tại và các bản gợi ý tạo lỗi cần khởi tạo lại.",
  ],
};
interface TranscriptRow {
  session_id: string;
  user_id: string;
  turns: number;
  started_at: string;
  last_at: string;
  flagged: number;
}
interface Turn {
  speaker: string;
  text: string;
  intent: string | null;
  agent: string | null;
  created_at: string;
}
interface HandoverReport {
  landlords: {
    landlord_id: string;
    conversations: number;
    answered: number;
    response_rate: number;
    median_response_minutes: number | null;
  }[];
}
interface UserRow {
  id: string;
  role: keyof typeof roleNames;
  status: string;
  display_name: string | null;
}
interface FailedRun {
  run_id: string;
  session_id: string;
  status: string;
}
const time = (value: string) =>
  new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
export function AdminWorkspace({
  api,
  section,
}: {
  api: Api;
  section: AdminSection;
}) {
  const [error, setError] = useState<string | null>(null);
  const [transcripts, setTranscripts] = useState<TranscriptRow[]>([]);
  const [turns, setTurns] = useState<{
    session_id: string;
    turns: Turn[];
  } | null>(null);
  const [handovers, setHandovers] = useState<HandoverReport | null>(null);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [failed, setFailed] = useState<FailedRun[]>([]);
  const load = useCallback(async () => {
    setError(null);
    try {
      if (section === "hoi-thoai")
        setTranscripts(await api.get("/admin/transcripts"));
      else if (section === "chuyen-giao")
        setHandovers(await api.get("/admin/handovers"));
      else if (section === "tai-khoan") setUsers(await api.get("/admin/users"));
      else if (section === "tin-dang")
        setRooms((await api.get<{ rooms: Room[] }>("/admin/rooms")).rooms);
      else {
        setMetrics(await api.get("/admin/metrics"));
        setFailed(await api.get("/admin/failed-runs"));
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, [api, section]);
  useEffect(() => {
    setTurns(null);
    void load();
  }, [load]);
  const act = async (action: () => Promise<unknown>) => {
    setError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const [title, description] = titles[section];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">ADMIN CONSOLE</span>
          <h1>{title}</h1>
          <p>{description}</p>
        </div>
        <button className="button outline small" onClick={() => void load()}>
          <Icon name="refresh" size={16} /> Đọc lại
        </button>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      {section === "hoi-thoai" && (
        <div className="inbox-layout">
          <section className="panel inbox-list" aria-label="Phiên chat">
            {transcripts.length === 0 && (
              <EmptyState
                title="Chưa có hội thoại"
                description="Hội thoại với trợ lý sẽ xuất hiện tại đây."
                icon="chat"
              />
            )}
            {transcripts.map((row) => (
              <button
                key={row.session_id}
                className={`queue-item ${turns?.session_id === row.session_id ? "active" : ""}`}
                onClick={() =>
                  void act(async () =>
                    setTurns(
                      await api.get(`/admin/transcripts/${row.session_id}`),
                    ),
                  )
                }
              >
                <div>
                  <strong>{row.user_id}</strong>
                  {row.flagged > 0 && (
                    <span className="badge">{row.flagged} bị chặn</span>
                  )}
                </div>
                <span>
                  {row.turns} lượt · {time(row.last_at)}
                </span>
              </button>
            ))}
          </section>
          <section
            className="panel inbox-thread"
            aria-label="Nội dung hội thoại"
          >
            {!turns ? (
              <EmptyState
                title="Chọn một phiên"
                description="Việc mở nội dung sẽ được ghi vào nhật ký kiểm toán."
                icon="shield"
              />
            ) : (
              <div className="message-list">
                {turns.turns.map((turn, index) => (
                  <div
                    key={index}
                    className={`chat-bubble ${turn.speaker === "user" ? "theirs" : "mine"}`}
                  >
                    <p>{turn.text}</p>
                    <small>
                      {turn.speaker === "user"
                        ? "Người dùng"
                        : `Trợ lý${turn.agent ? ` · ${turn.agent}` : ""}`}{" "}
                      · {time(turn.created_at)}
                    </small>
                  </div>
                ))}
              </div>
            )}
          </section>
        </div>
      )}
      {section === "chuyen-giao" && (
        <section className="panel">
          {!handovers?.landlords.length ? (
            <EmptyState
              title="Chưa có chuyển giao"
              description="Khi khách chuyển sang chat với chủ nhà, số liệu xuất hiện tại đây."
              icon="chat"
            />
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Chủ nhà</th>
                    <th>Cuộc trò chuyện</th>
                    <th>Đã phản hồi</th>
                    <th>Tỷ lệ phản hồi</th>
                    <th>Phản hồi đầu tiên (trung vị)</th>
                  </tr>
                </thead>
                <tbody>
                  {handovers.landlords.map((row) => (
                    <tr key={row.landlord_id}>
                      <td>{row.landlord_id}</td>
                      <td>{row.conversations}</td>
                      <td>{row.answered}</td>
                      <td>{Math.round(row.response_rate * 100)}%</td>
                      <td>
                        {row.median_response_minutes == null
                          ? "Chưa phản hồi"
                          : `${row.median_response_minutes} phút`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      )}
      {section === "tai-khoan" && (
        <section className="panel table-scroll">
          <table>
            <thead>
              <tr>
                <th>Tài khoản</th>
                <th>Vai trò</th>
                <th>Trạng thái</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id}>
                  <td>{user.display_name || user.id}</td>
                  <td>{roleNames[user.role] || user.role}</td>
                  <td>{user.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {section === "tin-dang" && (
        <section className="panel table-scroll">
          <table>
            <thead>
              <tr>
                <th>Tin</th>
                <th>Chủ nhà</th>
                <th>Giá thuê</th>
                <th>Công khai</th>
              </tr>
            </thead>
            <tbody>
              {rooms.map((room) => (
                <tr key={room.id}>
                  <td>
                    {roomTitle(room.title)}
                    <small>
                      {room.area} · {room.city}
                    </small>
                  </td>
                  <td>{room.landlord_id || "owner-a"}</td>
                  <td>{money(room.quote.rent_vnd)}</td>
                  <td>
                    <button
                      className="text-button"
                      aria-label={`${room.published ? "Ẩn" : "Hiện"} tin ${room.id}`}
                      onClick={() =>
                        void act(() =>
                          api.patch(`/admin/rooms/${room.id}/status`, {
                            expected_revision: room.revision,
                            published: !room.published,
                          }),
                        )
                      }
                    >
                      {room.published
                        ? "Đang hiện · Ẩn tin"
                        : "Đang ẩn · Hiện lại"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
      {section === "van-hanh" && (
        <section className="panel">
          <h2>Bản gợi ý tạo lỗi</h2>
          {failed.length === 0 ? (
            <p className="subtle">Không có bản gợi ý lỗi.</p>
          ) : (
            <ul className="memory-list">
              {failed.map((run) => (
                <li key={run.run_id}>
                  <span>
                    Phiên {run.session_id.slice(0, 8)} · {run.status}
                  </span>
                  <button
                    className="text-button"
                    onClick={() =>
                      void act(() =>
                        api.post(
                          `/landlord/recommendations/${run.run_id}/retry`,
                          {},
                        ),
                      )
                    }
                  >
                    Khởi tạo lại
                  </button>
                </li>
              ))}
            </ul>
          )}
          <h2>Số liệu tiến trình</h2>
          <pre className="metrics-dump">
            {metrics ? JSON.stringify(metrics, null, 2) : "—"}
          </pre>
        </section>
      )}
    </>
  );
}
