import { useEffect, useState } from "react";
import type { Api } from "../api";
import { ErrorNotice, Icon } from "../components/Shared";
// Cẩm nang người thuê: các mục chung của nền tảng và hỏi đáp tự động bằng
// truy xuất (không sinh nội dung). Nội quy riêng của từng chủ nhà được hỏi
// trong khung xem nhanh của tin đăng.
interface Entry {
  id: string;
  title: string;
  answer: string;
}
export function HandbookPage({ api }: { api: Api }) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<{
    answers: Entry[];
    disclaimer: string;
    found: boolean;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .get<Entry[]>("/handbook")
      .then(setEntries)
      .catch((err) => setError((err as Error).message));
  }, [api]);
  return (
    <>
      <div className="page-heading">
        <div>
          <span className="eyebrow">CẨM NANG NGƯỜI THUÊ</span>
          <h1>Hỏi đáp quyền lợi & quy định</h1>
          <p>
            Thông tin tham khảo chung. Nội quy và cách tính điện nước của từng
            phòng xem trong phần chi tiết tin.
          </p>
        </div>
      </div>
      <ErrorNotice error={error} onClose={() => setError(null)} />
      <form
        className="panel handbook-ask"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!question.trim()) return;
          try {
            setAnswer(await api.post("/handbook/ask", { question }));
          } catch (err) {
            setError((err as Error).message);
          }
        }}
      >
        <label>
          Câu hỏi của bạn
          <input
            value={question}
            placeholder="Ví dụ: khi trả phòng có được hoàn cọc không?"
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>
        <button className="button">
          <Icon name="search" size={16} /> Hỏi
        </button>
      </form>
      {answer && (
        <section className="panel handbook-answer" aria-label="Câu trả lời">
          {answer.found ? (
            answer.answers.map((entry) => (
              <p key={entry.id}>
                <strong>{entry.title}:</strong> {entry.answer}
              </p>
            ))
          ) : (
            <p>Chưa có mục phù hợp; bạn có thể hỏi trực tiếp chủ nhà.</p>
          )}
          <small>{answer.disclaimer}</small>
        </section>
      )}
      <section className="panel">
        <h2>Tất cả mục</h2>
        {entries.map((entry) => (
          <details key={entry.id}>
            <summary>{entry.title}</summary>
            <p>{entry.answer}</p>
          </details>
        ))}
      </section>
    </>
  );
}
