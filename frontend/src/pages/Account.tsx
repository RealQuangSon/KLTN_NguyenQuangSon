import { useCallback, useEffect, useState } from "react";
import type { Api } from "../api";
import type { Actor } from "../types";
import { amenities, roleNames, roomTypeLabels } from "../types";
import { ErrorNotice, Icon } from "../components/Shared";
// Hồ sơ tài khoản: đồng ý ghi nhớ và memory sở thích (FR-22), phiên đăng nhập.
// Chỉ hiển thị dữ liệu máy chủ trả về; memory không chứa tiền hay thu nhập.
interface AccountProfile {
  id: string;
  display_name: string | null;
  email: string | null;
  consents: Record<string, boolean>;
}
interface MemoryState {
  consented: boolean;
  memory: {
    fields: Record<string, unknown>;
    source_session: string;
    updated_at: string;
  } | null;
}
interface SessionEntry {
  token_id: string;
  expires_at: number | string;
  revoked: boolean;
}
const memoryLabels: Record<string, string> = {
  city: "Thành phố",
  area: "Khu vực",
  room_type: "Loại chỗ ở",
  bedrooms: "Số phòng ngủ",
  preferences: "Tiện ích quan tâm",
  soft_description: "Mô tả ưu tiên",
};
const memoryValue = (field: string, value: unknown) => {
  if (field === "preferences" && Array.isArray(value))
    return value.map((id) => amenities[id] || id).join(", ");
  if (field === "room_type")
    return (
      roomTypeLabels[value as keyof typeof roomTypeLabels] || String(value)
    );
  return String(value);
};
export function AccountPage({
  actor,
  section,
  api,
}: {
  actor: Actor;
  section: "ho-so" | "bao-mat";
  api: Api;
}) {
  const isProfile = section === "ho-so";
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [memory, setMemory] = useState<MemoryState | null>(null);
  const [sessions, setSessions] = useState<SessionEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setError(null);
    try {
      if (isProfile) {
        const [p, m] = await Promise.all([
          api.get<AccountProfile>("/me/profile"),
          api.get<MemoryState>("/me/memory"),
        ]);
        setProfile(p);
        setMemory(m);
      } else {
        setSessions(await api.get<SessionEntry[]>("/me/sessions"));
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, [api, isProfile]);
  useEffect(() => {
    void load();
  }, [load]);
  const act = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      await load();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const remembered = memory?.memory
    ? Object.entries(memory.memory.fields).filter(
        ([, value]) =>
          value != null && !(Array.isArray(value) && value.length === 0),
      )
    : [];
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">TÀI KHOẢN</span>
          <h1>{isProfile ? "Hồ sơ của bạn" : "Bảo mật & phiên đăng nhập"}</h1>
          <p>
            {isProfile
              ? "Thông tin tài khoản và những gì trợ lý được phép ghi nhớ."
              : "Xem và thu hồi các phiên đăng nhập của bạn."}
          </p>
        </div>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      <section className="panel">
        <div className="account-facts">
          <div className="avatar">{isProfile ? "TK" : "BM"}</div>
          <div>
            <strong>{profile?.display_name || actor.id}</strong>
            <small>{roleNames[actor.role]}</small>
          </div>
        </div>
        {isProfile ? (
          <>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={Boolean(profile?.consents.remember_sessions)}
                disabled={busy || !profile}
                onChange={(e) =>
                  void act(() =>
                    api.patch("/me/profile", {
                      consents: { remember_sessions: e.target.checked },
                    }),
                  )
                }
              />
              Cho phép trợ lý ghi nhớ sở thích giữa các phiên
            </label>
            <p className="input-hint">
              Chỉ ghi nhớ khu vực, loại chỗ ở, tiện ích và mô tả ưu tiên bạn đã
              xác nhận. Không ghi nhớ ngân sách, thu nhập, khoản vay hay nội
              dung chat. Phiên sau chỉ điền sẵn dạng “đã suy luận”, bạn vẫn phải
              xác nhận lại. Tắt tùy chọn này sẽ xóa dữ liệu đã ghi nhớ.
            </p>
            {memory?.consented && (
              <>
                <h2>Đang ghi nhớ</h2>
                {remembered.length === 0 ? (
                  <p className="subtle">
                    Chưa có gì. Sở thích sẽ được ghi nhớ sau lần xác nhận hồ sơ
                    tiếp theo.
                  </p>
                ) : (
                  <ul className="memory-list">
                    {remembered.map(([field, value]) => (
                      <li key={field}>
                        <span>
                          <strong>{memoryLabels[field] || field}:</strong>{" "}
                          {memoryValue(field, value)}
                        </span>
                        <button
                          className="text-button"
                          disabled={busy}
                          onClick={() =>
                            void act(() => api.delete(`/me/memory/${field}`))
                          }
                        >
                          Xóa
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {remembered.length > 0 && (
                  <button
                    className="button outline small"
                    disabled={busy}
                    onClick={() => void act(() => api.delete("/me/memory"))}
                  >
                    Xóa toàn bộ ghi nhớ
                  </button>
                )}
              </>
            )}
          </>
        ) : (
          <ul className="memory-list">
            {sessions.map((entry) => (
              <li key={entry.token_id}>
                <span>
                  Phiên {entry.token_id.slice(0, 8)} ·{" "}
                  {entry.revoked ? "đã thu hồi" : "đang hiệu lực"}
                </span>
                {!entry.revoked && (
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() =>
                      void act(() =>
                        api.delete(`/me/sessions/${entry.token_id}`),
                      )
                    }
                  >
                    Thu hồi
                  </button>
                )}
              </li>
            ))}
            {sessions.length === 0 && !error && (
              <li>
                <span className="subtle">
                  <Icon name="shield" size={15} /> Chưa đọc được phiên nào.
                </span>
              </li>
            )}
          </ul>
        )}
      </section>
    </>
  );
}
