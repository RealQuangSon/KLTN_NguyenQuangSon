import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Api, ApiError } from "../api";
import { visibleStatuses } from "../types";
import type {
  Actor,
  Candidate,
  ChatSimulation,
  Draft,
  Profile,
  Results,
  Session,
  Viewing,
} from "../types";
import {
  Comparison,
  CostBreakdown,
  ErrorNotice,
  Icon,
  money,
  PublishedResults,
  RoomCard,
  roomTitle,
} from "../components/Shared";
import { ProfileForm } from "../components/ProfileForm";
import { profileFromDraft, profileUpdateFromChat } from "../profile";
import { MapView } from "../components/MapView";
import { SimulationPanel, SimulationResults } from "../components/Simulation";
import type { Advice } from "../components/Advice";
import { openConversation } from "./Inbox";
import { ViewingForm, ViewingList } from "../components/ViewingPanel";
import { LoadingState } from "../components/LoadingState";
import { AgentMascot } from "../components/AgentMascot";
import { VoiceButton } from "../components/VoiceInput";
import { Link } from "../router";
type ClarificationOption = {
  id: string;
  label: string;
  patch: { set: Record<string, unknown> };
};
type Message = {
  role: "user" | "assistant";
  text: string;
  // AG-11: câu hỏi làm rõ kèm chip — render trên đầu câu trả lời.
  clarification?: {
    question: string;
    options: ClarificationOption[];
    decided_by: string;
  } | null;
  // FE-07: reply của intent simulate_finance kèm thẻ mô phỏng hoặc nhắc xem lại danh sách.
  simulation?: ChatSimulation | null;
  needsResults?: boolean;
  // WS-02: các bước xử lý thật của lượt ("tool: mô tả") — bung được sau câu trả lời.
  steps?: string[];
};
// Thẻ mô phỏng trong luồng chat (README §7.4). Bảng kết quả tái dùng đúng
// component của SimulationPanel nên không viết lại cách format số.
function SimulationMessage({ simulation }: { simulation: ChatSimulation }) {
  const { scenario } = simulation;
  // Máy chủ thiếu phần kết quả thì chỉ hiện câu trả lời, không render thẻ rỗng.
  if (!simulation.result?.cost) return null;
  return (
    <div className="chat-simulation" aria-label="Thẻ mô phỏng vay">
      <span className="eyebrow">MÔ PHỎNG VAY · KHÔNG ĐỔI HỒ SƠ</span>
      <strong>{roomTitle(simulation.room_title)}</strong>
      <small className="simulation-scenario">
        Lãi{" "}
        {scenario.annual_rate == null
          ? "Chưa rõ"
          : `${scenario.annual_rate}%/năm`}{" "}
        ·{" "}
        {scenario.term_months == null
          ? "Chưa rõ"
          : `${scenario.term_months} tháng`}{" "}
        · Gốc vay{" "}
        {scenario.principal_vnd == null
          ? "Chưa rõ"
          : money(scenario.principal_vnd)}
      </small>
      <SimulationResults
        items={[
          {
            label: simulation.result?.label || "Kịch bản hỏi nhanh",
            cost: simulation.result.cost,
          },
        ]}
      />
    </div>
  );
}
// Khung đang xử lý kiểu workspace tham chiếu: bộ khung thẻ + mascot trạng thái
// giữa khung preview, thay màn trắng chờ.
function PreviewSkeleton({ label }: { label: string }) {
  return (
    <div className="agent-pending">
      <div className="agent-pending-ring">
        <AgentMascot size={46} />
      </div>
      <strong>{label}</strong>
      <small>Danh sách sẽ tự hiện ở khung này trong chốc lát.</small>
      <div className="preview-skeleton" aria-hidden="true">
        {Array.from({ length: 4 }).map((_, index) => (
          <div className="skel-card" key={index}>
            <div className="skel-img" />
            <div className="skel-line w70" />
            <div className="skel-line w45" />
          </div>
        ))}
      </div>
    </div>
  );
}
// AG-05: mã phòng trong câu trả lời bấm được — mở xem nhanh đúng căn đang có
// trong kết quả; mã ngoài danh sách hiển thị chữ thường (không bấm được).
const ROOM_ID_PATTERN =
  /((?:chotot-\d+|synthetic-room-\d{1,3}|demo-\d{1,3}|room-[0-9a-f]{10}))/g;
function RoomRefText({
  text,
  rooms,
  onPick,
}: {
  text: string;
  rooms: Candidate[];
  onPick: (room: Candidate) => void;
}) {
  const parts = text.split(ROOM_ID_PATTERN);
  return (
    <p>
      {parts.map((part, index) => {
        const found = rooms.find((item) => item.room_id === part);
        return found ? (
          <button
            key={index}
            type="button"
            className="text-button"
            onClick={() => onPick(found)}
          >
            {part}
          </button>
        ) : (
          part
        );
      })}
    </p>
  );
}
// "Đã xử lý qua N bước" kiểu workspace tham chiếu: bung được các bước pipeline
// deterministic đã chạy thật (số liệu do máy chủ tính, không bịa).
function StepsDisclosure({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="steps-disclosure">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="sparkles" size={13} />
        Đã xử lý qua {steps.length} bước
        <span
          className={`steps-caret${open ? " open" : ""}`}
          aria-hidden="true"
        >
          <Icon name="chevron" size={12} />
        </span>
      </button>
      {open && (
        <ol>
          {steps.map((step, index) => (
            <li key={index}>{step}</li>
          ))}
        </ol>
      )}
    </div>
  );
}
// Nhãn tiếng Việt cho lý do bị loại trong diagnostics (thống nhất một chỗ).
const rejectionLabels: Record<string, string> = {
  city: "thành phố",
  area: "khu vực",
  room_type: "loại phòng",
  bedrooms: "số phòng ngủ",
  availability_or_capacity: "tình trạng còn trống/số người ở",
  required_amenity: "tiện ích bắt buộc",
  distance: "khoảng cách tới điểm đến",
  rent_budget: "giá thuê",
  monthly_budget: "trần tổng tháng",
  initial_budget: "tiền vào ở ban đầu",
  loan_principal: "kịch bản vay",
  loan_burden: "khả năng trả góp",
};
// Thông báo kho rỗng kiểu workspace tham chiếu: nói lại nhu cầu đã hiểu, nêu
// tiêu chí loại nhiều nhất, rồi đề nghị nới ĐÚNG MỘT tiêu chí do người dùng chọn.
function noMatchAnnouncement(result: Results, profile: Profile | null): string {
  const summary = result.diagnostics_summary;
  const lines: string[] = [];
  const recap: string[] = [];
  const place = [profile?.area, profile?.city].filter(Boolean).join(", ");
  if (place) recap.push(`khu ${place}`);
  if (profile?.max_monthly_cost_vnd)
    recap.push(`trần tổng tháng ${money(profile.max_monthly_cost_vnd)}`);
  const mustAmenities = (
    profile as unknown as { must_amenities?: string[] } | null
  )?.must_amenities?.length;
  if (mustAmenities) recap.push(`${mustAmenities} tiện ích bắt buộc`);
  if (recap.length) lines.push(`Nhu cầu mình đã nắm: ${recap.join(" · ")}.`);
  if (summary) {
    const held = Object.values(summary.verification ?? {}).reduce(
      (total, count) => total + count,
      0,
    );
    const reasons = Object.entries(summary.rejected ?? {})
      .sort((a, b) => b[1] - a[1])
      .slice(0, 3)
      .map(
        ([reason, count]) =>
          `${rejectionLabels[reason] ?? reason} (${count} tin)`,
      );
    const facts = [`Mình đã quét ${summary.scanned} tin trong kho.`];
    if (reasons.length)
      facts.push(
        `Chưa có căn khớp đồng thời — bị loại chủ yếu vì ${reasons.join(", ")}.`,
      );
    else facts.push("Chưa có căn nào khớp đồng thời các điều kiện của bạn.");
    if (held)
      facts.push(
        `Riêng ${held} tin bị giữ lại chờ xác minh số liệu (phí/vị trí) — chủ nhà cập nhật xong sẽ vào vòng sau.`,
      );
    lines.push(facts.join(" "));
  } else {
    lines.push("Kho hiện chưa có căn khớp đồng thời các điều kiện của bạn.");
  }
  lines.push(
    "Bạn muốn nới MỘT tiêu chí nào trước: ngân sách, khu vực, tiện ích hay khoảng cách? Bấm chip nới ở khung preview hoặc nhắn thẳng — mình chỉ nới đúng tiêu chí bạn chọn, không tự nới.",
  );
  return lines.join("\n\n");
}
export function RenterWorkspace({
  api,
  actor,
  tab,
  initialNeed = null,
  onNeedHandled,
}: {
  api: Api;
  actor: Actor;
  tab: string;
  initialNeed?: string | null;
  onNeedHandled?: () => void;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [result, setResult] = useState<Results | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Candidate[] | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [viewRoom, setViewRoom] = useState<Candidate | null>(null);
  const [simRoom, setSimRoom] = useState<Candidate | null>(null);
  const [viewings, setViewings] = useState<Viewing[]>([]);
  const [editing, setEditing] = useState(false);
  const [restoring, setRestoring] = useState(() =>
    Boolean(sessionStorage.getItem(`homematch.session.${actor.id}`)),
  );
  const [viewsLoading, setViewsLoading] = useState(false);
  // Bố cục workspace kiểu tham chiếu: cột chat cố định, khung preview gồm
  // bản đồ + danh sách đề xuất; "Nhu cầu của tôi" đè lên cột đề xuất.
  const [showMap, setShowMap] = useState(true);
  const [previewFull, setPreviewFull] = useState(false);
  const [sideView, setSideView] = useState<"rooms" | "profile">("rooms");
  const [sort, setSort] = useState<"match" | "price_asc" | "price_desc">(
    "match",
  );
  // Đánh giá câu trả lời chỉ lưu trên trình duyệt này, không gửi lên máy chủ.
  const [feedback, setFeedback] = useState<null | "up" | "down">(null);
  // WS-02: bước xử lý đang chạy theo sự kiện thật từ stream ("tên — mô tả").
  const [turnStep, setTurnStep] = useState<string | null>(null);
  // WS-01: view do agent chọn (map/list/detail/cost); null = bố cục kết hợp mặc định.
  const [agentView, setAgentView] = useState<
    null | "map" | "list" | "detail" | "cost"
  >(null);
  const [viewPayload, setViewPayload] = useState<Record<
    string,
    unknown
  > | null>(null);
  // Căn đã lưu của người thuê: nạp một lần khi vào workspace, tối ưu trên thẻ.
  const [savedIds, setSavedIds] = useState<string[]>([]);
  useEffect(() => {
    const version = epoch.current;
    api
      .get<{ id: string; room_id?: string }[]>("/rooms/saved")
      .then((items) => {
        if (live.current && version === epoch.current)
          setSavedIds(
            items.map((item) => item.room_id ?? item.id).filter(Boolean),
          );
      })
      .catch(() => {
        /* chưa lưu gì hoặc lỗi mạng: nút vẫn hoạt động khi bấm */
      });
  }, [api]);
  const messageInput = useRef<HTMLTextAreaElement>(null);
  const messageList = useRef<HTMLDivElement>(null);
  const viewsMarker = useRef(0);
  const needHandled = useRef(false);
  // Run đã thông báo kho rỗng trong quá trình chạy này (tránh lặp thông báo).
  const announcedRun = useRef<string | null>(null);
  const live = useRef(true),
    epoch = useRef(0),
    current = useRef<string | null>(null),
    lock = useRef(false),
    readMarker = useRef(0),
    resultRef = useRef(result);
  resultRef.current = result;
  useEffect(() => {
    const list = messageList.current;
    if (list) list.scrollTop = list.scrollHeight;
  }, [messages, busy]);
  useEffect(() => {
    live.current = true;
    return () => {
      live.current = false;
      epoch.current++;
    };
  }, []);
  const apply = useCallback(
    (value: Session) => {
      current.current = value.session_id;
      setSession(value);
      sessionStorage.setItem(`homematch.session.${actor.id}`, value.session_id);
    },
    [actor.id],
  );
  // Lịch sử lượt chat lưu theo phiên trên trình duyệt này: reload/quay lại
  // vẫn thấy hội thoại như workspace tham chiếu. Nội dung nhạy cảm vẫn do
  // máy chủ PII-mask khi lưu chính thức; đây chỉ là bản hiển thị tạm thời.
  const msgKey = useCallback(
    (sid: string) => `homematch.msgs.${actor.id}.${sid}`,
    [actor.id],
  );
  const putMessages = useCallback(
    (updater: (current: Message[]) => Message[]) => {
      setMessages((currentMessages) => {
        const next = updater(currentMessages);
        try {
          if (current.current)
            sessionStorage.setItem(
              msgKey(current.current),
              JSON.stringify(next),
            );
        } catch {
          /* vượt hạn mức sessionStorage thì bỏ qua, chat vẫn chạy */
        }
        return next;
      });
    },
    [msgKey],
  );
  const loadViews = useCallback(async () => {
    const e = epoch.current;
    const marker = ++viewsMarker.current;
    setViewsLoading(true);
    try {
      const rows = await api.get<Viewing[]>("/viewings");
      if (live.current && e === epoch.current && marker === viewsMarker.current)
        setViewings(rows);
    } catch (err) {
      if (live.current && e === epoch.current && marker === viewsMarker.current)
        setError((err as Error).message);
    } finally {
      if (live.current && marker === viewsMarker.current)
        setViewsLoading(false);
    }
  }, [api]);
  const refresh = useCallback(async () => {
    const sid = current.current;
    if (!sid) return;
    const e = epoch.current;
    const marker = ++readMarker.current;
    setLoading(true);
    try {
      const next = await api.get<Results>(`/sessions/${sid}/results`);
      if (
        live.current &&
        e === epoch.current &&
        current.current === sid &&
        marker === readMarker.current
      ) {
        const old = resultRef.current;
        if (
          old?.run_id !== next.run_id ||
          old?.status !== next.status ||
          !visibleStatuses.includes(next.status)
        ) {
          setSelected([]);
          setComparison(null);
          setViewRoom(null);
          setSimRoom(null);
        }
        setResult(next);
      }
    } catch (err) {
      if (live.current && e === epoch.current) setError((err as Error).message);
    } finally {
      if (live.current && e === epoch.current && marker === readMarker.current)
        setLoading(false);
    }
  }, [api]);
  useEffect(() => {
    const sid = sessionStorage.getItem(`homematch.session.${actor.id}`);
    if (!sid) return;
    let cancelled = false;
    const version = epoch.current;
    api
      .get<Session>(`/sessions/${sid}`)
      .then((s) => {
        if (!cancelled && live.current && version === epoch.current) {
          apply(s);
          // Khôi phục lượt chat đã lưu cục bộ cho phiên này (nếu có).
          try {
            const saved = sessionStorage.getItem(msgKey(s.session_id));
            if (saved) setMessages(JSON.parse(saved) as Message[]);
          } catch {
            /* dữ liệu lưu hỏng thì bắt đầu khung chat trống */
          }
          // Run đang mở đã có mặt trong lịch sử lưu: không thông báo rỗng lại.
          announcedRun.current = s.active_run_id ?? null;
        }
      })
      .catch((err) => {
        if (!cancelled && live.current && version === epoch.current) {
          sessionStorage.removeItem(`homematch.session.${actor.id}`);
          setError(err.message);
        }
      })
      .finally(() => {
        if (!cancelled && live.current && version === epoch.current)
          setRestoring(false);
      });
    return () => {
      cancelled = true;
    };
  }, [api, actor.id, apply, msgKey]);
  useEffect(() => {
    if (!session) return;
    void refresh();
  }, [session?.session_id, session?.active_run_id, refresh]);
  useEffect(() => {
    if (result?.status === "generating") return;
    let ticks = 0;
    const timer = setInterval(() => {
      if (++ticks > 60) {
        clearInterval(timer);
        return;
      }
      if (!lock.current && document.visibilityState !== "hidden")
        void refresh();
    }, 5000);
    return () => clearInterval(timer);
  }, [result?.status, result?.run_id, refresh]);
  useEffect(() => {
    if (tab === "viewings") void loadViews();
  }, [tab, loadViews]);
  const mutate = async (action: () => Promise<void>) => {
    if (lock.current) return false;
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      await action();
      return true;
    } catch (err) {
      if (live.current) {
        setError((err as Error).message);
        if (
          err instanceof ApiError &&
          (err.status === 409 || err.status === 0) &&
          current.current
        ) {
          const sid = current.current;
          try {
            const s = await api.get<Session>(`/sessions/${sid}`);
            if (live.current && sid === current.current) apply(s);
            await refresh();
          } catch {
            /* Preserve original failure. Read-only recovery can be retried manually. */
          }
        }
      }
      return false;
    } finally {
      lock.current = false;
      setTurnStep(null);
      if (live.current) setBusy(false);
    }
  };
  const create = () =>
    mutate(async () => {
      epoch.current++;
      setRestoring(false);
      current.current = null;
      setResult(null);
      setSelected([]);
      setComparison(null);
      setViewRoom(null);
      setSimRoom(null);
      setSideView("rooms");
      const s = await api.post<Session>("/sessions");
      if (live.current) {
        apply(s);
        putMessages(() => [
          {
            role: "assistant",
            text: "Bạn muốn tìm phòng ở đâu, cho bao nhiêu người và tổng ngân sách mỗi tháng là bao nhiêu?",
          },
        ]);
        setEditing(false);
      }
    });
  const sendText = (content: string) =>
    mutate(async () => {
      const sid = current.current;
      const value = content.trim();
      if (!sid || !value) return;
      // WS-02: ưu tiên stream bước xử lý; đứt luồng → thử lại ≤2 lần → fallback POST.
      const response = await api.turn<Session & { steps?: string[] }>(
        `/sessions/${sid}/messages`,
        {
          text: value,
          // WS-01: ngữ cảnh workspace để agent hiểu "căn này"/"căn thứ 2".
          workspace: {
            view: agentView,
            selected_room_id: selected[0] ?? null,
            visible_room_ids: resultList
              .map((item) => item.room_id)
              .slice(0, 30),
            focus_room_ids: selected.slice(0, 4),
          },
        },
        (step) => {
          if (live.current && current.current === sid)
            setTurnStep(`${step.name} — ${step.detail}`);
        },
      );
      if (live.current && current.current === sid) {
        setTurnStep(null);
        lastBudgetExplicit.current =
          (response as { budget_explicit?: boolean }).budget_explicit === true
            ? response.draft_revision
            : null;
        // WS-01: view do agent chọn — map/list/detail/cost áp dụng, keep giữ,
        // clear dọn workspace; view lạ bỏ qua giữ view cũ (an toàn theo hợp đồng).
        const nextView = (response as { view?: string }).view;
        if (
          nextView === "map" ||
          nextView === "list" ||
          nextView === "detail" ||
          nextView === "cost"
        )
          setAgentView(nextView);
        else if (nextView === "clear") {
          setAgentView(null);
          setSelected([]);
          setViewPayload(null);
        }
        setViewPayload(
          ((response as { view_payload?: Record<string, unknown> })
            .view_payload ?? null) as Record<string, unknown> | null,
        );
        apply(response);
        // AG-09: handover chủ nhà → chuyển sang Tin nhắn mở đúng hội thoại.
        const handover = response as {
          intent?: string;
          conversation_id?: string;
        };
        if (handover.intent === "landlord_handover" && handover.conversation_id)
          openConversation(handover.conversation_id, "/tin-nhan");
        putMessages((m) => [
          ...m,
          { role: "user", text: value },
          {
            role: "assistant",
            text:
              (response.answers?.length || response.house_rules?.length
                ? [
                    ...(response.house_rules || []),
                    ...(response.answers || []).map(
                      (entry) => `${entry.title}: ${entry.answer}`,
                    ),
                    response.disclaimer || "",
                  ]
                    .filter(Boolean)
                    .join("\n\n")
                : "") ||
              response.message ||
              response.questions?.join("\n") ||
              "Nhu cầu đã được ghi vào nháp. Kiểm tra biểu mẫu và xác nhận để tiếp tục.",
            // FE-07: kèm thẻ mô phỏng khi máy chủ trả status "simulation".
            simulation:
              response.status === "simulation"
                ? (response.simulation ?? null)
                : null,
            needsResults: response.status === "needs_results",
            // AG-11: chip làm rõ từ kho thật (render trên đầu câu trả lời).
            clarification:
              (response as { clarification?: Message["clarification"] })
                .clarification ?? null,
            // WS-02: "Đã xử lý qua N bước" bung được theo bước thật.
            steps: response.steps ?? undefined,
          },
        ]);
      }
    });
  // AG-11: bấm chip làm rõ → PATCH nháp với patch có cấu trúc (source=clarify,
  // server ghi confirmed kèm evidence clarify:rN); hiệu ứng tự xác nhận sẽ chạy
  // vòng tìm mới theo cách hiểu đã chọn. Không tự nới điều kiện cứng.
  const applyClarification = async (option: ClarificationOption) => {
    const sid = current.current;
    if (!sid || lock.current) return;
    try {
      await api.patch(`/sessions/${sid}/draft`, {
        expected_draft_revision: session?.draft_revision ?? 0,
        set: option.patch.set ?? {},
        clear_fields: [],
        remove_preferences: [],
        source: "clarify",
      });
      await refresh();
    } catch (err) {
      if (live.current) setError((err as Error).message);
    }
  };
  const send = async () => {
    const content = text.trim();
    if (!content) return;
    if (await sendText(content)) setText("");
  };
  // Màn trò chuyện mới: tạo phiên và gửi luôn câu đầu tiên trong một nhịp,
  // không có bước chặn "bắt đầu phiên"; lỗi bước nào cũng hiện qua notice.
  const [welcomeText, setWelcomeText] = useState("");
  const autoConfirmedRev = useRef<number | null>(null);
  // Nháp đã xử lý gần nhất của phiên: so với nháp mới để biết lượt chat vừa
  // đổi trường nào. Phiên vừa khôi phục chỉ lấy làm mốc, không tự chạy lại.
  const seenDraft = useRef<{ sid: string; draft: Draft } | null>(null);
  // AG-02: revision mà lượt chat vừa ghi mức tiền tuyệt đối/tương đối — chỉ
  // revision đó được phép đưa budget_hint vào trần khi tự xác nhận.
  const lastBudgetExplicit = useRef<number | null>(null);
  const createAndSend = async (content: string) => {
    const value = content.trim();
    if (!value || busy) return;
    if (await create()) {
      setWelcomeText("");
      await sendText(value);
    }
  };
  // Tự xác nhận nháp của trợ lý khi đã đủ dữ liệu tối thiểu (thành phố + ngân
  // sách): kết quả tự sinh như tham chiếu, không cần form. Lỗi (thiếu dữ liệu,
  // 409 đổi nháp) bỏ qua im lặng — trợ lý hỏi thêm và lượt sau thử lại với
  // draft_revision mới. Không dùng mutate để không bắn error notice làm nhiễu.
  // Đã có hồ sơ xác nhận thì lượt chat đổi nhu cầu xác nhận lại bản cập nhật
  // (profileUpdateFromChat) để chạy vòng tìm mới.
  useEffect(() => {
    if (!session || restoring) return;
    if (autoConfirmedRev.current === session.draft_revision) return;
    const sid = session.session_id;
    const draft = session.draft;
    const before =
      seenDraft.current?.sid === sid ? seenDraft.current.draft : null;
    const profile = !session.confirmed_profile
      ? profileFromDraft(draft)
      : before
        ? profileUpdateFromChat(
            session.confirmed_profile,
            before,
            draft,
            lastBudgetExplicit.current === session.draft_revision,
          )
        : null;
    if (!profile) {
      seenDraft.current = { sid, draft };
      return;
    }
    autoConfirmedRev.current = session.draft_revision;
    void (async () => {
      try {
        const res = await api.post<Results>(`/sessions/${sid}/confirm`, {
          expected_draft_revision: session.draft_revision,
          profile,
        });
        // Chỉ dời mốc khi xác nhận thành công: lỗi thì lượt sau so lại từ mốc
        // cũ nên thay đổi chưa áp dụng không bị mất.
        seenDraft.current = { sid, draft };
        const updated = await api.get<Session>(`/sessions/${sid}`);
        if (live.current && current.current === sid) {
          apply(updated);
          // Phản hồi xác nhận phải là Results thật (có mảng results) mới gắn
          // vào khung preview; sai cấu trúc thì bỏ để refresh tự kéo lại.
          if (Array.isArray(res.results)) setResult(res);
          setEditing(false);
        }
      } catch {
        /* im lặng: nháp chưa đủ hoặc vừa đổi; lượt chat sau thử lại */
      }
    })();
  }, [
    session?.session_id,
    session?.draft_revision,
    session?.confirmed_profile,
    restoring,
    api,
    apply,
  ]);
  // Nhu cầu khách chia sẻ trên trang chủ: mở phiên mới rồi gửi ngay câu đầu
  // tiên; nếu đã có phiên đang mở thì chỉ điền sẵn để khách quyết định gửi.
  useEffect(() => {
    if (!initialNeed || needHandled.current || restoring) return;
    needHandled.current = true;
    onNeedHandled?.();
    const need = initialNeed;
    if (sessionStorage.getItem(`homematch.session.${actor.id}`)) {
      setText(need);
      messageInput.current?.focus();
      return;
    }
    void (async () => {
      if (await create()) await sendText(need);
    })();
    // Chạy một lần sau khi việc khôi phục phiên kết thúc.
  }, [restoring]);
  const confirm = (profile: Profile) =>
    mutate(async () => {
      if (!session) return;
      epoch.current++;
      setResult(null);
      setComparison(null);
      setSelected([]);
      setViewRoom(null);
      setSimRoom(null);
      setSideView("rooms");
      const sid = session.session_id;
      const response = await api.post<Results>(`/sessions/${sid}/confirm`, {
        expected_draft_revision: session.draft_revision,
        profile,
      });
      const updated = await api.get<Session>(`/sessions/${sid}`);
      if (live.current && current.current === sid) {
        apply(updated);
        if (Array.isArray(response.results)) setResult(response);
        setEditing(false);
      }
    });
  const save = (
    values: Parameters<React.ComponentProps<typeof ProfileForm>["onSave"]>[0],
  ) =>
    mutate(async () => {
      if (!session) return;
      const sid = session.session_id;
      const s = await api.patch<Session>(`/sessions/${sid}/draft`, {
        expected_draft_revision: session.draft_revision,
        set: values,
        clear_fields: [],
        remove_preferences: [],
      });
      if (live.current && sid === current.current) {
        apply(s);
        putMessages((m) => [
          ...m,
          {
            role: "assistant",
            text: "Đã lưu điều chỉnh nháp. Ngân sách và kịch bản chỉ được xác nhận khi bạn chọn “Xác nhận & tìm phòng”.",
          },
        ]);
      }
    });
  const toggle = (id: string) => {
    setError(null);
    setComparison(null);
    setSelected((ids) => {
      if (ids.includes(id)) return ids.filter((x) => x !== id);
      if (ids.length >= 3) {
        setError(
          "Bạn chỉ có thể so sánh tối đa 3 phòng. Bỏ một lựa chọn để thêm phòng khác.",
        );
        return ids;
      }
      return [...ids, id];
    });
  };
  // Live chat with the room's landlord, carrying this session's context (smart handover).
  const chat = async (item: Candidate) => {
    if (!session) return;
    try {
      const conversation = await api.post<{ id: string }>("/conversations", {
        room_id: item.room_id,
        session_id: session.session_id,
      });
      openConversation(conversation.id, "/tin-nhan");
    } catch (err) {
      setError((err as Error).message);
    }
  };
  // Lưu/bỏ lưu căn: tối ưu giao diện trước, lỗi mạng thì hoàn tác lại.
  const toggleSave = (roomId: string) => {
    const savedNow = savedIds.includes(roomId);
    setSavedIds((ids) =>
      savedNow ? ids.filter((id) => id !== roomId) : [...ids, roomId],
    );
    const request = savedNow
      ? api.delete(`/rooms/${encodeURIComponent(roomId)}/save`)
      : api.put(`/rooms/${encodeURIComponent(roomId)}/save`, {});
    void request.catch(() => {
      if (!live.current) return;
      setError("Chưa cập nhật được trạng thái lưu — thử lại nhé.");
      setSavedIds((ids) =>
        savedNow ? [...ids, roomId] : ids.filter((id) => id !== roomId),
      );
    });
  };
  const compare = () =>
    mutate(async () => {
      if (!session || selected.length < 2) return;
      const sid = session.session_id;
      const version = epoch.current;
      const output = await api.post<{
        run_id: string;
        items: Candidate[];
        advice?: Advice | null;
      }>(`/sessions/${sid}/compare`, { room_ids: selected });
      if (
        live.current &&
        sid === current.current &&
        version === epoch.current &&
        output.run_id === result?.run_id
      ) {
        setComparison(output.items);
        setAdvice(output.advice ?? null);
      }
    });
  // Đánh giá câu trả lời: lưu trên máy (localStorage), không gửi máy chủ.
  useEffect(() => {
    if (!session) return;
    try {
      const saved = localStorage.getItem(`homematch.fb.${session.session_id}`);
      setFeedback(saved === "up" || saved === "down" ? saved : null);
    } catch {
      setFeedback(null);
    }
  }, [session?.session_id]);
  // Thông báo kho rỗng ngay trong khung chat khi run về no_match /
  // needs_verification — mỗi run chỉ thông báo một lần mỗi quá trình chạy.
  useEffect(() => {
    if (!result || busy) return;
    if (result.status !== "no_match" && result.status !== "needs_verification")
      return;
    if (announcedRun.current && announcedRun.current === result.run_id) return;
    announcedRun.current = result.run_id ?? null;
    putMessages((current) => [
      ...current,
      {
        role: "assistant",
        text: noMatchAnnouncement(result, session?.confirmed_profile ?? null),
      },
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result, busy]);
  // Sắp xếp tại máy khách trên danh sách đã duyệt; null giá xếp cuối.
  // Hook phải chạy ở cả nhánh lịch xem để thứ tự hook không đổi.
  const sortedResult = useMemo<Results | null>(() => {
    if (!result || sort === "match") return result;
    const weight = (value: number | null) =>
      value == null
        ? sort === "price_asc"
          ? Number.POSITIVE_INFINITY
          : Number.NEGATIVE_INFINITY
        : value;
    const items = [...result.results].sort((a, b) => {
      const diff =
        weight(a.cost.monthly_total_vnd) - weight(b.cost.monthly_total_vnd);
      return sort === "price_asc" ? diff : -diff;
    });
    return { ...result, results: items };
  }, [result, sort]);
  const rate = (value: "up" | "down") => {
    const next = feedback === value ? null : value;
    setFeedback(next);
    if (!session) return;
    try {
      if (next)
        localStorage.setItem(`homematch.fb.${session.session_id}`, next);
      else localStorage.removeItem(`homematch.fb.${session.session_id}`);
    } catch {
      /* trình duyệt chặn localStorage thì chỉ giữ trạng thái phiên */
    }
  };
  if (tab === "viewings")
    return (
      <>
        <div className="page-heading">
          <span className="eyebrow">THỜI GIAN DÀNH CHO NƠI Ở MỚI</span>
          <h1>Lịch xem phòng</h1>
          <p>
            Đề xuất của bạn được quản lý xác nhận trước khi trở thành lịch hẹn.
          </p>
        </div>
        <ErrorNotice error={error} onClose={() => setError(null)} />
        <section className="panel">
          <div className="section-heading">
            <h2>Yêu cầu của bạn</h2>
            <button
              className="button outline small"
              onClick={() => void loadViews()}
              disabled={viewsLoading}
            >
              <Icon name="refresh" size={16} />
              Đọc lại
            </button>
          </div>
          {viewsLoading && !viewings.length ? (
            <LoadingState label="Đang tải lịch xem phòng…" />
          ) : (
            <ViewingList items={viewings} />
          )}
        </section>
      </>
    );
  const resultVisible = Boolean(
    result && visibleStatuses.includes(result.status),
  );
  const lastAssistantIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--)
      if (messages[i].role === "assistant") return i;
    return -1;
  })();
  const resultList = sortedResult?.results ?? [];
  const pins = resultList.map((item) => ({
    id: item.room_id,
    title: item.title,
    latitude: item.latitude ?? null,
    longitude: item.longitude ?? null,
    uncertainty_m: item.uncertainty_m ?? null,
    location_accuracy: item.location_accuracy ?? "area_only",
    monthly: item.cost.monthly_total_vnd,
  }));
  if (restoring)
    return (
      <div className="agent-screen-load">
        <LoadingState label="Đang khôi phục phiên tư vấn…" />
      </div>
    );
  // Màn chào kiểu workspace tham chiếu: mascot, câu hỏi mở và composer lớn —
  // gõ câu đầu tiên là mở phiên và gửi luôn.
  if (!session)
    return (
      <main className="agent-welcome">
        <ErrorNotice error={error} onClose={() => setError(null)} />
        <div className="agent-mascot">
          <AgentMascot size={96} />
        </div>
        <h1 className="agent-welcome-title">
          Bạn đang tìm một <span>nơi ở</span> như thế nào?
        </h1>
        <p className="agent-welcome-sub">
          HomeMatch Agent giúp bạn tìm phòng nhanh, chính xác và tiết kiệm thời
          gian — chi phí rõ trước khi xem.
        </p>
        <form
          className="agent-hero-composer"
          onSubmit={(e) => {
            e.preventDefault();
            void createAndSend(welcomeText);
          }}
        >
          <label className="visually-hidden" htmlFor="welcome-need">
            Nhu cầu tìm phòng
          </label>
          <textarea
            id="welcome-need"
            rows={2}
            maxLength={2000}
            aria-label="Nhu cầu tìm phòng"
            placeholder="Ví dụ: tìm nhà trọ 4 triệu một tháng gần HUST, hoặc studio Quận 7 có cửa sổ…"
            value={welcomeText}
            onChange={(e) => setWelcomeText(e.target.value)}
            disabled={busy}
            onKeyDown={(e) => {
              if (
                e.key === "Enter" &&
                !e.shiftKey &&
                !e.nativeEvent.isComposing
              ) {
                e.preventDefault();
                if (!busy && welcomeText.trim())
                  void createAndSend(welcomeText);
              }
            }}
          />
          <div className="agent-hero-row">
            <div className="agent-hero-tools">
              <Link to="/tim-kiem" className="agent-hero-chip">
                <Icon name="search" size={14} /> Tìm nhanh
              </Link>
              <VoiceButton
                onText={(text) =>
                  setWelcomeText((prev) => (prev ? `${prev} ${text}` : text))
                }
                disabled={busy}
              />
            </div>
            <button
              className="agent-send"
              aria-label="Nhắn cho trợ lý"
              disabled={busy || !welcomeText.trim()}
            >
              <Icon name="send" size={17} />
            </button>
          </div>
        </form>
        <p className="agent-try">
          <Icon name="sparkles" size={14} /> Bạn có thể thử hỏi:
        </p>
        <div className="agent-try-cards">
          {[
            {
              icon: "cap",
              text: "Tìm phòng trọ dưới 4 triệu gần HUST",
            },
            {
              icon: "cap",
              text: "Phòng gần ĐH Kinh tế, ưu tiên có máy lạnh",
            },
            {
              icon: "sofa",
              text: "Studio có nội thất, gác lửng ở Quận 10",
            },
            {
              icon: "wallet",
              text: "Tính tổng chi phí thuê 3 triệu một tháng",
            },
          ].map((card) => (
            <button
              type="button"
              key={card.text}
              className="agent-try-card"
              disabled={busy}
              onClick={() => void createAndSend(card.text)}
            >
              <Icon name={card.icon} size={16} />
              <span>{card.text}</span>
            </button>
          ))}
        </div>
        <p className="agent-welcome-foot">
          Tin đang công khai · Chi phí rõ trước khi xem · Đặt lịch xem nhanh
        </p>
      </main>
    );
  return (
    <>
      <div className={`agent-shell${previewFull ? " preview-full" : ""}`}>
        <section className="agent-chat" aria-label="Trò chuyện với trợ lý">
          <header className="agent-chat-head">
            <span className="agent-ava">
              <AgentMascot size={32} />
            </span>
            <div className="agent-chat-id">
              <strong>HomeMatch Agent</strong>
              <small>
                <span className="dot-on" aria-hidden="true" /> Chỉ quét tin đang
                công khai trong kho HomeMatch
              </small>
            </div>
            <button
              type="button"
              className="rail-mini"
              aria-label="Nhu cầu của tôi"
              aria-pressed={sideView === "profile"}
              onClick={() =>
                setSideView(sideView === "profile" ? "rooms" : "profile")
              }
            >
              <Icon name="user" size={17} />
            </button>
            <button
              type="button"
              className="rail-mini"
              aria-label="Phiên mới"
              onClick={() => void create()}
              disabled={busy}
            >
              <Icon name="refresh" size={16} />
            </button>
          </header>
          <div className="agent-chat-body" aria-live="polite" ref={messageList}>
            {messages.length === 0 && !busy ? (
              <p className="subtle">
                Bạn có thể tiếp tục chia sẻ nhu cầu. Nội dung hội thoại không
                được lưu trên trình duyệt sau khi đăng xuất.
              </p>
            ) : (
              <>
                {busy && turnStep && (
                  <p
                    className="chat-turn-step"
                    role="status"
                    aria-live="polite"
                  >
                    Đang xử lý — bước: {turnStep}
                  </p>
                )}
                {messages.map((m, i) => (
                  <div className={`chat-message ${m.role}`} key={i}>
                    <span className="visually-hidden">
                      {m.role === "assistant" ? "Trợ lý HomeMatch" : "Bạn"}
                    </span>
                    {m.role === "assistant" && m.clarification && (
                      <div
                        className="chat-clarify"
                        role="group"
                        aria-label="Lựa chọn làm rõ"
                      >
                        <strong>{m.clarification.question}</strong>
                        <div className="relax-chips">
                          {m.clarification.options.map((option) => (
                            <button
                              key={option.id}
                              type="button"
                              className="button small outline"
                              onClick={() => void applyClarification(option)}
                            >
                              {option.label}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                    {m.role === "assistant" ? (
                      <RoomRefText
                        text={m.text}
                        rooms={resultList}
                        onPick={(room) => setViewRoom(room)}
                      />
                    ) : (
                      <p>{m.text}</p>
                    )}
                    {m.steps && m.steps.length > 0 && (
                      <StepsDisclosure steps={m.steps} />
                    )}
                    {m.simulation && (
                      <SimulationMessage simulation={m.simulation} />
                    )}
                    {m.needsResults && (
                      <button
                        type="button"
                        className="button small outline"
                        onClick={() => {
                          // Danh sách gợi ý thuộc phiên; về đúng màn list của
                          // khách rồi cuộn tới bảng kết quả (cùng cơ chế điều
                          // hướng với openConversation, không phụ thuộc provider).
                          setSideView("rooms");
                          setShowMap(true);
                          window.history.pushState(null, "", "/tro-ly-ai");
                          window.dispatchEvent(new PopStateEvent("popstate"));
                          document
                            .getElementById("results-panel")
                            ?.scrollIntoView({
                              behavior: "smooth",
                              block: "start",
                            });
                        }}
                      >
                        Xem danh sách gợi ý <Icon name="arrow" size={14} />
                      </button>
                    )}
                    {m.role === "assistant" &&
                      i === lastAssistantIdx &&
                      !busy && (
                        <div
                          className="chat-feedback"
                          aria-label="Đánh giá câu trả lời"
                        >
                          <button
                            type="button"
                            aria-label="Hữu ích"
                            aria-pressed={feedback === "up"}
                            title="Đánh giá chỉ lưu trên máy này"
                            onClick={() => rate("up")}
                          >
                            <Icon name="thumbUp" size={14} />
                          </button>
                          <button
                            type="button"
                            aria-label="Chưa hữu ích"
                            aria-pressed={feedback === "down"}
                            title="Đánh giá chỉ lưu trên máy này"
                            onClick={() => rate("down")}
                          >
                            <Icon name="thumbDown" size={14} />
                          </button>
                        </div>
                      )}
                  </div>
                ))}
              </>
            )}
            {busy && (
              <div className="chat-typing" role="status">
                <span aria-hidden="true">•••</span> Trợ lý đang xử lý…
              </div>
            )}
            {!busy && result?.steps?.length ? (
              <StepsDisclosure steps={result.steps} />
            ) : null}
            {resultVisible && showMap && (
              <div className="chat-sys-chip">
                <Icon name="pin" size={13} /> Đã mở bản đồ trong khung preview
              </div>
            )}
          </div>
          <div className="agent-chat-foot">
            <ErrorNotice error={error} onClose={() => setError(null)} />
            <form
              className="agent-composer"
              onSubmit={(e) => {
                e.preventDefault();
                void send();
              }}
            >
              <label className="visually-hidden" htmlFor="message">
                Nhu cầu của bạn
              </label>
              <textarea
                id="message"
                ref={messageInput}
                rows={1}
                maxLength={2000}
                placeholder="Nhắn cho HomeMatch Agent…"
                value={text}
                onChange={(e) => setText(e.target.value)}
                disabled={busy}
                onKeyDown={(e) => {
                  if (
                    e.key === "Enter" &&
                    !e.shiftKey &&
                    !e.nativeEvent.isComposing
                  ) {
                    e.preventDefault();
                    if (!busy && text.trim()) void send();
                  }
                }}
              />
              <VoiceButton
                onText={(voice) =>
                  setText((prev) => (prev ? `${prev} ${voice}` : voice))
                }
                disabled={busy}
              />
              <button
                className="agent-send"
                aria-label="Gửi nhu cầu"
                disabled={busy || !text.trim()}
              >
                <Icon name="send" size={17} />
              </button>
            </form>
            <div className="agent-quick" aria-label="Câu hỏi nhanh">
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void sendText(
                    "Tính giúp mình tổng chi phí thuê mỗi tháng và khoản ban đầu cho căn đầu tiên.",
                  )
                }
              >
                Tính tổng chi phí
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() =>
                  void sendText("Gợi ý thêm các căn tương tự căn đầu tiên.")
                }
              >
                Gợi ý căn tương tự
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void sendText("Mình muốn đổi khu vực tìm.")}
              >
                Đổi khu vực
              </button>
            </div>
            <p className="agent-hint">
              Enter để gửi · Shift + Enter xuống dòng · Ngân sách chốt trong
              “Nhu cầu của tôi”.
            </p>
          </div>
        </section>
        <section className="agent-preview" aria-label="Preview kết quả">
          <header className="agent-preview-head">
            <span className="agent-preview-tag">
              <Icon name="layers" size={15} /> PREVIEW
            </span>
            <div className="agent-preview-tools">
              <button
                type="button"
                aria-label="Danh sách đề xuất"
                aria-pressed={sideView === "rooms"}
                onClick={() => setSideView("rooms")}
              >
                <Icon name="grid" size={16} />
              </button>
              <button
                type="button"
                aria-label="Bản đồ"
                aria-pressed={showMap}
                disabled={!resultVisible}
                onClick={() => setShowMap((v) => !v)}
              >
                <Icon name="pin" size={16} />
              </button>
              <button
                type="button"
                aria-label="Toàn màn hình khung preview"
                aria-pressed={previewFull}
                onClick={() => setPreviewFull((v) => !v)}
              >
                <Icon name="expand" size={16} />
              </button>
            </div>
          </header>
          <div className="agent-preview-body" id="results-panel">
            {sideView === "profile" ? (
              <div className="agent-suggest agent-suggest-profile">
                <ProfileForm
                  key={session.session_id}
                  draft={session.draft}
                  revision={session.draft_revision}
                  confirmed={session.confirmed_profile}
                  confirmedVersion={session.profile_version}
                  busy={busy}
                  onConfirm={confirm}
                  onSave={save}
                  onDirty={setEditing}
                />
              </div>
            ) : !resultVisible && (busy || loading) ? (
              <PreviewSkeleton
                label={busy ? "Đang ghi nhớ nhu cầu…" : "Đang soạn danh sách…"}
              />
            ) : !resultVisible && result ? (
              <div className="agent-status-panel">
                <PublishedResults
                  result={result}
                  selected={selected}
                  onSelect={toggle}
                  onViewing={setViewRoom}
                  onSimulate={setSimRoom}
                  onChat={(item) => void chat(item)}
                  onAskFollowUp={(text) => {
                    // Điền câu nới vào ô chat; không tự gửi — người dùng đọc
                    // và quyết định, đúng nguyên tắc không tự nới điều kiện.
                    setText(text);
                    messageInput.current?.focus();
                  }}
                />
              </div>
            ) : (
              <div className="agent-results">
                {showMap && agentView !== "list" && (
                  <div className="agent-map">
                    <span className="agent-map-chip">
                      {resultList.length} căn phù hợp
                    </span>
                    <MapView pins={pins} />
                  </div>
                )}
                {(agentView === "detail" || agentView === "cost") && (
                  <div
                    className="agent-focus-view"
                    aria-label={
                      agentView === "detail"
                        ? "Chi tiết căn đang chọn"
                        : "Chi phí căn đang chọn"
                    }
                  >
                    <div className="agent-suggest-head">
                      <span>
                        {agentView === "detail"
                          ? "CHI TIẾT CĂN ĐANG CHỌN"
                          : "CHI PHÍ CĂN ĐANG CHỌN"}
                      </span>
                      <button
                        type="button"
                        className="text-button"
                        onClick={() => setAgentView(null)}
                      >
                        <Icon name="refresh" size={13} /> Bố cục thường
                      </button>
                    </div>
                    {(() => {
                      const focusedId =
                        selected[0] ??
                        (viewPayload?.room_id as string | undefined);
                      const focused =
                        resultList.find((item) => item.room_id === focusedId) ??
                        resultList[0];
                      if (!focused) return null;
                      return (
                        <>
                          <RoomCard
                            item={focused}
                            selected
                            onViewing={() => setViewRoom(focused)}
                            onSimulate={() => setSimRoom(focused)}
                            onChat={() => void chat(focused)}
                          />
                          <CostBreakdown cost={focused.cost} />
                        </>
                      );
                    })()}
                  </div>
                )}
                {agentView !== "map" && (
                  <div className="agent-suggest">
                    <div className="agent-suggest-head">
                      <span>SẮP XẾP:</span>
                      <select
                        value={sort}
                        aria-label="Sắp xếp danh sách"
                        onChange={(e) =>
                          setSort(
                            e.target.value as
                              | "match"
                              | "price_asc"
                              | "price_desc",
                          )
                        }
                      >
                        <option value="match">Phù hợp nhất</option>
                        <option value="price_asc">Giá thấp trước</option>
                        <option value="price_desc">Giá cao trước</option>
                      </select>
                      {agentView && (
                        <button
                          type="button"
                          className="text-button"
                          onClick={() => setAgentView(null)}
                        >
                          Bố cục thường
                        </button>
                      )}
                    </div>
                    <div className="agent-suggest-body">
                      {editing && resultVisible ? (
                        <p className="subtle">
                          Bạn đang điều chỉnh nhu cầu — xác nhận hồ sơ mới để
                          tìm lại. Gợi ý trước thuộc kịch bản đã xác nhận.
                        </p>
                      ) : (
                        <PublishedResults
                          result={sortedResult}
                          selected={selected}
                          onSelect={toggle}
                          onViewing={setViewRoom}
                          onSimulate={setSimRoom}
                          onChat={(item) => void chat(item)}
                          onAskFollowUp={(text) => {
                            setText(text);
                            messageInput.current?.focus();
                          }}
                          savedIds={savedIds}
                          onToggleSave={toggleSave}
                        />
                      )}
                      {!editing &&
                        resultVisible &&
                        (sortedResult?.results.length ?? 0) > 1 && (
                          <div className="compare-bar">
                            <span>
                              Đã chọn <strong>{selected.length}/3</strong> phòng
                            </span>
                            <button
                              className="button"
                              disabled={selected.length < 2 || busy}
                              onClick={() => void compare()}
                            >
                              <Icon name="compare" size={17} />
                              So sánh lựa chọn
                            </button>
                          </div>
                        )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        </section>
      </div>
      {comparison && !editing && (
        <Comparison
          items={comparison}
          advice={advice}
          onClose={() => setComparison(null)}
        />
      )}
      {simRoom &&
        !editing &&
        visibleStatuses.includes(result?.status ?? "") &&
        session.confirmed_profile && (
          <SimulationPanel
            key={simRoom.room_id}
            room={simRoom}
            sessionId={session.session_id}
            profile={session.confirmed_profile}
            api={api}
            onClose={() => setSimRoom(null)}
          />
        )}
      {viewRoom &&
        session &&
        !editing &&
        visibleStatuses.includes(result?.status ?? "") && (
          <ViewingForm
            room={viewRoom}
            sessionId={session.session_id}
            api={api}
            onCancel={() => setViewRoom(null)}
            onDone={() => {
              setViewRoom(null);
              void loadViews();
              putMessages((m) => [
                ...m,
                {
                  role: "assistant",
                  text: "Đã ghi nhận yêu cầu xem phòng. Bạn có thể theo dõi ở mục Lịch xem; lịch còn chờ quản lý xác nhận.",
                },
              ]);
            }}
          />
        )}
    </>
  );
}
