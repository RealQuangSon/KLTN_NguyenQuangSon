import { useEffect, useRef, useState } from "react";
import { Brand } from "../components/Brand";
import { Icon } from "../components/Shared";
import { Journey } from "../components/Journey";
import { Link } from "../router";
// Màn mặc định là màn khởi đầu trợ lý, tham chiếu cảm giác hubhome.vn/tro-ly-ai
// (đọc 30/10/2026): giữa trang là avatar sáng, heading lớn và ô trò chuyện. Luồng
// công khai: tin nhắn ĐẦU TIÊN được trợ lý phản hồi ngay tại trang (kèm hiệu ứng
// đang soạn); từ tin nhắn THỨ HAI, tiếp tục trò chuyện yêu cầu đăng nhập — phiên
// tư vấn sau đăng nhập bắt đầu từ đúng câu hỏi mới nhất. Phản hồi công khai là
// văn bản chào mẫu, không giả kết quả tìm kiếm; phòng chỉ trả sau khi đăng nhập,
// xác nhận hồ sơ và chủ nhà duyệt. Hình ảnh/thương hiệu là của HomeMatch.
type Turn = { kind: "user" | "agent"; text: string };
const AGENT_FIRST_REPLY =
  "Mình đã ghi nhận nhu cầu của bạn. Khi đăng nhập, mình sẽ hỏi rõ phần còn thiếu — thành phố, số người, trần tổng tháng — rồi cùng bạn xác nhận hồ sơ trước khi tìm trong số phòng đã được chủ nhà duyệt.";
const AGENT_LOGIN_REPLY =
  "Để trả lời tiếp, bạn cần đăng nhập tài khoản. Phiên tư vấn sẽ bắt đầu từ đúng câu bạn vừa hỏi.";
const sampleAsks = [
  {
    icon: "cap",
    text: "Tìm phòng dưới 4 triệu gần trường, yên tĩnh để học tập",
  },
  {
    icon: "pin",
    text: "Phòng gần Cầu Giấy, Hà Nội cho 2 người, ưu tiên có máy lạnh",
  },
  {
    icon: "sofa",
    text: "Studio có nội thất ở Quận 7, tổng tháng tầm 5 triệu",
  },
  {
    icon: "wallet",
    text: "Tính giúp chi phí vào ở cho phòng 3 triệu, cọc 1 tháng",
  },
];
const quickNeeds = [
  {
    icon: "cap",
    title: "Gần trường đại học",
    description: "Tiến độ học, dễ cân đối ngân sách.",
    text: "Tôi cần phòng gần trường, yên tĩnh để học tập.",
  },
  {
    icon: "work",
    title: "Gần nơi làm việc",
    description: "Rút ngắn thời gian di chuyển mỗi ngày.",
    text: "Tìm phòng gần khu văn phòng ở TP.HCM, đi lại thuận tiện.",
  },
  {
    icon: "sofa",
    title: "Sẵn nội thất",
    description: "Dọn vào ngay với tiện ích thiết yếu.",
    text: "Cần studio có nội thất, máy lạnh và máy giặt ở Hà Nội.",
  },
  {
    icon: "wallet",
    title: "Dưới 5 triệu",
    description: "Lựa chọn vừa túi tiền đang còn phòng.",
    text: "Tìm phòng dưới 5 triệu một tháng, gần khu trung tâm.",
  },
];
const areaTiles = [
  {
    label: "Gần trường đại học",
    caption: "Tiến độ học, dễ cân đối ngân sách",
    tone: "navy",
  },
  {
    label: "Khu vực trung tâm",
    caption: "Kết nối thuận tiện, nhiều tiện ích",
    tone: "orange",
  },
  {
    label: "Gần nơi làm việc",
    caption: "Rút ngắn thời gian di chuyển mỗi ngày",
    tone: "teal",
  },
];
export function Landing({
  onNeed,
  onLogin,
  loggedIn = false,
}: {
  onNeed: (need: string) => void;
  onLogin: () => void;
  // Đã đăng nhập vẫn xem được trang chủ (tham chiếu HubHome): nút auth chuyển
  // thành CTA mở trợ lý, nhu cầu đi thẳng vào phiên đang mở.
  loggedIn?: boolean;
}) {
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [typing, setTyping] = useState(false);
  const [locked, setLocked] = useState(false);
  const timer = useRef<number | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  useEffect(
    () => () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    },
    [],
  );
  const focusComposer = () => {
    input.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    input.current?.focus({ preventScroll: true });
  };
  const fillComposer = (sample: string) => {
    if (turns.length > 0) return;
    setText(sample);
    focusComposer();
  };
  const send = () => {
    const need = text.trim();
    if (!need || typing || locked) return;
    setText("");
    if (turns.length === 0) {
      // Lượt đầu: trợ lý phản hồi ngay tại trang công khai.
      setTurns([{ kind: "user", text: need }]);
      setTyping(true);
      timer.current = window.setTimeout(() => {
        setTyping(false);
        setTurns((prev) => [...prev, { kind: "agent", text: AGENT_FIRST_REPLY }]);
      }, 900);
    } else {
      // Từ lượt thứ hai: tiếp tục trò chuyện cần tài khoản; phiên sau đăng nhập
      // bắt đầu từ câu hỏi mới nhất.
      setLocked(true);
      setTurns((prev) => [...prev, { kind: "user", text: need }]);
      setTyping(true);
      timer.current = window.setTimeout(() => {
        setTyping(false);
        setTurns((prev) => [...prev, { kind: "agent", text: AGENT_LOGIN_REPLY }]);
        timer.current = window.setTimeout(() => onNeed(need), 1100);
      }, 800);
    }
  };
  const started = turns.length > 0;
  const lastUserText = [...turns].reverse().find((turn) => turn.kind === "user")?.text;
  return (
    <main className="landing">
      <header className="landing-header site-header">
        <Brand />
        <nav className="site-nav" aria-label="Điều hướng trang chủ">
          <Link to="/tro-ly-ai">
            <Icon name="sparkles" size={14} /> Trợ lý AI
          </Link>
          <Link to="/cam-nang">Cẩm nang</Link>
          <Link to="/tim-kiem">Tìm nhà nhanh</Link>
        </nav>
        <div className="header-actions">
          <button className="text-button" onClick={onLogin}>
            {loggedIn ? "Mở trợ lý" : "Đăng nhập"}
          </button>
          <button className="button pill" onClick={focusComposer}>
            Tìm phòng ngay
          </button>
        </div>
      </header>
      <section className="landing-hero hh-start" aria-label="Trợ lý HomeMatch">
        {!started && (
          <>
            <span className="hh-start-avatar" aria-hidden="true">
              <Icon name="sparkles" size={34} />
            </span>
            <h1>
              Bạn đang tìm một <span>chỗ ở</span> như thế nào?
            </h1>
            <p className="hh-start-sub">
              Kể HomeMatch Agent biết bạn cần gì — khu vực, số người, ngân sách.
              Hồ sơ do bạn xác nhận; gợi ý luôn được quản lý duyệt trước khi tới
              tay bạn.
            </p>
          </>
        )}
        {started && (
          <div className="hh-conversation" aria-live="polite">
            {turns.map((turn, index) =>
              turn.kind === "user" ? (
                <div className="chat-message user" key={index}>
                  <span>Bạn</span>
                  <p>{turn.text}</p>
                </div>
              ) : (
                <div className="chat-message agent-reply" key={index}>
                  <span className="agent-avatar">
                    <Icon name="sparkles" size={16} />
                  </span>
                  <div>
                    <strong>HomeMatch Agent</strong>
                    <p>{turn.text}</p>
                  </div>
                </div>
              ),
            )}
            {typing && (
              <div className="chat-message agent-reply hh-typing" aria-label="Trợ lý đang soạn">
                <span className="agent-avatar">
                  <Icon name="sparkles" size={16} />
                </span>
                <span className="hh-dots" aria-hidden="true">
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            )}
            {!locked && (
              <button className="button pill" onClick={() => onNeed(lastUserText ?? "")}>
                {loggedIn ? "Tiếp tục trong trợ lý" : "Đăng nhập để tiếp tục"}
                <Icon name="arrow" size={18} />
              </button>
            )}
          </div>
        )}
        <form
          className="chat-composer hh-composer"
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
            rows={2}
            maxLength={2000}
            placeholder={
              started
                ? "Tiếp tục trò chuyện — lượt kế tiếp cần đăng nhập…"
                : "Tìm phòng dưới 4 triệu gần Đại học Bách Khoa…"
            }
            value={text}
            disabled={locked}
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
            disabled={!text.trim() || locked}
            aria-label="Gửi nhu cầu"
          >
            <Icon name="arrow" />
          </button>
        </form>
        {!started && (
          <>
            <p className="hh-ask-title">
              <Icon name="sparkles" size={14} /> Bạn có thể hỏi:
            </p>
            <div className="hh-asks">
              {sampleAsks.map((ask) => (
                <button
                  type="button"
                  key={ask.text}
                  onClick={() => fillComposer(ask.text)}
                >
                  <span className={`hh-quick-icon tone-${ask.icon}`}>
                    <Icon name={ask.icon} size={18} />
                  </span>
                  {ask.text}
                </button>
              ))}
            </div>
            <p className="input-hint">
              Lượt trò chuyện đầu được phản hồi ngay — từ lượt tiếp theo cần
              đăng nhập. HomeMatch không lưu hội thoại trên trình duyệt của bạn.
            </p>
          </>
        )}
        {started && !locked && (
          <p className="input-hint">
            Lượt trò chuyện kế tiếp sẽ cần đăng nhập — phiên tư vấn bắt đầu từ
            đúng câu bạn vừa hỏi.
          </p>
        )}
      </section>
      <section className="hh-quick" aria-label="Nhu cầu thường gặp">
        {quickNeeds.map((need) => (
          <button
            type="button"
            key={need.title}
            className="hh-quick-card"
            onClick={() => fillComposer(need.text)}
          >
            <span className={`hh-quick-icon tone-${need.icon}`}>
              <Icon name={need.icon} size={20} />
            </span>
            <span className="hh-quick-copy">
              <strong>{need.title}</strong>
              <small>{need.description}</small>
            </span>
            <Icon name="arrow" size={16} />
          </button>
        ))}
      </section>
      <section className="hh-banner">
        <div className="hh-banner-agent" aria-hidden="true">
          <span className="hh-banner-avatar">
            <Icon name="sparkles" size={30} />
          </span>
          <span className="hh-chip">Studio Quận 7 dưới 4 triệu</span>
          <span className="hh-chip">Gần ĐH Bách Khoa</span>
          <span className="hh-chip">Có máy giặt riêng</span>
        </div>
        <div className="hh-banner-copy">
          <span className="hh-eyebrow">Tìm bằng ngôn ngữ tự nhiên</span>
          <h2>Chỉ cần kể chỗ ở bạn đang tìm</h2>
          <p>
            Trợ lý ghi nhớ ngân sách, loại phòng và tiện ích trong cuộc trò
            chuyện, sau đó giúp bạn lưu và so sánh tối đa 3 lựa chọn.
          </p>
        </div>
        <div className="hh-banner-actions">
          <button className="button pill" onClick={focusComposer}>
            <Icon name="sparkles" size={16} /> Bắt đầu với trợ lý
          </button>
          <Link className="button pill outline" to="/tim-kiem">
            Xem gợi ý mẫu
          </Link>
        </div>
      </section>
      <section className="hh-tiles" aria-label="Vùng tìm phòng phổ biến">
        {areaTiles.map((tile) => (
          <div key={tile.label} className={`hh-tile tone-${tile.tone}`}>
            <span className="hh-tile-label">
              <Icon name="pin" size={17} /> {tile.label}
            </span>
            <small>{tile.caption}</small>
          </div>
        ))}
      </section>
      <section className="hh-roles">
        <article className="hh-role tone-orange">
          <span className="hh-eyebrow">Dành cho người tìm phòng</span>
          <h2>Gần trường, vừa ngân sách, dễ bắt đầu.</h2>
          <p>
            Tìm phòng theo nơi học, mức giá, chỗ để xe và nội quy — chi phí
            tháng và tiền vào ở được tính rõ theo kịch bản của bạn.
          </p>
          <button className="button pill light" onClick={focusComposer}>
            Bắt đầu tìm phòng
          </button>
        </article>
        <article className="hh-role tone-navy">
          <span className="hh-eyebrow">Dành cho chủ nhà</span>
          <h2>Tin của bạn có người trông.</h2>
          <p>
            Quản lý tin, duyệt gợi ý cho người thuê, theo hợp đồng, hóa đơn và
            bảo trì trong một cổng vận hành duy nhất.
          </p>
          <Link className="button pill light" to="/dang-nhap">
            Đăng nhập cổng chủ nhà
          </Link>
        </article>
      </section>
      <section className="hh-journey">
        <Journey step={0} />
      </section>
      <footer className="landing-footer">
        HomeMatch · Đề tài KLTN · Kho phòng giả lập · Chi phí là ước tính theo
        kịch bản đã xác nhận
      </footer>
    </main>
  );
}
