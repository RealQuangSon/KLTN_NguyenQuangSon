import { useState } from "react";
import { Api } from "../api";
import type { Actor } from "../types";
import { ErrorNotice, Icon } from "../components/Shared";
import { Brand } from "../components/Brand";
import {
  ExperienceChips,
  useDemoExperience,
} from "../components/DemoExperience";
import { Link } from "../router";
// Màn đăng nhập (S02) bố cục hai cột: cột trái là form tối giản
// (chọn loại tài khoản, ô gạch chân, nút pill), cột phải là cảnh phố màu ấm vẽ bằng
// CSS kèm tagline. Icon và hình dùng bộ của HomeMatch.
export function Login({
  error,
  onError,
  onBack,
  pendingNeed,
  onAuthenticated,
}: {
  error: string | null;
  onError: (message: string) => void;
  onBack: () => void;
  pendingNeed: string | null;
  onAuthenticated: (token: string, actor: Actor) => void;
}) {
  const [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [showPassword, setShowPassword] = useState(false),
    [busy, setBusy] = useState(false),
    [role, setRole] = useState<"renter" | "owner">("renter"),
    [forgotOpen, setForgotOpen] = useState(false),
    [forgotUsername, setForgotUsername] = useState(""),
    [forgotBusy, setForgotBusy] = useState(false),
    [forgotNote, setForgotNote] = useState<string | null>(null);
  // Chỉ hiện chip trải nghiệm nhanh khi /health xác nhận seed local.
  const demoReady = useDemoExperience();
  const login = async () => {
    if (busy) return;
    setBusy(true);
    onError("");
    try {
      const response = await new Api(null).post<{
        access_token: string;
        actor: Actor;
      }>("/auth/login", { username, password });
      onAuthenticated(response.access_token, response.actor);
    } catch (err) {
      onError(err instanceof Error ? err.message : "Chưa đăng nhập được.");
    } finally {
      setBusy(false);
    }
  };
  const requestReset = async () => {
    if (forgotBusy || !forgotUsername.trim()) return;
    setForgotBusy(true);
    setForgotNote(null);
    try {
      await new Api(null).post("/auth/password-reset/request", {
        username: forgotUsername.trim(),
      });
      // Email chỉ là stub ghi log trong môi trường local; nói thẳng điều đó.
      setForgotNote(
        "Đã ghi nhận yêu cầu. Môi trường local chưa có email thật — mã đặt lại nằm trong log máy chủ.",
      );
    } catch (err) {
      setForgotNote(
        err instanceof Error ? err.message : "Chưa gửi được yêu cầu đặt lại.",
      );
    } finally {
      setForgotBusy(false);
    }
  };
  return (
    <main className="auth-page">
      <section className="auth-main">
        <div className="auth-top">
          <Brand />
          <button
            type="button"
            className="text-button login-back"
            onClick={onBack}
          >
            ← Về trang chủ
          </button>
        </div>
        <div className="auth-card">
          <h1>Đăng nhập HomeMatch</h1>
          <p className="auth-sub">
            {role === "renter"
              ? "Trợ lý sẽ ghi nhớ khu vực, ngân sách và số người ở mà bạn đã chia sẻ."
              : "Quản lý tin đăng, hợp đồng và hóa đơn trong cổng chủ nhà."}
          </p>
          <div
            className="auth-toggle"
            role="group"
            aria-label="Chọn loại tài khoản"
          >
            <button
              type="button"
              aria-pressed={role === "renter"}
              onClick={() => setRole("renter")}
            >
              Người thuê
            </button>
            <button
              type="button"
              aria-pressed={role === "owner"}
              onClick={() => setRole("owner")}
            >
              Chủ nhà
            </button>
          </div>
          {demoReady && (
            <ExperienceChips
              kind={role}
              disabled={busy}
              onAuthenticated={onAuthenticated}
              onError={onError}
            />
          )}
          {pendingNeed && (
            <div className="pending-need">
              <div className="pending-need-icon">
                <Icon name="chat" size={19} />
              </div>
              <div>
                <strong>Bạn vừa chia sẻ nhu cầu với trợ lý</strong>
                <p>“{pendingNeed}”</p>
                <small>
                  Đăng nhập bằng tài khoản người thuê để trợ lý bắt đầu phiên tư
                  vấn từ nhu cầu này.
                </small>
              </div>
            </div>
          )}
          <ErrorNotice error={error} />
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void login();
            }}
          >
            <label className="auth-field">
              <span className="auth-req">
                Tên đăng nhập <i aria-hidden="true">*</i>
              </span>
              <input
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Nhập tên đăng nhập của bạn"
                disabled={busy}
              />
            </label>
            <div className="auth-field password-field">
              <label htmlFor="login-password" className="auth-req">
                Mật khẩu <i aria-hidden="true">*</i>
              </label>
              <div className="password-input">
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Nhập mật khẩu"
                  disabled={busy}
                />
                <button
                  type="button"
                  className="icon-button"
                  aria-label={showPassword ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  aria-pressed={showPassword}
                  onClick={() => setShowPassword(!showPassword)}
                  disabled={busy}
                >
                  <Icon name={showPassword ? "eyeOff" : "eye"} size={19} />
                </button>
              </div>
            </div>
            <div className="auth-form-meta">
              <small>Mật khẩu mã hóa scrypt — không lưu bản rõ</small>
              <Link to="/cam-nang" className="auth-help">
                Cần trợ giúp?
              </Link>
            </div>
            <button className="auth-cta" disabled={busy}>
              <Icon name="shield" size={17} />
              {busy ? "Đang đăng nhập…" : "Đăng nhập"}
            </button>
          </form>
          <p className="auth-terms">
            Khi tiếp tục, bạn đồng ý sử dụng HomeMatch trong khuôn khổ đồ án
            nghiên cứu; dữ liệu phòng là dữ liệu giả lập.
          </p>
          <Link to="/dang-ky" className="auth-alt-cta">
            Chưa có tài khoản? Đăng ký
          </Link>
          <div className="auth-forgot">
            {forgotOpen ? (
              <>
                <label className="auth-field">
                  Tên đăng nhập cần đặt lại mật khẩu
                  <input
                    value={forgotUsername}
                    onChange={(e) => setForgotUsername(e.target.value)}
                    placeholder="ví dụ: renter-a"
                    disabled={forgotBusy}
                  />
                </label>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => void requestReset()}
                  disabled={forgotBusy || !forgotUsername.trim()}
                >
                  {forgotBusy ? "Đang gửi…" : "Gửi yêu cầu đặt lại mật khẩu"}
                </button>
                {forgotNote && (
                  <small className="auth-forgot-note">{forgotNote}</small>
                )}
              </>
            ) : (
              <button
                type="button"
                className="text-button auth-forgot-toggle"
                onClick={() => setForgotOpen(true)}
              >
                Quên mật khẩu?
              </button>
            )}
          </div>
          <p className="auth-safety">
            HomeMatch không bao giờ hỏi mật khẩu của bạn qua điện thoại hay tin
            nhắn.
          </p>
        </div>
      </section>
      <section className="auth-hero" aria-hidden="true">
        <div className="auth-sky">
          <span className="auth-sun" />
          <span className="auth-skyline far" />
          <span className="auth-skyline near" />
          <span className="auth-water" />
        </div>
        <p className="auth-tagline">
          Một nơi ở.
          <br />
          Nhiều điều phù hợp.
        </p>
      </section>
    </main>
  );
}
