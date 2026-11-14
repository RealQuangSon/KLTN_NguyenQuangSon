import { useState } from "react";
import { ApiError, registerAccount } from "../api";
import { ErrorNotice, Icon } from "../components/Shared";
import { Brand } from "../components/Brand";
import { Link, useNavigate } from "../router";
import { RoomIllustration } from "../components/RoomIllustration";
// Màn đăng ký (S02, FE-18; FE-01/FE-02): gọi POST /auth/register theo hợp đồng
// (docs/coding-plan/README.md §7.1). Người dùng tự chọn account_type
// "renter"|"owner"; hồ sơ chủ nhà bắt đầu ở trạng thái chờ quản trị viên duyệt.
// Xác minh email và cấp vai trò nhạy cảm vẫn do máy chủ quyết định. Lỗi hiển thị
// đúng message máy chủ trả về, không bịa nhánh lỗi cũ (FE-01).
type FieldErrors = Partial<
  Record<"full_name" | "email" | "username" | "password" | "confirm", string>
>;
const validate = (
  fullName: string,
  email: string,
  username: string,
  password: string,
  confirm: string,
): FieldErrors => {
  const errors: FieldErrors = {};
  if (!fullName.trim()) errors.full_name = "Vui lòng nhập họ và tên.";
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim()))
    errors.email = "Vui lòng nhập email hợp lệ.";
  if (username.trim().length < 3)
    errors.username = "Tên đăng nhập cần ít nhất 3 ký tự.";
  if (password.length < 10) errors.password = "Mật khẩu cần ít nhất 10 ký tự.";
  if (password !== confirm) errors.confirm = "Mật khẩu nhập lại chưa khớp.";
  return errors;
};
export function Register() {
  const [fullName, setFullName] = useState(""),
    [email, setEmail] = useState(""),
    [username, setUsername] = useState(""),
    [password, setPassword] = useState(""),
    [confirm, setConfirm] = useState(""),
    [accountType, setAccountType] = useState<"renter" | "owner">("renter"),
    [fieldErrors, setFieldErrors] = useState<FieldErrors>({}),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<string | null>(null),
    [serverNotice, setServerNotice] = useState<string | null>(null);
  const navigate = useNavigate();
  const submit = async () => {
    setServerNotice(null);
    const errors = validate(fullName, email, username, password, confirm);
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setBusy(true);
    setError(null);
    try {
      const result = await registerAccount({
        username: username.trim(),
        password,
        email: email.trim(),
        display_name: fullName.trim(),
        account_type: accountType,
      });
      // Chỉ hiển thị những gì máy chủ trả về: đăng ký luôn ở trạng thái
      // pending_verification; việc xác minh và cấp vai trò thuộc về máy chủ.
      setServerNotice(
        result.message ||
          (result.status === "pending_verification"
            ? "Đã tạo tài khoản, đang chờ xác minh email. Mở thư theo hướng dẫn của máy chủ để kích hoạt; môi trường dev in mã xác minh trong log máy chủ."
            : "Máy chủ đã tiếp nhận đăng ký. Tình trạng kích hoạt và vai trò do máy chủ quyết định."),
      );
    } catch (err) {
      // FE-01: không còn nhánh 404 giả định máy chủ thiếu chức năng đăng ký;
      // mọi lỗi hiện đúng message của ApiError, lỗi mạng hiển thị riêng.
      if (err instanceof ApiError && err.status === 0)
        setError("Không kết nối được máy chủ");
      else
        setError(err instanceof Error ? err.message : "Đăng ký chưa hoàn tất.");
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
            Bắt đầu hành trình
            <br />
            <span>tìm một nơi ở phù hợp.</span>
          </h1>
          <p>
            Tạo tài khoản để trò chuyện với trợ lý, lưu nhu cầu và nhận danh
            sách phòng phù hợp — hoặc đăng ký làm chủ nhà để đăng tin cho thuê.
          </p>
        </div>
        <div className="login-art">
          <RoomIllustration />
          <div className="art-caption">
            <span>
              <Icon name="sun" size={18} />
            </span>
            <div>
              <strong>Minh bạch từ đầu</strong>
              <small>Chi phí rõ ràng theo kịch bản của bạn</small>
            </div>
          </div>
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
            onClick={() => navigate("/")}
          >
            ← Về trang chủ
          </button>
          <span className="login-welcome-icon">
            <Icon name="home" size={25} />
          </span>
          <span className="eyebrow">ĐĂNG KÝ TÀI KHOẢN</span>
          <h2>Tạo tài khoản HomeMatch.</h2>
          <p className="subtle">
            Chọn vai trò của bạn: người thuê tìm phòng hoặc chủ nhà đăng tin.
            Tài khoản quản lý và quản trị vẫn do máy chủ cấp theo quy trình
            riêng.
          </p>
          <ErrorNotice error={error} onClose={() => setError(null)} />
          {serverNotice && (
            <div className="notice success" role="status">
              {serverNotice}
            </div>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void submit();
            }}
            noValidate
          >
            <fieldset className="account-type">
              <legend>Bạn là</legend>
              <div className="chip-row">
                <label className="checkbox-line">
                  <input
                    type="radio"
                    name="account_type"
                    value="renter"
                    checked={accountType === "renter"}
                    onChange={() => setAccountType("renter")}
                    disabled={busy}
                  />
                  Người thuê
                </label>
                <label className="checkbox-line">
                  <input
                    type="radio"
                    name="account_type"
                    value="owner"
                    checked={accountType === "owner"}
                    onChange={() => setAccountType("owner")}
                    disabled={busy}
                  />
                  Chủ nhà
                </label>
              </div>
              {accountType === "owner" && (
                <small className="input-hint">
                  Sau khi xác minh email, tài khoản chủ nhà cần quản trị viên
                  duyệt trước khi công khai tin.
                </small>
              )}
            </fieldset>
            <label>
              Họ và tên
              <input
                autoComplete="name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                placeholder="Nhập họ và tên của bạn"
                disabled={busy}
                aria-invalid={fieldErrors.full_name ? true : undefined}
              />
              {fieldErrors.full_name && (
                <small className="field-error">{fieldErrors.full_name}</small>
              )}
            </label>
            <label>
              Email
              <input
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email nhận thư xác minh"
                disabled={busy}
                aria-invalid={fieldErrors.email ? true : undefined}
              />
              {fieldErrors.email && (
                <small className="field-error">{fieldErrors.email}</small>
              )}
            </label>
            <label>
              Tên đăng nhập
              <input
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Chọn tên đăng nhập"
                disabled={busy}
                aria-invalid={fieldErrors.username ? true : undefined}
              />
              {fieldErrors.username && (
                <small className="field-error">{fieldErrors.username}</small>
              )}
            </label>
            <div className="password-field">
              <label htmlFor="register-password">Mật khẩu</label>
              <div className="password-input">
                <input
                  id="register-password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Ít nhất 10 ký tự"
                  disabled={busy}
                  aria-invalid={fieldErrors.password ? true : undefined}
                />
              </div>
              {fieldErrors.password && (
                <small className="field-error">{fieldErrors.password}</small>
              )}
            </div>
            <label>
              Nhập lại mật khẩu
              <input
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                placeholder="Nhập lại mật khẩu"
                disabled={busy}
                aria-invalid={fieldErrors.confirm ? true : undefined}
              />
              {fieldErrors.confirm && (
                <small className="field-error">{fieldErrors.confirm}</small>
              )}
            </label>
            <button className="button" disabled={busy}>
              {busy ? "Đang gửi đăng ký…" : "Đăng ký"}
              <Icon name="arrow" size={18} />
            </button>
          </form>
          <p className="auth-alt">
            Đã có tài khoản? <Link to="/dang-nhap">Đăng nhập</Link>
          </p>
          <div className="login-note">
            <Icon name="shield" size={18} />
            <p>
              Mật khẩu không được lưu trên trình duyệt. Yêu cầu đăng ký gửi tới
              máy chủ thật; lỗi từ máy chủ được hiển thị nguyên văn thay vì báo
              thành công ảo.
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
