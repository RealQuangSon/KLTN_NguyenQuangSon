import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Api, ApiError } from "../api";
import { addressLine, visibleStatuses } from "../types";
import type {
  Actor,
  Candidate,
  ChatHistory,
  ChatSimulation,
  ChatTranscript,
  Draft,
  Profile,
  Results,
  RouteTravel,
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
import { coverPhotoSrc } from "../components/PhotoGallery";
import { MapView, type MapAnchor } from "../components/MapView";
import { ResizeHandle } from "../components/ResizeHandle";
import {
  RoutePanel,
  useRoomRoute,
  useSessionRoutes,
} from "../components/RoutePanel";
import { SimulationResults } from "../components/Simulation";
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
  source?: "model";
  // HN-13.2: "patch" áp patch cấu trúc; "text" GỬI câu đó (tiền đọc tất định).
  action?: "patch" | "text";
  text?: string | null;
};
type Message = {
  role: "user" | "assistant";
  text: string;
  // UX-06: tin của người dùng hiện ngay khi gửi; gửi lỗi thì đánh dấu để gửi lại.
  failed?: boolean;
  // AG-11: câu hỏi làm rõ kèm chip — render trên đầu câu trả lời.
  clarification?: {
    question: string;
    // HN-13.2: một câu vì sao câu trả lời làm đổi kết quả (model viết qua hậu
    // kiểm hoặc mẫu kho) — FE hiển thị nhỏ dưới câu hỏi.
    reason?: string | null;
    options: ClarificationOption[];
    decided_by: string;
    // Nhãn lựa chọn khách đã bấm: câu hỏi coi như đã trả lời, không vẽ lại nút.
    answered?: string | null;
  } | null;
  // HN-13.2: giả định engine tự áp, diễn đạt thành câu — hiển thị RIÊNG.
  assumptions?: string[] | null;
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
// Khung đang xử lý: bộ khung thẻ + mascot trạng thái
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
// UX-06: nhãn tiếng Việt cho bước đang chạy, ánh xạ một chỗ (không lộ tên tool).
const turnStepLabels: Record<string, string> = {
  route: "Đang đọc yêu cầu",
  update_needs: "Đang ghi nhu cầu",
  search_rooms: "Đang lọc kho phòng",
  confirm_and_search: "Đang xếp hạng",
};
const turnStepLabel = (name: string) => turnStepLabels[name] ?? "Đang xử lý";
// "Đã xử lý qua N bước": bung được các bước pipeline
// deterministic đã chạy thật (số liệu do máy chủ tính, không bịa).
// Dòng bước đã chạy: bỏ tên bước nội bộ, giữ phần mô tả tiếng Việt.
const stepText = (step: string) => {
  const at = step.indexOf(": ");
  if (at < 0) return step;
  const name = step.slice(0, at);
  return name in turnStepLabels || /^[a-z_]+$/.test(name)
    ? step.slice(at + 2)
    : step;
};
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
            <li key={index}>{stepText(step)}</li>
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
// Thông báo kho rỗng: nói lại nhu cầu đã hiểu, nêu
// tiêu chí loại nhiều nhất, rồi đề nghị nới ĐÚNG MỘT tiêu chí do người dùng chọn.
function noMatchAnnouncement(result: Results, profile: Profile | null): string {
  const summary = result.diagnostics_summary;
  const lines: string[] = [];
  const recap: string[] = [];
  const place = [profile?.area, profile?.city].filter(Boolean).join(", ");
  if (place) recap.push(`khu ${place}`);
  if (profile?.max_rent_vnd)
    recap.push(`tiền thuê đến ${money(profile.max_rent_vnd)}`);
  if (profile?.max_monthly_cost_vnd)
    recap.push(`trần tổng tháng ${money(profile.max_monthly_cost_vnd)}`);
  const mustAmenities = (
    profile as unknown as { must_amenities?: string[] } | null
  )?.must_amenities?.length;
  if (mustAmenities) recap.push(`${mustAmenities} tiện ích bắt buộc`);
  if (recap.length) lines.push(`Nhu cầu mình đã nắm: ${recap.join(" · ")}.`);
  if (summary) {
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
    lines.push(facts.join(" "));
  } else {
    lines.push("Kho hiện chưa có căn khớp đồng thời các điều kiện của bạn.");
  }
  lines.push(
    "Bạn muốn nới MỘT tiêu chí nào trước: ngân sách, khu vực, tiện ích hay khoảng cách? Bấm chip nới ở khung preview hoặc nhắn thẳng — mình chỉ nới đúng tiêu chí bạn chọn, không tự nới.",
  );
  return lines.join("\n\n");
}
const VN_ZONE = "Asia/Ho_Chi_Minh";
function vnDay(date: Date) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: VN_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
}
// "Hôm nay 14:05", "Hôm qua" hoặc "dd/mm", theo giờ Việt Nam.
export function chatTimeLabel(iso: string, now = new Date()) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const day = vnDay(date);
  if (day === vnDay(now))
    return `Hôm nay ${date.toLocaleTimeString("vi-VN", {
      timeZone: VN_ZONE,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    })}`;
  if (day === vnDay(new Date(now.getTime() - 86_400_000))) return "Hôm qua";
  return date.toLocaleDateString("vi-VN", {
    timeZone: VN_ZONE,
    day: "2-digit",
    month: "2-digit",
  });
}
export function RenterWorkspace({
  api,
  actor,
  tab,
  initialNeed = null,
  onNeedHandled,
  sideViewRequest = null,
  viewingsFilter = null,
}: {
  api: Api;
  actor: Actor;
  tab: string;
  initialNeed?: string | null;
  onNeedHandled?: () => void;
  // Route "Nhu cầu của tôi" (/nguoi-thue/nhu-cau) yêu cầu mở sẵn khung hồ sơ;
  // về /tro-ly-ai thì request về null và khung trả về danh sách đề xuất.
  sideViewRequest?: "profile" | null;
  // Route "Phòng xem trực tuyến" lọc lịch xem theo mode online.
  viewingsFilter?: "online" | null;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [result, setResult] = useState<Results | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  // HN-10: câu trả lời đang stream theo đoạn chữ (delta/replace từ NDJSON).
  const [streamText, setStreamText] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Thông báo thành công kiểu trang tìm kiếm: đặt lịch từ khung trợ lý xong phải
  // có dòng xác nhận kèm đường dẫn tới /nguoi-thue/lich-xem (hộp thoại chỉ đóng
  // là không đủ — bắt ở trình duyệt 14/11).
  const [notice, setNotice] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [comparison, setComparison] = useState<Candidate[] | null>(null);
  const [advice, setAdvice] = useState<Advice | null>(null);
  const [viewRoom, setViewRoom] = useState<Candidate | null>(null);
  const [viewings, setViewings] = useState<Viewing[]>([]);
  const [editing, setEditing] = useState(false);
  const [restoring, setRestoring] = useState(() =>
    Boolean(sessionStorage.getItem(`homematch.session.${actor.id}`)),
  );
  const [historyOpen, setHistoryOpen] = useState(false);
  const [history, setHistory] = useState<ChatHistory | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const historyMarker = useRef(0);
  const [recentAll, setRecentAll] = useState(false);
  const [viewsLoading, setViewsLoading] = useState(false);
  // Chưa tải xong lần đầu thì hiện "đang tải", không hiện trạng thái rỗng.
  const [viewsLoaded, setViewsLoaded] = useState(false);
  // Bố cục workspace: cột chat cố định, khung preview gồm
  // bản đồ + danh sách đề xuất; "Nhu cầu của tôi" đè lên cột đề xuất.
  const [showMap, setShowMap] = useState(true);
  const [previewFull, setPreviewFull] = useState(false);
  // Lọc lịch xem: "Tất cả" hoặc chỉ lịch trực tuyến (có phòng họp video). Mở
  // từ /lich-xem/truc-tuyen thì khởi tạo là trực tuyến.
  const [viewingsOnline, setViewingsOnline] = useState(
    viewingsFilter === "online",
  );
  useEffect(() => {
    setViewingsOnline(viewingsFilter === "online");
  }, [viewingsFilter]);
  // Chiều rộng do người dùng kéo (px); null = mặc định của CSS. Nhớ trong
  // trình duyệt để lần sau mở lại giữ nguyên bố cục.
  const [layout, setLayout] = useState<{
    chat: number | null;
    map: number | null;
  }>(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("homematch.agentLayout") ?? "{}",
      ) as { chat?: unknown; map?: unknown };
      return {
        chat: typeof saved.chat === "number" ? saved.chat : null,
        map: typeof saved.map === "number" ? saved.map : null,
      };
    } catch {
      return { chat: null, map: null };
    }
  });
  const updateLayout = (patch: Partial<typeof layout>) =>
    setLayout((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem("homematch.agentLayout", JSON.stringify(next));
      } catch {
        // Không lưu được (chế độ riêng tư): bố cục chỉ giữ trong phiên này.
      }
      return next;
    });
  const shellRef = useRef<HTMLDivElement>(null);
  const chatPanelRef = useRef<HTMLElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const mapPanelRef = useRef<HTMLDivElement>(null);
  const [sideView, setSideView] = useState<"rooms" | "profile">(
    sideViewRequest ?? "rooms",
  );
  // Đổi route giữa /nguoi-thue/nhu-cau và /tro-ly-ai không dựng lại component
  // (cùng key), nên phải theo dõi request để khung cạnh chuyển đúng lúc.
  useEffect(() => {
    setSideView(sideViewRequest ?? "rooms");
  }, [sideViewRequest]);
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
  // Agent mở chi tiết/chi phí một căn: khung này nằm dưới bản đồ nên phải cuộn
  // tới, nếu không câu "đã mở sẵn căn đó bên cạnh" không thấy gì đổi trên màn hình.
  const focusViewRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (agentView === "detail" || agentView === "cost")
      focusViewRef.current?.scrollIntoView?.({
        behavior: "smooth",
        block: "nearest",
      });
  }, [agentView, viewPayload]);
  // Căn đã lưu của người thuê: nạp một lần khi vào workspace, tối ưu trên thẻ.
  const [savedIds, setSavedIds] = useState<string[]>([]);
  // Liên kết hai chiều thẻ ↔ marker: mapFocusId là lựa chọn bền (bấm marker
  // hoặc thẻ), cardHoverId chỉ nổi trong lúc hover thẻ — không cuộn trang.
  const [mapFocusId, setMapFocusId] = useState<string | null>(null);
  // Căn đang vẽ đường đi tới điểm neo. Chỉ đặt khi khách bấm marker trên bản
  // đồ (chủ động muốn xem đường); bấm thẻ trong danh sách chỉ mở chi tiết căn.
  const [routeRoomId, setRouteRoomId] = useState<string | null>(null);
  const [cardHoverId, setCardHoverId] = useState<string | null>(null);
  // Căn đang mở ở khung chi tiết (bấm thẻ nhỏ); null = chưa mở từ thẻ.
  const [detailId, setDetailId] = useState<string | null>(null);
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
  // vẫn thấy hội thoại. Nội dung nhạy cảm vẫn do
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
  // Ưu tiên bản lưu trên trình duyệt (giữ nút chọn làm rõ); không có thì lấy
  // nội dung đã che PII từ máy chủ để mở lại cuộc trò chuyện cũ.
  const loadMessages = useCallback(
    async (sid: string, stillCurrent: () => boolean) => {
      try {
        const saved = sessionStorage.getItem(msgKey(sid));
        if (saved) {
          setMessages(JSON.parse(saved) as Message[]);
          return;
        }
      } catch {
        /* dữ liệu lưu hỏng thì lấy từ máy chủ */
      }
      try {
        const transcript = await api.get<ChatTranscript>(
          `/sessions/${sid}/transcript`,
        );
        if (!stillCurrent() || !Array.isArray(transcript?.messages)) return;
        const list: Message[] = transcript.messages.map((item) => ({
          role: item.role,
          text: item.text,
        }));
        setMessages(list);
        try {
          if (list.length)
            sessionStorage.setItem(msgKey(sid), JSON.stringify(list));
        } catch {
          /* vượt hạn mức sessionStorage thì bỏ qua */
        }
      } catch {
        /* không đọc được thì khung chat để trống, người thuê vẫn nhắn tiếp */
      }
    },
    [api, msgKey],
  );
  const loadViews = useCallback(async () => {
    const e = epoch.current;
    const marker = ++viewsMarker.current;
    setViewsLoading(true);
    try {
      // Lịch xem thuộc tài khoản, không thuộc phiên chat: đổi phiên (epoch) giữa
      // lúc tải KHÔNG được bỏ kết quả, nếu không trang hiện "chưa có lịch" sai.
      const rows = await api.get<Viewing[]>("/viewings");
      if (live.current && marker === viewsMarker.current) setViewings(rows);
    } catch (err) {
      if (live.current && e === epoch.current && marker === viewsMarker.current)
        setError((err as Error).message);
    } finally {
      if (live.current && marker === viewsMarker.current) {
        setViewsLoading(false);
        setViewsLoaded(true);
      }
    }
  }, [api]);
  // background: đọc lại định kỳ, không báo "đang tải" để khung kết quả không nhấp nháy.
  const refresh = useCallback(
    async (background = false) => {
      const sid = current.current;
      if (!sid) return;
      const e = epoch.current;
      const marker = ++readMarker.current;
      if (!background) setLoading(true);
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
          }
          setResult(next);
        }
      } catch (err) {
        if (live.current && e === epoch.current)
          setError((err as Error).message);
      } finally {
        if (
          live.current &&
          e === epoch.current &&
          marker === readMarker.current
        )
          setLoading(false);
      }
    },
    [api],
  );
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
          // Khôi phục lượt chat: bản lưu cục bộ, không có thì bản của máy chủ.
          void loadMessages(
            s.session_id,
            () => live.current && version === epoch.current,
          );
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
  }, [api, actor.id, apply, loadMessages]);
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
        void refresh(true);
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
      // HN-10: lượt hỏng thì bỏ dở phần chữ đang stream.
      setStreamText(null);
      setTurnStep(null);
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
  // withFirstMessage: phiên mở kèm câu đầu thì không chèn câu chào (UX-06).
  const create = (withFirstMessage = false) =>
    mutate(async () => {
      epoch.current++;
      setRestoring(false);
      current.current = null;
      setResult(null);
      setSelected([]);
      setComparison(null);
      setViewRoom(null);
      setSideView("rooms");
      const s = await api.post<Session>("/sessions");
      if (live.current) {
        apply(s);
        putMessages(() =>
          withFirstMessage
            ? []
            : [
                {
                  role: "assistant",
                  text: "Bạn muốn tìm phòng ở đâu, cho bao nhiêu người và tổng ngân sách mỗi tháng là bao nhiêu?",
                },
              ],
        );
        setEditing(false);
        setHistoryOpen(false);
      }
    });
  const loadHistory = useCallback(async () => {
    const marker = ++historyMarker.current;
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const data = await api.get<ChatHistory>("/sessions");
      if (
        live.current &&
        marker === historyMarker.current &&
        Array.isArray(data?.items)
      )
        setHistory(data);
    } catch (err) {
      if (live.current && marker === historyMarker.current)
        setHistoryError((err as Error).message);
    } finally {
      if (live.current && marker === historyMarker.current)
        setHistoryLoading(false);
    }
  }, [api]);
  useEffect(() => {
    if (!historyOpen) return;
    void loadHistory();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setHistoryOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [historyOpen, loadHistory]);
  // Màn chào: nạp danh sách một lần để người thuê quay lại thấy chat cũ.
  const onWelcome = !session && !restoring;
  useEffect(() => {
    if (onWelcome) void loadHistory();
  }, [onWelcome, loadHistory]);
  const openSession = (sid: string) => {
    if (sid === current.current) {
      setHistoryOpen(false);
      return Promise.resolve(false);
    }
    return mutate(async () => {
      const before = epoch.current;
      const s = await api.get<Session>(`/sessions/${sid}`);
      if (!live.current || before !== epoch.current) return;
      const e = ++epoch.current;
      setRestoring(false);
      current.current = null;
      setResult(null);
      setSelected([]);
      setComparison(null);
      setViewRoom(null);
      setSideView("rooms");
      setAgentView(null);
      setViewPayload(null);
      setStreamText(null);
      setDetailId(null);
      setMapFocusId(null);
      setRouteRoomId(null);
      setCardHoverId(null);
      setEditing(false);
      setFeedback(null);
      setNotice(null);
      setAdvice(null);
      setMessages([]);
      apply(s);
      announcedRun.current = s.active_run_id ?? null;
      setHistoryOpen(false);
      await loadMessages(sid, () => live.current && e === epoch.current);
    });
  };
  const sendText = (content: string) =>
    mutate(async () => {
      const sid = current.current;
      const value = content.trim();
      if (!sid || !value) return;
      // UX-06: hiện tin của người dùng ngay; gửi lại thì thay bản lỗi cũ.
      putMessages((m) => [
        ...m.filter((item) => !(item.failed && item.text === value)),
        { role: "user", text: value },
      ]);
      try {
        await runTurn(sid, value);
      } catch (err) {
        if (live.current && current.current === sid)
          putMessages((m) =>
            m.map((item, index) =>
              index === m.length - 1 &&
              item.role === "user" &&
              item.text === value
                ? { ...item, failed: true }
                : item,
            ),
          );
        throw err;
      }
    });
  const runTurn = async (sid: string, value: string) => {
    // WS-02: ưu tiên stream bước xử lý; đứt luồng → thử lại ≤2 lần → fallback POST.
    const response = await api.turn<Session & { steps?: string[] }>(
      `/sessions/${sid}/messages`,
      {
        text: value,
        // WS-01: ngữ cảnh workspace để agent hiểu "căn này"/"căn thứ 2".
        workspace: {
          view: agentView,
          selected_room_id: selected[0] ?? null,
          visible_room_ids: resultList.map((item) => item.room_id).slice(0, 30),
          focus_room_ids: selected.slice(0, 4),
        },
      },
      (step) => {
        if (live.current && current.current === sid)
          setTurnStep(turnStepLabel(step.name));
      },
      (event) => {
        // HN-10: delta nối dần câu trả lời; replace thay toàn bộ khi hậu kiểm
        // phát hiện vi phạm (số bịa/guard) — done vẫn là nguồn sự thật cuối.
        if (!live.current || current.current !== sid) return;
        if (event.type === "replace") setStreamText(event.text);
        else setStreamText((text) => (text ?? "") + event.text);
      },
    );
    if (live.current && current.current === sid) {
      setTurnStep(null);
      setStreamText(null);
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
      // Gợi ý trả lời đổi theo nháp mới ngay cả khi lượt này chưa tạo run.
      void refresh(true);
    }
  };
  // AG-11: bấm chip làm rõ → PATCH nháp với patch có cấu trúc (source=clarify,
  // server ghi confirmed kèm evidence clarify:rN); hiệu ứng tự xác nhận sẽ chạy
  // vòng tìm mới theo cách hiểu đã chọn. Không tự nới điều kiện cứng.
  const applyClarification = async (
    option: ClarificationOption,
    index: number,
  ) => {
    const sid = current.current;
    if (!sid || lock.current) return;
    if (option.source === "model" || option.action === "text") {
      // HN-13.2: chip chữ (kể cả field=other patch rỗng) GỬI ĐÚNG câu đó —
      // bấm vào phải làm việc thật, không PATCH rỗng rồi đứng im.
      await sendText(option.text || option.label);
      return;
    }
    // Phản hồi ngay: lựa chọn hiện như câu trả lời của khách, nút biến mất và có
    // dòng "đang xử lý" — việc tìm lại có thể mất vài giây.
    const markAnswered = (messagesNow: Message[]) =>
      messagesNow.map((message, position) =>
        position === index && message.clarification
          ? {
              ...message,
              clarification: {
                ...message.clarification,
                answered: option.label,
              },
            }
          : message,
      );
    await mutate(async () => {
      putMessages((currentMessages) => [
        ...markAnswered(currentMessages),
        { role: "user", text: option.label },
      ]);
      setTurnStep("Đang tìm lại theo lựa chọn của bạn");
      try {
        const patched = await api.patch<{
          message?: string | null;
          clarification?: Message["clarification"];
        }>(`/sessions/${sid}/draft`, {
          expected_draft_revision: session?.draft_revision ?? 0,
          set: option.patch.set ?? {},
          clear_fields: [],
          remove_preferences: [],
          source: "clarify",
        });
        // Backend đã tự xác nhận và xếp hạng trong cùng yêu cầu: đọc lại phiên + kết quả.
        const updated = await api.get<Session>(`/sessions/${sid}`);
        if (live.current && current.current === sid) {
          apply(updated);
          // Câu trả lời THẬT của máy chủ: đã tìm (kèm số căn) hoặc câu hỏi tiếp
          // theo kèm nút.
          const reply =
            patched?.message ||
            "Mình đã tìm lại theo lựa chọn này — danh sách bên cạnh đã cập nhật.";
          putMessages((currentMessages) => [
            ...currentMessages,
            {
              role: "assistant",
              text: reply,
              clarification: patched?.clarification ?? null,
            },
          ]);
        }
        await refresh();
      } catch (err) {
        // Lỗi: trả nút về để bấm lại, bỏ câu trả lời tạm.
        if (live.current && current.current === sid)
          putMessages((currentMessages) =>
            currentMessages.slice(0, -1).map((message, position) =>
              position === index && message.clarification
                ? {
                    ...message,
                    clarification: {
                      ...message.clarification,
                      answered: undefined,
                    },
                  }
                : message,
            ),
          );
        throw err;
      }
    });
  };
  const send = async () => {
    const content = text.trim();
    if (!content) return;
    if (lock.current) return;
    setText("");
    await sendText(content);
  };
  // Màn trò chuyện mới: tạo phiên và gửi luôn câu đầu tiên trong một nhịp,
  // không có bước chặn "bắt đầu phiên"; lỗi bước nào cũng hiện qua notice.
  const [welcomeText, setWelcomeText] = useState("");
  const createAndSend = async (content: string) => {
    const value = content.trim();
    if (!value || busy) return;
    if (await create(true)) {
      setWelcomeText("");
      await sendText(value);
    }
  };
  // UX-02: tự xác nhận + xếp hạng do BACKEND làm ngay trong lượt chat/chip; frontend
  // không dựng hồ sơ nữa, chỉ đọc lại phiên và kết quả sau mỗi lượt.
  // Nhu cầu khách chia sẻ trên trang chủ: mở phiên mới rồi gửi ngay câu đầu
  // tiên; nếu đã có phiên đang mở thì chỉ điền sẵn để khách quyết định gửi.
  useEffect(() => {
    if (!initialNeed || needHandled.current || restoring) return;
    needHandled.current = true;
    const need = initialNeed;
    if (sessionStorage.getItem(`homematch.session.${actor.id}`)) {
      onNeedHandled?.();
      setText(need);
      messageInput.current?.focus();
      return;
    }
    // Chỉ xoá nhu cầu chờ sau khi câu đã gửi xong (UX-05).
    void (async () => {
      if (await create(true)) await sendText(need);
      onNeedHandled?.();
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
  // Sắp xếp tại máy khách trên danh sách đã công bố; null giá xếp cuối.
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
  // MP-01: điểm neo = điểm đến của hồ sơ đã xác nhận (trường, công ty, địa
  // điểm khách muốn ở gần). Chỉ vẽ khi kết quả đang hiện thuộc đúng phiên bản
  // hồ sơ đó. Hook đặt trước mọi nhánh return để thứ tự hook không đổi.
  const destination = session?.confirmed_profile?.destination ?? null;
  const anchorMatchesResult =
    result?.profile_version == null ||
    result.profile_version === session?.profile_version;
  const mapAnchor = useMemo<MapAnchor | null>(
    () =>
      destination && anchorMatchesResult
        ? {
            label: destination.label,
            latitude: destination.latitude,
            longitude: destination.longitude,
            radius_m: destination.max_distance_m,
          }
        : null,
    [destination, anchorMatchesResult],
  );
  const [routeTravel, setRouteTravel] = useState<RouteTravel>("ride");
  // Đường đi chỉ theo căn khách bấm trên bản đồ, không theo hover hay thẻ.
  const routeRoom =
    mapAnchor && routeRoomId
      ? (result?.results.find((item) => item.room_id === routeRoomId) ?? null)
      : null;
  // Địa chỉ căn đang chọn (đường, phường, quận) lấy từ tin đăng công khai; chưa
  // có hoặc lỗi thì dùng quận/thành phố đã có trong kết quả xếp hạng.
  const [roomAddresses, setRoomAddresses] = useState<Record<string, string>>(
    {},
  );
  const routeRoomId_ = routeRoom?.room_id ?? null;
  useEffect(() => {
    if (!routeRoomId_ || roomAddresses[routeRoomId_] !== undefined) return;
    let alive = true;
    api
      .get<Parameters<typeof addressLine>[0]>(
        `/listings/${encodeURIComponent(routeRoomId_)}`,
      )
      .then((room) => {
        if (alive)
          setRoomAddresses((prev) => ({
            ...prev,
            [routeRoomId_]: addressLine(room),
          }));
      })
      .catch(() => {
        if (alive)
          setRoomAddresses((prev) => ({ ...prev, [routeRoomId_]: "" }));
      });
    return () => {
      alive = false;
    };
  }, [api, routeRoomId_, roomAddresses]);
  const routeState = useRoomRoute(
    api,
    session?.session_id ?? null,
    routeRoom?.room_id ?? null,
    result?.run_id ?? null,
    routeTravel,
  );
  const mapRoute =
    routeRoom && routeState.route?.room_id === routeRoom.room_id
      ? {
          coordinates: routeState.route.geometry.coordinates,
          straight: routeState.route.provider === "straight_line",
        }
      : null;
  // cả danh sách lấy quãng đường/thời gian tới điểm neo bằng MỘT
  // request /routes cho mỗi cặp (lượt tìm, chế độ đi); số liệu hiện trên thẻ
  // căn và bảng so sánh, dùng chung chế độ đi với bảng chỉ đường nên đổi ở đó
  // thì thẻ đổi theo.
  const sessionRoutesEnabled =
    Boolean(mapAnchor) &&
    result?.status === "published" &&
    (result?.results.length ?? 0) > 0;
  const sessionRoutes = useSessionRoutes(
    api,
    session?.session_id ?? null,
    result?.run_id ?? null,
    routeTravel,
    sessionRoutesEnabled,
  );
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
  if (tab === "viewings") {
    // Lọc "Trực tuyến": chỉ hiện lịch có phòng họp video (mode online).
    const shownViewings = viewingsOnline
      ? viewings.filter((view) => view.mode === "online")
      : viewings;
    return (
      <>
        <div className="page-heading">
          <span className="eyebrow">THỜI GIAN DÀNH CHO NƠI Ở MỚI</span>
          <h1>Lịch xem phòng</h1>
          <p>
            Đây là thời gian bạn mong muốn. Bên phụ trách tin (chủ nhà hoặc bộ
            phận điều phối với tin từ tin đăng gốc) sẽ xác nhận hoặc đề xuất giờ
            khác.
          </p>
        </div>
        <ErrorNotice error={error} onClose={() => setError(null)} />
        <section className="panel">
          <div className="section-heading">
            <h2>Yêu cầu của bạn</h2>
            <div className="segmented" role="group" aria-label="Lọc lịch xem">
              <button
                type="button"
                className={viewingsOnline ? "choice" : "choice active"}
                aria-pressed={!viewingsOnline}
                onClick={() => setViewingsOnline(false)}
              >
                Tất cả
              </button>
              <button
                type="button"
                className={viewingsOnline ? "choice active" : "choice"}
                aria-pressed={viewingsOnline}
                onClick={() => setViewingsOnline(true)}
              >
                Trực tuyến
              </button>
            </div>
            <button
              className="button outline small"
              onClick={() => void loadViews()}
              disabled={viewsLoading}
            >
              <Icon name="refresh" size={16} />
              Đọc lại
            </button>
          </div>
          {(viewsLoading || !viewsLoaded) && !shownViewings.length ? (
            <LoadingState label="Đang tải lịch xem phòng…" />
          ) : (
            <ViewingList
              items={shownViewings}
              onFeedback={(id, rating, note) => {
                void mutate(async () => {
                  await api.post(`/viewings/${id}/feedback`, {
                    rating,
                    note: note || null,
                  });
                  await loadViews();
                });
              }}
              onAction={(id, action) => {
                void mutate(async () => {
                  // choose_time gửi giờ mới (ngày mai,
                  // khung sáng, +07:00) để máy chủ cập nhật requested_at thật.
                  const body =
                    action === "choose_time"
                      ? {
                          action,
                          requested_at: new Date(
                            `${new Date(Date.now() + 86400000)
                              .toISOString()
                              .slice(0, 10)}T08:00:00+07:00`,
                          ).toISOString(),
                          time_slot: "morning",
                        }
                      : { action };
                  await api.post(`/viewings/${id}/actions`, body);
                  await loadViews();
                });
              }}
            />
          )}
        </section>
      </>
    );
  }
  const resultVisible = Boolean(
    result && visibleStatuses.includes(result.status),
  );
  const lastAssistantIdx = (() => {
    for (let i = messages.length - 1; i >= 0; i--)
      if (messages[i].role === "assistant") return i;
    return -1;
  })();
  const resultList = sortedResult?.results ?? [];
  const mapVisible = showMap && agentView !== "list";
  // Chip do máy chủ chọn theo trạng thái phiên; lượt có chip làm rõ thì chỉ hiện chip đó.
  const replyPrompts = messages[messages.length - 1]?.clarification
    ? []
    : (result?.suggested_prompts ?? []);
  const pins = resultList.map((item) => ({
    id: item.room_id,
    title: item.title,
    latitude: item.latitude ?? null,
    longitude: item.longitude ?? null,
    uncertainty_m: item.uncertainty_m ?? null,
    location_accuracy: item.location_accuracy ?? "area_only",
    monthly: item.cost.monthly_total_vnd,
    area: item.area,
    city: item.city,
    area_m2: item.area_m2,
    bedrooms: item.bedrooms ?? null,
    room_type: item.room_type ?? null,
    // Ảnh bìa cho popup marker (Candidate chỉ có source_images — displayPhotos
    // tự ghép; không có ảnh thì popup giữ hình minh họa).
    photoUrl: coverPhotoSrc(item),
  }));
  // Bấm marker: làm nổi thẻ tương ứng, cuộn tới thẻ trong danh sách và vẽ
  // đường đi từ căn đó tới điểm neo.
  const handleMapSelect = (id: string) => {
    setMapFocusId(id);
    setRouteRoomId(id);
    const card = document.querySelector(`[data-room-id="${CSS.escape(id)}"]`);
    card?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };
  // Bấm thẻ nhỏ: mở khung chi tiết (đánh đổi, cần xác minh, bảng phí, chat,
  // đặt lịch) và làm nổi marker tương ứng; không tự vẽ đường đi. Đang có
  // đường của căn khác thì gỡ, để bản đồ không chỉ đường cho căn không xem.
  const openDetail = (item: Candidate) => {
    setDetailId(item.room_id);
    setMapFocusId(item.room_id);
    setRouteRoomId((current) => (current === item.room_id ? current : null));
    setAgentView("detail");
  };
  const mapSelectedId = cardHoverId ?? mapFocusId;
  if (restoring)
    return (
      <div className="agent-screen-load">
        <LoadingState label="Đang khôi phục phiên tư vấn…" />
      </div>
    );
  // Màn chào: mascot, câu hỏi mở và composer lớn —
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
        {!historyLoading && !historyError && history?.items.length ? (
          <section
            className="agent-recent"
            aria-label="Cuộc trò chuyện gần đây"
          >
            <h2>Cuộc trò chuyện gần đây</h2>
            <ul>
              {(recentAll ? history.items : history.items.slice(0, 5)).map(
                (item) => (
                  <li key={item.session_id}>
                    <button
                      type="button"
                      className="chat-history-row"
                      disabled={busy}
                      onClick={() => void openSession(item.session_id)}
                    >
                      <span className="chat-history-title">{item.title}</span>
                      <small>
                        {chatTimeLabel(item.last_at)} · {item.turns} lượt
                      </small>
                    </button>
                  </li>
                ),
              )}
            </ul>
            {!recentAll && history.items.length > 5 && (
              <button
                type="button"
                className="button small outline"
                onClick={() => setRecentAll(true)}
              >
                Xem tất cả ({history.items.length})
              </button>
            )}
          </section>
        ) : null}
        <p className="agent-welcome-foot">
          Tin đang công khai · Chi phí rõ trước khi xem · Đặt lịch xem nhanh
        </p>
      </main>
    );
  return (
    <>
      <div
        ref={shellRef}
        className={`agent-shell${previewFull ? " preview-full" : ""}`}
        style={
          layout.chat != null
            ? ({ "--chat-w": `${layout.chat}px` } as React.CSSProperties)
            : undefined
        }
      >
        <section
          ref={chatPanelRef}
          className={`agent-chat${historyOpen ? " history-open" : ""}`}
          aria-label="Trò chuyện với trợ lý"
        >
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
              aria-label="Lịch sử trò chuyện"
              aria-expanded={historyOpen}
              aria-pressed={historyOpen}
              onClick={() => setHistoryOpen((open) => !open)}
            >
              <Icon name="clock" size={17} />
            </button>
            <button
              type="button"
              className="rail-mini"
              aria-label="Cuộc trò chuyện mới"
              onClick={() => void create()}
              disabled={busy}
            >
              <Icon name="plus" size={17} />
            </button>
          </header>
          <div className="agent-chat-body" aria-live="polite" ref={messageList}>
            {messages.length === 0 && !busy ? (
              <p className="subtle">
                Bạn có thể tiếp tục chia sẻ nhu cầu. Các cuộc trò chuyện cũ nằm
                trong Lịch sử trò chuyện.
              </p>
            ) : (
              <>
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
                        {m.clarification.reason && (
                          <small className="chat-clarify-reason">
                            {m.clarification.reason}
                          </small>
                        )}
                        {/* Nút chỉ còn hiệu lực ở câu hỏi mới nhất và chưa trả lời;
                            câu hỏi cũ giữ lại dòng chữ, không giữ nút bấm được. */}
                        {m.clarification.answered ? (
                          <small className="chat-clarify-reason chat-answered">
                            Đã chọn: {m.clarification.answered}
                          </small>
                        ) : (
                          i === messages.length - 1 && (
                            <div className="relax-chips">
                              {m.clarification.options.map((option) => (
                                <button
                                  key={option.id}
                                  type="button"
                                  className="button small outline"
                                  onClick={() =>
                                    void applyClarification(option, i)
                                  }
                                >
                                  {option.label}
                                </button>
                              ))}
                            </div>
                          )
                        )}
                      </div>
                    )}
                    {m.role === "assistant" ? (
                      // Lời trả lời trùng nguyên câu hỏi của chip thì không in lần hai.
                      m.clarification?.question.trim() ===
                      m.text.trim() ? null : (
                        <RoomRefText
                          text={m.text}
                          rooms={resultList}
                          onPick={(room) => setViewRoom(room)}
                        />
                      )
                    ) : (
                      <p>{m.text}</p>
                    )}
                    {m.role === "user" && m.failed && (
                      <p className="chat-send-failed" role="alert">
                        Chưa gửi được.{" "}
                        <button
                          type="button"
                          className="button small outline"
                          onClick={() => void sendText(m.text)}
                        >
                          Gửi lại
                        </button>
                      </p>
                    )}
                    {m.assumptions && m.assumptions.length > 0 && (
                      <p className="chat-assumptions">
                        {m.assumptions.join(" ")} Bạn có thể sửa trong “Nhu cầu
                        của tôi”.
                      </p>
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
                {busy && streamText && (
                  <div className="chat-message assistant">
                    <span className="visually-hidden">Trợ lý HomeMatch</span>
                    <div
                      className="chat-bubble theirs"
                      aria-live="polite"
                      data-testid="stream-text"
                    >
                      {streamText}
                    </div>
                  </div>
                )}
              </>
            )}
            {busy && (
              <div className="chat-typing" role="status">
                <span aria-hidden="true">•••</span>{" "}
                {turnStep ? `${turnStep}…` : "Trợ lý đang xử lý…"}
              </div>
            )}
            {!busy &&
            result?.steps?.length &&
            !messages.some((m) => m.steps?.length) ? (
              <StepsDisclosure steps={result.steps} />
            ) : null}
          </div>
          <div className="agent-chat-foot">
            <ErrorNotice error={error} onClose={() => setError(null)} />
            {notice && (
              <div className="notice success" role="status">
                {notice} <Link to="/nguoi-thue/lich-xem">Xem lịch đã gửi</Link>
              </div>
            )}
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
            {replyPrompts.length > 0 && (
              <div
                className="agent-quick"
                role="group"
                aria-label="Gợi ý trả lời"
              >
                {replyPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    disabled={busy}
                    onClick={() => void sendText(prompt)}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            )}
            <p className="agent-hint">
              Enter để gửi · Shift + Enter xuống dòng · Ngân sách chốt trong
              “Nhu cầu của tôi”.
            </p>
          </div>
          {historyOpen && (
            <div
              className="chat-history"
              role="region"
              aria-label="Lịch sử trò chuyện"
            >
              <div className="chat-history-head">
                <strong>Lịch sử trò chuyện</strong>
                <button
                  type="button"
                  className="rail-mini"
                  aria-label="Đóng lịch sử"
                  onClick={() => setHistoryOpen(false)}
                >
                  <Icon name="close" size={16} />
                </button>
              </div>
              <button
                type="button"
                className="button primary chat-history-new"
                onClick={() => void create()}
                disabled={busy}
              >
                <Icon name="plus" size={16} /> Cuộc trò chuyện mới
              </button>
              <div className="chat-history-list">
                {historyLoading && !history ? (
                  <LoadingState label="Đang tải lịch sử…" />
                ) : historyError ? (
                  <div className="chat-history-empty" role="alert">
                    <p>{historyError}</p>
                    <button
                      type="button"
                      className="button small outline"
                      onClick={() => void loadHistory()}
                    >
                      Thử lại
                    </button>
                  </div>
                ) : history && history.items.length === 0 ? (
                  <p className="chat-history-empty">
                    Chưa có cuộc trò chuyện nào được lưu.
                  </p>
                ) : (
                  <ul>
                    {(history?.items ?? []).map((item) => {
                      const isCurrent = item.session_id === session?.session_id;
                      return (
                        <li key={item.session_id}>
                          <button
                            type="button"
                            className="chat-history-row"
                            aria-current={isCurrent ? "true" : undefined}
                            disabled={busy}
                            onClick={() => void openSession(item.session_id)}
                          >
                            <span className="chat-history-title">
                              {item.title}
                            </span>
                            <small>
                              {chatTimeLabel(item.last_at)} · {item.turns} lượt
                            </small>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
              {history && (
                <p className="chat-history-note">
                  Hội thoại được lưu {history.retention_days} ngày; số điện
                  thoại, email… đã được ẩn.
                </p>
              )}
            </div>
          )}
        </section>
        {!previewFull && (
          <ResizeHandle
            label="Đổi chiều rộng khung trò chuyện"
            getSize={() => chatPanelRef.current?.offsetWidth ?? 440}
            min={320}
            max={() => (shellRef.current?.offsetWidth ?? 1200) - 560}
            onChange={(px) => updateLayout({ chat: px })}
            onReset={() => updateLayout({ chat: null })}
          />
        )}
        <section className="agent-preview" aria-label="Preview kết quả">
          <header className="agent-preview-head">
            <span className="agent-preview-tag">
              <Icon name="layers" size={15} /> PREVIEW
            </span>
            <div className="agent-preview-tools">
              <button
                type="button"
                aria-label="Bản đồ"
                aria-pressed={mapVisible}
                disabled={!resultVisible}
                onClick={() => {
                  // Agent đang chọn dạng danh sách thì bấm là mở bản đồ, không phải tắt.
                  setSideView("rooms");
                  if (agentView === "list") {
                    setAgentView(null);
                    setShowMap(true);
                  } else setShowMap((v) => !v);
                }}
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
                  onChat={(item) => void chat(item)}
                  routes={sessionRoutes.byRoom}
                  routeSkipped={sessionRoutes.skipped}
                  anchorLabel={mapAnchor?.label}
                  routeAttribution={sessionRoutes.attribution}
                  onAskFollowUp={(text) => {
                    // Điền câu nới vào ô chat; không tự gửi — người dùng đọc
                    // và quyết định, đúng nguyên tắc không tự nới điều kiện.
                    setText(text);
                    messageInput.current?.focus();
                  }}
                />
              </div>
            ) : (
              <div
                ref={resultsRef}
                className="agent-results"
                style={
                  layout.map != null
                    ? ({ "--map-w": `${layout.map}px` } as React.CSSProperties)
                    : undefined
                }
              >
                {mapVisible && (
                  <div ref={mapPanelRef} className="agent-map">
                    <span className="agent-map-chip">
                      {resultList.length} căn phù hợp
                    </span>
                    <MapView
                      pins={pins}
                      selectedId={mapSelectedId}
                      onSelect={handleMapSelect}
                      savedIds={savedIds}
                      onToggleSave={toggleSave}
                      anchor={mapAnchor}
                      route={mapRoute}
                      overlay={
                        mapAnchor ? (
                          <RoutePanel
                            anchor={mapAnchor}
                            roomAddress={
                              routeRoom
                                ? roomAddresses[routeRoom.room_id] ||
                                  `${routeRoom.area}, ${routeRoom.city}`
                                : null
                            }
                            state={routeState}
                            travel={routeTravel}
                            onTravel={setRouteTravel}
                            onClose={() => setRouteRoomId(null)}
                          />
                        ) : undefined
                      }
                    />
                  </div>
                )}
                {(agentView === "detail" || agentView === "cost") && (
                  <div
                    ref={focusViewRef}
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
                        onClick={() => {
                          setAgentView(null);
                          setDetailId(null);
                        }}
                      >
                        <Icon name="back" size={13} /> Quay lại
                      </button>
                    </div>
                    {(() => {
                      const focusedId =
                        detailId ??
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
                            onChat={() => void chat(focused)}
                          />
                          <CostBreakdown cost={focused.cost} />
                        </>
                      );
                    })()}
                  </div>
                )}
                {mapVisible && (
                  <ResizeHandle
                    label="Đổi chiều rộng bản đồ"
                    getSize={() => mapPanelRef.current?.offsetWidth ?? 480}
                    min={280}
                    max={() => (resultsRef.current?.offsetWidth ?? 1000) - 330}
                    onChange={(px) => updateLayout({ map: px })}
                    onReset={() => updateLayout({ map: null })}
                  />
                )}
                {/* Khung chi tiết (bấm thẻ) thay thế danh sách: bản đồ bên
                    trái giữ nguyên, chi tiết chiếm cột phải. View "list" do
                    agent chọn vẫn hiện danh sách (bản đồ đã ẩn). */}
                {(agentView === null || agentView === "list") && (
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
                          <Icon name="back" size={13} /> Quay lại
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
                          onChat={(item) => void chat(item)}
                          routes={sessionRoutes.byRoom}
                          routeSkipped={sessionRoutes.skipped}
                          anchorLabel={mapAnchor?.label}
                          routeAttribution={sessionRoutes.attribution}
                          onAskFollowUp={(text) => {
                            setText(text);
                            messageInput.current?.focus();
                          }}
                          savedIds={savedIds}
                          onToggleSave={toggleSave}
                          highlightId={mapSelectedId}
                          onHoverCard={setCardHoverId}
                          onOpenCard={openDetail}
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
          routes={sessionRoutes.byRoom}
          routeSkipped={sessionRoutes.skipped}
          anchorLabel={mapAnchor?.label}
          travel={routeTravel}
          onClose={() => setComparison(null)}
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
              setNotice(
                "Đã gửi lịch xem mong muốn. Bên phụ trách tin (chủ nhà hoặc điều phối với tin từ tin gốc) sẽ xác nhận hoặc đề xuất giờ khác; theo dõi ở mục Lịch xem.",
              );
              putMessages((m) => [
                ...m,
                {
                  role: "assistant",
                  text: "Đã ghi nhận yêu cầu xem phòng. Bạn có thể theo dõi ở mục Lịch xem; lịch còn chờ xác nhận của bên phụ trách tin.",
                },
              ]);
            }}
          />
        )}
    </>
  );
}
