import { useEffect, useRef, useState } from "react";
import type { Api } from "../api";
import type { Room } from "../types";
import { ErrorNotice, Icon } from "../components/Shared";
// Trợ lý AI cho chủ nhà: viết bài đăng theo kênh (chỉ dùng dữ liệu của tin),
// chia sẻ nhanh và cố vấn điều hành bằng câu lệnh văn bản hoặc giọng nói.
// HomeMatch không tự đăng lên mạng xã hội.
interface Post {
  channel: string;
  text: string;
  share_url: string | null;
  listing_url: string;
  highlights: string[];
  notice: string;
}
interface Answer {
  question: string;
  intent: string;
  answer: string;
}
type Recognition = {
  lang: string;
  interimResults: boolean;
  start: () => void;
  onresult:
    | ((event: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>;
      }) => void)
    | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
};
const speechApi = () =>
  (
    window as unknown as {
      SpeechRecognition?: new () => Recognition;
      webkitSpeechRecognition?: new () => Recognition;
    }
  ).SpeechRecognition ||
  (window as unknown as { webkitSpeechRecognition?: new () => Recognition })
    .webkitSpeechRecognition;
export function CopilotPage({ api }: { api: Api }) {
  const [rooms, setRooms] = useState<Room[]>([]);
  const [roomId, setRoomId] = useState("");
  const [channel, setChannel] = useState("facebook");
  const [post, setPost] = useState<Post | null>(null);
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [listening, setListening] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recognition = useRef<Recognition | null>(null);
  useEffect(() => {
    api
      .get<{ rooms: Room[] }>("/landlord/rooms")
      .then((data) => {
        setRooms(data.rooms);
        setRoomId((current) => current || data.rooms[0]?.id || "");
      })
      .catch((err) => setError((err as Error).message));
  }, [api]);
  const generate = async () => {
    setError(null);
    setCopied(false);
    try {
      setPost(
        await api.post<Post>(`/landlord/rooms/${roomId}/marketing`, {
          channel,
        }),
      );
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const ask = async (text: string) => {
    if (!text.trim()) return;
    setError(null);
    try {
      const result = await api.post<{ intent: string; answer: string }>(
        "/landlord/assistant",
        { question: text },
      );
      setAnswers((list) => [{ question: text, ...result }, ...list]);
      setQuestion("");
    } catch (err) {
      setError((err as Error).message);
    }
  };
  const listen = () => {
    const Speech = speechApi();
    if (!Speech) return;
    const engine = new Speech();
    engine.lang = "vi-VN";
    engine.interimResults = false;
    engine.onresult = (event) => {
      const text = event.results[0]?.[0]?.transcript || "";
      setQuestion(text);
      void ask(text);
    };
    engine.onerror = () =>
      setError("Không nhận được giọng nói; hãy thử lại hoặc gõ câu hỏi.");
    engine.onend = () => setListening(false);
    recognition.current = engine;
    setListening(true);
    engine.start();
  };
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">TRỢ LÝ AI CHO CHỦ NHÀ</span>
          <h1>Tiếp thị & cố vấn điều hành</h1>
          <p>
            Bài đăng chỉ dùng thông tin có trong tin (không bịa tiện ích hay
            giá). Cố vấn trả lời từ dữ liệu phòng, hợp đồng, hóa đơn và phòng
            tương đương trên hệ thống.
          </p>
        </div>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      <section className="panel">
        <h2>Tạo bài đăng đa kênh</h2>
        <div className="inline-form">
          <label>
            Phòng
            <select value={roomId} onChange={(e) => setRoomId(e.target.value)}>
              {rooms.map((room) => (
                <option key={room.id} value={room.id}>
                  {room.title.split(". ")[0]}
                </option>
              ))}
            </select>
          </label>
          <label>
            Kênh
            <select
              value={channel}
              onChange={(e) => setChannel(e.target.value)}
            >
              <option value="facebook">Facebook</option>
              <option value="zalo">Zalo</option>
              <option value="forum">Diễn đàn thuê trọ</option>
            </select>
          </label>
          <button
            className="button"
            disabled={!roomId}
            onClick={() => void generate()}
          >
            <Icon name="chat" size={16} /> Tạo nội dung
          </button>
        </div>
        {post && (
          <div className="marketing-output">
            <p className="input-hint">
              Điểm mạnh được chọn: {post.highlights.join(", ")}
            </p>
            <textarea
              aria-label="Nội dung bài đăng"
              rows={10}
              value={post.text}
              readOnly
            />
            <div className="form-actions">
              <button
                className="button small outline"
                onClick={async () => {
                  try {
                    await navigator.clipboard.writeText(post.text);
                    setCopied(true);
                  } catch {
                    setError(
                      "Trình duyệt không cho sao chép tự động; hãy chọn và sao chép thủ công.",
                    );
                  }
                }}
              >
                {copied ? "Đã sao chép" : "Sao chép nội dung"}
              </button>
              {post.share_url && (
                <a
                  className="button small"
                  href={post.share_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  Chia sẻ lên Facebook
                </a>
              )}
              <a
                className="text-button"
                href={post.listing_url}
                target="_blank"
                rel="noreferrer"
              >
                Mở trang tin công khai
              </a>
            </div>
            <small>{post.notice}</small>
          </div>
        )}
      </section>
      <section className="panel">
        <h2>Cố vấn điều hành</h2>
        <form
          className="handbook-ask"
          onSubmit={(e) => {
            e.preventDefault();
            void ask(question);
          }}
        >
          <label>
            Câu hỏi
            <input
              value={question}
              placeholder="Ví dụ: Vì sao phòng trống lâu? Phòng 012 nên cho thuê giá bao nhiêu?"
              onChange={(e) => setQuestion(e.target.value)}
            />
          </label>
          {speechApi() && (
            <button
              type="button"
              className="button outline"
              onClick={listen}
              disabled={listening}
            >
              {listening ? "Đang nghe…" : "Nói"}
            </button>
          )}
          <button className="button">Hỏi</button>
        </form>
        {answers.map((item, index) => (
          <article key={index} className="lead-card">
            <strong>{item.question}</strong>
            <p className="pre-line">{item.answer}</p>
          </article>
        ))}
      </section>
    </>
  );
}
