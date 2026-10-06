import { useEffect, useRef, useState } from "react";
import { Brand } from "../components/Brand";
import { Icon } from "../components/Shared";
import { Journey } from "../components/Journey";
import { RoomIllustration } from "../components/RoomIllustration";
const suggestions = [
  {
    label: "Gần trường",
    text: "Tôi cần phòng gần trường, yên tĩnh để học tập.",
  },
  {
    label: "Có cửa sổ",
    text: "Tôi muốn phòng có cửa sổ, thoáng sáng.",
  },
  {
    label: "Dưới 3 triệu",
    text: "Tìm phòng TP.HCM, tổng chi phí tầm 3 triệu một tháng.",
  },
  {
    label: "Căn hộ Hà Nội",
    text: "Tìm căn hộ 1 phòng ngủ ở Cầu Giấy, Hà Nội cho 2 người, view thoáng.",
  },
];
const points = [
  {
    icon: "chat",
    title: "Hỏi rõ, không đoán",
    description:
      "Trợ lý hỏi từng điều còn thiếu; bạn xác nhận hồ sơ trước khi tìm.",
  },
  {
    icon: "compare",
    title: "Chi phí rõ ràng",
    description:
      "Tổng chi phí tháng và tiền cần chuẩn bị vào ở theo kịch bản của bạn.",
  },
  {
    icon: "shield",
    title: "Duyệt trước khi giới thiệu",
    description:
      "Quản lý kiểm tra nguồn và bảng phí; bạn chỉ nhận danh sách đã duyệt.",
  },
];
// Sau khi gửi nhu cầu, trang chủ chuyển sang đăng nhập như khảo sát HubHome:
// hội thoại công khai kết thúc bằng yêu cầu đăng nhập, không trả phòng chưa duyệt.
export function Landing({
  onNeed,
  onLogin,
}: {
  onNeed: (need: string) => void;
  onLogin: () => void;
}) {
  const [text, setText] = useState("");
  const [sent, setSent] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );
  const send = () => {
    const need = text.trim();
    if (!need || sent) return;
    setSent(need);
    setText("");
    timer.current = window.setTimeout(() => onNeed(need), 700);
  };
  return (
    <main className="landing">
      <header className="landing-header">
        <Brand />
        <button className="button outline small" onClick={onLogin}>
          Đăng nhập
        </button>
      </header>
      <section className="landing-hero">
        <div className="landing-copy">
          <span className="story-tag">
            <Icon name="sparkles" size={15} /> Trợ lý tìm phòng của bạn
          </span>
          <h1>
            Nơi ở tiếp theo
            <br />
            <span>bắt đầu từ một cuộc trò chuyện.</span>
          </h1>
          <p>
            Kể HomeMatch biết bạn cần gì: khu vực, số người, điều kiện bắt buộc
            và ngân sách. Hồ sơ do bạn xác nhận; quản lý kiểm tra gợi ý trước
            khi danh sách tới tay bạn.
          </p>
          <Journey step={0} />
        </div>
        <section className="panel landing-chat" aria-label="Trợ lý HomeMatch">
          <div className="agent-heading">
            <div className="agent-avatar">
              <Icon name="sparkles" size={22} />
            </div>
            <div>
              <h2>Trợ lý HomeMatch</h2>
              <span>Hỏi rõ nhu cầu · Chỉ giới thiệu phòng đã được duyệt</span>
            </div>
          </div>
          {sent ? (
            <div className="landing-captured" aria-live="polite">
              <div className="chat-message user">
                <span>Bạn</span>
                <p>{sent}</p>
              </div>
              <div className="chat-message">
                <span>HomeMatch</span>
                <p>
                  Cảm ơn bạn! Trợ lý sẽ bắt đầu phiên tư vấn từ nhu cầu này sau
                  khi bạn đăng nhập: hỏi rõ phần còn thiếu, cùng bạn xác nhận hồ
                  sơ rồi mới tìm phòng.
                </p>
              </div>
              <button className="button" onClick={() => onNeed(sent)}>
                Đăng nhập để tiếp tục <Icon name="arrow" size={18} />
              </button>
            </div>
          ) : (
            <>
              <p className="landing-chat-lead">
                Bạn đang tìm phòng như thế nào? Cứ viết tự nhiên — khu vực, gần
                đâu, cho bao nhiêu người và tầm bao nhiêu mỗi tháng.
              </p>
              <form
                className="chat-composer"
                onSubmit={(e) => {
                  e.preventDefault();
                  send();
                }}
              >
                <label className="visually-hidden" htmlFor="landing-need">
                  Nhu cầu tìm phòng của bạn
                </label>
                <textarea
                  id="landing-need"
                  ref={input}
                  rows={3}
                  maxLength={2000}
                  placeholder="Ví dụ: căn hộ 1PN Cầu Giấy, Hà Nội cho 2 người, hoặc phòng Quận 7 TP.HCM có cửa sổ, tổng tháng tầm 4 triệu…"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !e.nativeEvent.isComposing
                    ) {
                      e.preventDefault();
                      send();
                    }
                  }}
                />
                <button
                  className="button icon-button"
                  disabled={!text.trim()}
                  aria-label="Gửi nhu cầu"
                >
                  <Icon name="arrow" />
                </button>
              </form>
              <div className="chat-suggestions" aria-label="Gợi ý bắt đầu">
                <span>Bạn có thể bắt đầu với</span>
                {suggestions.map((suggestion) => (
                  <button
                    type="button"
                    key={suggestion.label}
                    onClick={() => {
                      setText(suggestion.text);
                      input.current?.focus();
                    }}
                  >
                    {suggestion.label}
                    <Icon name="arrow" size={12} />
                  </button>
                ))}
              </div>
              <p className="input-hint">
                Cần đăng nhập để mở phiên tư vấn. HomeMatch không lưu hội thoại
                trên trình duyệt của bạn.
              </p>
            </>
          )}
        </section>
      </section>
      <section className="landing-showcase">
        <div className="landing-art">
          <RoomIllustration />
          <span>Hình minh họa — không phải căn phòng thật</span>
        </div>
        <ul className="landing-points">
          {points.map((point) => (
            <li key={point.title}>
              <span className="point-icon">
                <Icon name={point.icon} size={19} />
              </span>
              <div>
                <strong>{point.title}</strong>
                <small>{point.description}</small>
              </div>
            </li>
          ))}
        </ul>
      </section>
      <footer className="landing-footer">
        HomeMatch · Đề tài KLTN · Kho phòng giả lập · Chi phí là ước tính theo
        kịch bản đã xác nhận
      </footer>
    </main>
  );
}
