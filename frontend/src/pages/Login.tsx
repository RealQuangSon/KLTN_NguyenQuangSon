import { useState } from "react";
import { Api } from "../api";
import type { Actor } from "../types";
import { ErrorNotice, Icon } from "../components/Shared";
import { Brand } from "../components/Brand";
import { Link } from "../router";
import { RoomIllustration } from "../components/RoomIllustration";
// Màn đăng nhập (S02) tách từ App khi gắn router; giữ nguyên văn bản và luồng
// pendingNeed từ trang chủ. Đăng ký là lối mới nối tới /dang-ky.
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
    [busy, setBusy] = useState(false);
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
  return (
    <main className="login-layout">
      <section className="login-story">
        <Brand />
        <div className="login-story-copy">
          <span className="story-tag">
            <Icon name="leaf" size={15} /> Một nơi ở. Nhiều điều phù hợp.
          </span>
          <h1>
            Một căn phòng nhỏ.
            <br />
            <span>Một khởi đầu mới.</span>
          </h1>
          <p>
            Tìm nơi bạn muốn trở về, với những lựa chọn phù hợp nhu cầu và chi
            phí rõ ràng ngay từ đầu.
          </p>
        </div>
        <div className="login-art">
          <RoomIllustration />
          <div className="art-caption">
            <span>
              <Icon name="sun" size={18} />
            </span>
            <div>
              <strong>Vừa với cuộc sống của bạn</strong>
              <small>Một nơi sáng hơn cho những ngày mới</small>
            </div>
          </div>
        </div>
        <div className="login-principles">
          <span>
            <Icon name="chat" />
            Hỏi rõ nhu cầu
          </span>
          <span>
            <Icon name="compare" />
            So sánh chi phí
          </span>
          <span>
            <Icon name="shield" />
            Quản lý duyệt
          </span>
        </div>
        <small className="story-footer">
          HomeMatch · Đề tài KLTN · Dữ liệu phòng giả lập
        </small>
      </section>
      <section className="login-form-side">
        <div className="login-form">
          <button
            type="button"
            className="text-button login-back"
            onClick={onBack}
          >
            ← Về trang chủ
          </button>
          <span className="login-welcome-icon">
            <Icon name="home" size={25} />
          </span>
          <span className="eyebrow">NƠI Ở TIẾP THEO BẮT ĐẦU TỪ ĐÂY</span>
          <h2>Chào mừng bạn trở lại.</h2>
          <p className="subtle">
            Đăng nhập để tiếp tục hành trình tìm phòng của bạn hoặc quản lý các
            đề xuất tư vấn.
          </p>
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
            <label>
              Tên đăng nhập
              <input
                autoComplete="username"
                required
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Nhập tên đăng nhập của bạn"
                disabled={busy}
              />
            </label>
            <div className="password-field">
              <label htmlFor="login-password">Mật khẩu</label>
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
            <button className="button" disabled={busy}>
              {busy ? "Đang đăng nhập…" : "Đăng nhập"}
              <Icon name="arrow" size={18} />
            </button>
          </form>
          <p className="auth-alt">
            Chưa có tài khoản? <Link to="/dang-ky">Đăng ký</Link>
          </p>
          <div className="login-note">
            <Icon name="shield" size={18} />
            <p>
              Tài khoản người thuê và quản lý được cấp trong môi trường thử
              nghiệm. Gợi ý phòng luôn được kiểm tra trước khi giới thiệu.
            </p>
          </div>
          <div className="login-form-footer">
            <span className="status-dot" /> Môi trường nghiên cứu · Kho phòng
            giả lập
          </div>
        </div>
      </section>
    </main>
  );
}
