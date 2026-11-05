import { useEffect, useState } from "react";
import { Api } from "../api";
import type { Actor } from "../types";
// Trải nghiệm đăng nhập nhanh bằng tài khoản seed, chỉ tồn tại ở môi trường
// demo local: GET /health phải báo auth_mode=seed và public=false. Khi triển
// khai public, mật khẩu seed bị quay nên backend từ chối và nhánh UI này tự
// ẩn — không có lối vào nào cho bản chạy thật.
export type ExperienceKind = "renter" | "owner";
type DemoAccount = { username: string; hint: string };
// Phân thành phố theo bảng tài khoản local trong README.
const demoAccounts: Record<ExperienceKind, DemoAccount[]> = {
  renter: [
    { username: "renter-a", hint: "tài khoản mẫu, có kịch bản demo" },
    { username: "renter-b", hint: "tài khoản mẫu" },
  ],
  owner: [
    { username: "owner-a", hint: "TP.HCM · có kịch bản demo" },
    { username: "owner-b", hint: "TP.HCM" },
    { username: "owner-c", hint: "Hà Nội" },
    { username: "owner-d", hint: "Hà Nội" },
  ],
};
const primaryAccount: Record<ExperienceKind, string> = {
  renter: "renter-a",
  owner: "owner-a",
};
export function useDemoExperience(): boolean {
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    let active = true;
    new Api(null)
      .get<{ auth_mode?: string; public?: boolean }>("/health")
      .then((health) => {
        // Backend cũ không có trường public => coi như không khả dụng.
        if (active)
          setAvailable(health?.auth_mode === "seed" && health.public === false);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return available;
}
// Auto-publish: phòng tự công bố không chờ duyệt (môi trường demo). Chỉ dùng
// để đổi vài dòng copy trạng thái chờ — bật/tắt do máy chủ quyết định.
export function useAutoPublish(): boolean {
  const [autoPublish, setAutoPublish] = useState(false);
  useEffect(() => {
    let active = true;
    new Api(null)
      .get<{ auto_publish?: boolean }>("/health")
      .then((health) => {
        if (active) setAutoPublish(health?.auto_publish === true);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  return autoPublish;
}
export async function quickExperienceLogin(
  username: string,
): Promise<{ access_token: string; actor: Actor }> {
  // Mật khẩu seed local theo convention `local-<username>-password` (README,
  // backend.manage seed-users); sai lệch thì backend trả invalid_credentials.
  return new Api(null).post("/auth/login", {
    username,
    password: `local-${username}-password`,
  });
}
// Nhóm chip trên trang đăng nhập: bấm một tài khoản seed là vào ngay trải
// nghiệm của vai trò đang chọn, không cần gõ tên đăng nhập hay mật khẩu.
export function ExperienceChips({
  kind,
  disabled,
  onAuthenticated,
  onError,
}: {
  kind: ExperienceKind;
  disabled?: boolean;
  onAuthenticated: (token: string, actor: Actor) => void;
  onError: (message: string) => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const enter = async (username: string) => {
    if (busy || disabled) return;
    setBusy(username);
    onError("");
    try {
      const result = await quickExperienceLogin(username);
      onAuthenticated(result.access_token, result.actor);
    } catch (err) {
      onError(
        err instanceof Error ? err.message : "Chưa đăng nhập nhanh được.",
      );
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="auth-quick">
      <small className="auth-quick-title">
        Trải nghiệm nhanh (môi trường demo) — chọn tài khoản để vào ngay:
      </small>
      <div className="auth-quick-list">
        {demoAccounts[kind].map((account) => (
          <button
            key={account.username}
            type="button"
            className="auth-quick-chip"
            onClick={() => void enter(account.username)}
            disabled={disabled || busy !== null}
          >
            <strong>
              {busy === account.username
                ? `Đang vào ${account.username}…`
                : account.username}
            </strong>
            {account.hint && <small>{account.hint}</small>}
          </button>
        ))}
      </div>
    </div>
  );
}
// Hai lựa chọn trong khối tài khoản trên sidebar: người đã đăng nhập chuyển
// thẳng sang trải nghiệm người thuê hoặc chủ nhà (phiên hiện tại bị thay thế).
// Tự gọi useDemoExperience để AppShell không phải probe /health trên mọi
// route — trang đăng ký public phải giữ bất biến "không network call".
export function ExperienceSwitch({
  onAuthenticated,
}: {
  onAuthenticated: (token: string, actor: Actor) => void;
}) {
  const demoReady = useDemoExperience();
  const [busy, setBusy] = useState<ExperienceKind | null>(null),
    [localError, setLocalError] = useState<string | null>(null);
  if (!demoReady) return null;
  const enter = async (kind: ExperienceKind) => {
    if (busy) return;
    setBusy(kind);
    setLocalError(null);
    try {
      const result = await quickExperienceLogin(primaryAccount[kind]);
      onAuthenticated(result.access_token, result.actor);
    } catch (err) {
      setLocalError(
        err instanceof Error ? err.message : "Chưa chuyển được trải nghiệm.",
      );
    } finally {
      setBusy(null);
    }
  };
  return (
    <div className="account-experience">
      <small>Trải nghiệm nhanh (demo):</small>
      <button
        type="button"
        className="experience-switch-button"
        onClick={() => void enter("renter")}
        disabled={busy !== null}
      >
        {busy === "renter" ? "Đang chuyển…" : "Trải nghiệm người thuê"}
      </button>
      <button
        type="button"
        className="experience-switch-button"
        onClick={() => void enter("owner")}
        disabled={busy !== null}
      >
        {busy === "owner" ? "Đang chuyển…" : "Trải nghiệm chủ nhà"}
      </button>
      {localError && (
        <small className="experience-switch-error" role="status">
          {localError}
        </small>
      )}
    </div>
  );
}
