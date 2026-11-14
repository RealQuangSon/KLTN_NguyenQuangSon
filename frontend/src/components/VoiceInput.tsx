import { useRef, useState } from "react";
import { Icon } from "./Shared";
// Nhập giọng nói bằng Web Speech API của chính trình duyệt (miễn phí, chạy
// local — không gọi dịch vụ ngoài). Trình duyệt không hỗ trợ thì nói thẳng
// thay vì giả vờ có tính năng.
type RecognitionLike = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  start: () => void;
  stop: () => void;
  onresult:
    | ((event: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};
function recognitionCtor(): (new () => RecognitionLike) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: new () => RecognitionLike;
    webkitSpeechRecognition?: new () => RecognitionLike;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}
export function VoiceButton({
  onText,
  disabled,
}: {
  onText: (text: string) => void;
  disabled?: boolean;
}) {
  const [listening, setListening] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const recRef = useRef<RecognitionLike | null>(null);
  const supported = Boolean(recognitionCtor());
  const toggle = () => {
    if (!supported) {
      setNote(
        "Trình duyệt này chưa hỗ trợ nhập giọng nói — hãy dùng Chrome hoặc Edge.",
      );
      return;
    }
    if (listening) {
      recRef.current?.stop();
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor) return;
    const rec = new Ctor();
    rec.lang = "vi-VN";
    rec.interimResults = false;
    rec.continuous = false;
    rec.onresult = (event) => {
      const text = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (text) onText(text);
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => {
      setListening(false);
      setNote("Chưa nghe được — kiểm tra quyền micro của trình duyệt.");
    };
    recRef.current = rec;
    setNote(null);
    setListening(true);
    rec.start();
  };
  return (
    <>
      <button
        type="button"
        className={listening ? "voice-btn listening" : "voice-btn"}
        aria-label={listening ? "Dừng nhập giọng nói" : "Nhập bằng giọng nói"}
        aria-pressed={listening}
        title={
          supported
            ? "Nhập bằng giọng nói (tiếng Việt)"
            : "Trình duyệt không hỗ trợ nhập giọng nói"
        }
        disabled={disabled}
        onClick={toggle}
      >
        <Icon name="mic" size={16} />
      </button>
      {note && (
        <small className="voice-note" role="status">
          {note}
        </small>
      )}
    </>
  );
}
