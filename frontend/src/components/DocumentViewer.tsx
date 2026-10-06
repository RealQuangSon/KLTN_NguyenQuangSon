import { useRef } from "react";
import { Icon } from "./Shared";
// Văn bản (hợp đồng, hóa đơn, biên lai) do máy chủ dựng HTML; hiển thị trong
// iframe cô lập và in/lưu PDF bằng hộp in của trình duyệt.
const STYLE = `<style>body{font:15px/1.6 system-ui,Arial,sans-serif;color:#222;margin:32px}
h1{font-size:20px;text-align:center}table{width:100%;border-collapse:collapse}
td,th{border:1px solid #ccc;padding:6px;text-align:left}</style>`;
export function DocumentViewer({
  html,
  title,
  onClose,
}: {
  html: string;
  title: string;
  onClose: () => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  return (
    <div className="modal-backdrop">
      <section
        className="panel modal document-modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
      >
        <div className="section-heading">
          <strong>{title}</strong>
          <div className="form-actions">
            <button
              className="button small outline"
              onClick={() => frame.current?.contentWindow?.print()}
            >
              <Icon name="check" size={15} /> In / Lưu PDF
            </button>
            <button className="text-button" onClick={onClose}>
              Đóng
            </button>
          </div>
        </div>
        <iframe
          ref={frame}
          title={title}
          className="document-frame"
          sandbox="allow-modals allow-same-origin"
          srcDoc={`<!doctype html><meta charset="utf-8">${STYLE}${html}`}
        />
      </section>
    </div>
  );
}
