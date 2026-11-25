import {
  Fragment,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Api, ApiError } from "./api";
import type { Actor, Role } from "./types";
import { landlordPendingNote, roleNames } from "./types";
import { Icon } from "./components/Shared";
import { RenterWorkspace } from "./pages/RenterWorkspace";
import { LandlordWorkspace } from "./pages/LandlordWorkspace";
import { SearchPage } from "./pages/SearchPage";
import { HandbookPage } from "./pages/Handbook";
import { InboxPage } from "./pages/Inbox";
import { PublicListing } from "./pages/PublicListing";
import { NotificationBell } from "./components/NotificationBell";
import { AccountMenu } from "./components/AccountMenu";
import { LandlordAgentDock } from "./components/LandlordAgentDock";
import {
  BillingPage,
  LandlordDashboard,
  LeasesPage,
  MaintenancePage,
  UsagePage,
} from "./pages/Pms";
import { RenterOverview } from "./pages/RenterOverview";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { SavedPage } from "./pages/Saved";
import { AdminWorkspace, type AdminSection } from "./pages/AdminWorkspace";
import { AccountPage } from "./pages/Account";
import { Forbidden, NotFound } from "./pages/StatusPages";
import { RouterProvider, Redirect, useRouter } from "./router";
import { Brand } from "./components/Brand";
import { LoadingState } from "./components/LoadingState";
import { clearLocal, clearLoginStorage } from "./session-storage";
// FE-02: điều hướng theo route (deep link, back/forward) thay state tab.
// Route UI theo UI_SPEC mục 3; màn chưa có API v1 là khung trung thực.
type AppRoute =
  | { kind: "landing" }
  | { kind: "login" }
  | { kind: "register" }
  | {
      kind: "renter";
      tab: "search" | "viewings";
      // "Nhu cầu của tôi" (/nguoi-thue/nhu-cau) mở thẳng khung hồ sơ nhu cầu
      // trong màn trợ lý; "Phòng xem trực tuyến" lọc lịch xem theo mode online.
      focus?: "profile";
      filter?: "online";
    }
  | { kind: "saved"; tab?: "saved" | "viewed" }
  | { kind: "listings" }
  | { kind: "handbook" }
  | { kind: "inbox" }
  | { kind: "public-listing"; id: string }
  | {
      kind: "pms";
      page: "dashboard" | "leases" | "billing" | "maintenance" | "usage";
      side: "landlord" | "renter";
    }
  | { kind: "landlord"; tab: "catalog" | "viewings" }
  // Trang đã bỏ: deep link cũ chuyển hẳn sang trang thay thế (URL đổi theo).
  | { kind: "redirect"; to: string }
  | { kind: "admin"; section: AdminSection }
  | { kind: "account"; section: "ho-so" | "bao-mat" }
  | { kind: "not-found" };
const publicKinds = ["landing", "login", "register"];
const routeRoles: Partial<Record<AppRoute["kind"], Role[]>> = {
  renter: ["renter"],
  saved: ["renter"],
  listings: ["renter"],
  handbook: ["renter"],
  inbox: ["renter", "owner"],
  pms: ["renter", "owner"],
  landlord: ["owner"],
  redirect: ["owner"],
  admin: ["admin"],
  account: ["renter", "owner", "admin"],
};
const roleHomes: Record<Role, string> = {
  renter: "/nguoi-thue/tong-quan",
  owner: "/chu-nha/tong-quan",
  admin: "/quan-tri/hoi-thoai",
};
const avatarInitials: Record<Role, string> = {
  renter: "NT",
  owner: "CN",
  admin: "QT",
};
const workspaceLabels: Record<Role, string> = {
  renter: "KHÔNG GIAN NGƯỜI THUÊ",
  owner: "KHÔNG GIAN CHỦ NHÀ",
  admin: "KHÔNG GIAN QUẢN TRỊ",
};
const breadcrumbRoles: Record<Role, string> = {
  renter: "Không gian của bạn",
  owner: "Chủ nhà",
  admin: "Quản trị",
};
// also: các đường dẫn khác cùng sáng mục này (trang gộp nhiều lối vào).
type NavItem = { path: string; label: string; icon: string; also?: string[] };
// Sidebar nhóm theo cụm mục: nhóm có nhãn thì
// hiện tiêu đề mục, nhóm không nhãn nằm đầu/cuối danh sách. Trợ lý AI không nằm
// trong sidebar — là màn riêng, chỉ mở qua nút "Hỏi trợ lý AI"/nút nổi.
type NavGroup = { label?: string; items: NavItem[] };
const navByRole: Record<Role, NavGroup[]> = {
  renter: [
    {
      items: [
        { path: "/nguoi-thue/tong-quan", label: "Tổng quan", icon: "home" },
      ],
    },
    {
      label: "TÌM CHỖ Ở",
      items: [
        {
          path: "/nguoi-thue/nhu-cau",
          label: "Nhu cầu của tôi",
          icon: "target",
        },
        {
          path: "/nguoi-thue/da-luu",
          label: "Đã lưu & đã xem",
          icon: "heart",
          also: ["/nguoi-thue/phong-da-xem"],
        },
        {
          path: "/nguoi-thue/lich-xem",
          label: "Lịch xem phòng",
          icon: "calendar",
          also: ["/nguoi-thue/lich-xem/truc-tuyen"],
        },
      ],
    },
    {
      label: "PHÒNG ĐANG THUÊ",
      items: [
        { path: "/nguoi-thue/hop-dong", label: "Hợp đồng", icon: "contract" },
        {
          path: "/nguoi-thue/hoa-don",
          label: "Hóa đơn & thanh toán",
          icon: "wallet",
        },
        { path: "/nguoi-thue/chi-phi", label: "Chi phí sử dụng", icon: "coin" },
        {
          path: "/nguoi-thue/sua-chua",
          label: "Yêu cầu sửa chữa",
          icon: "wrench",
        },
      ],
    },
    {
      items: [
        { path: "/tai-khoan/ho-so", label: "Hồ sơ", icon: "user" },
        { path: "/cam-nang", label: "Trung tâm trợ giúp", icon: "book" },
      ],
    },
  ],
  owner: [
    {
      items: [{ path: "/chu-nha/tong-quan", label: "Tổng quan", icon: "home" }],
    },
    {
      label: "NHÀ CỦA BẠN",
      items: [
        { path: "/chu-nha/phong", label: "Phòng & tin", icon: "grid" },
        { path: "/chu-nha/lich-xem", label: "Lịch xem", icon: "calendar" },
        { path: "/chu-nha/hop-thu", label: "Hộp thư", icon: "mail" },
      ],
    },
    {
      label: "PHÒNG ĐANG CHO THUÊ",
      items: [
        { path: "/chu-nha/hop-dong", label: "Hợp đồng", icon: "contract" },
        {
          path: "/chu-nha/hoa-don",
          label: "Hóa đơn & công nợ",
          icon: "wallet",
        },
        { path: "/chu-nha/sua-chua", label: "Sửa chữa", icon: "wrench" },
      ],
    },
    {
      items: [{ path: "/tai-khoan/ho-so", label: "Hồ sơ", icon: "user" }],
    },
  ],
  admin: [
    {
      items: [
        { path: "/quan-tri/hoi-thoai", label: "Hội thoại AI", icon: "chat" },
        {
          path: "/quan-tri/chuyen-giao",
          label: "Chuyển giao",
          icon: "compare",
        },
        { path: "/quan-tri/ho-tro", label: "Yêu cầu hỗ trợ", icon: "clock" },
        { path: "/quan-tri/tai-khoan", label: "Người dùng", icon: "user" },
        { path: "/quan-tri/tin-dang", label: "Tin đăng", icon: "home" },
        {
          path: "/quan-tri/dieu-phoi",
          label: "Điều phối lịch xem",
          icon: "calendar",
        },
        { path: "/quan-tri/van-hanh", label: "Vận hành", icon: "refresh" },
        { path: "/tai-khoan/ho-so", label: "Hồ sơ", icon: "shield" },
      ],
    },
  ],
};
function resolveRoute(rawPath: string): AppRoute {
  const path = rawPath.replace(/\/+$/, "") || "/";
  switch (path) {
    case "/":
      return { kind: "landing" };
    case "/dang-nhap":
      return { kind: "login" };
    case "/dang-ky":
      return { kind: "register" };
    case "/nguoi-thue/tong-quan":
      return { kind: "pms", page: "dashboard", side: "renter" };
    case "/tro-ly-ai":
      return { kind: "renter", tab: "search" };
    case "/nguoi-thue/nhu-cau":
      return { kind: "renter", tab: "search", focus: "profile" };
    case "/nguoi-thue/lich-xem":
      return { kind: "renter", tab: "viewings" };
    case "/nguoi-thue/lich-xem/truc-tuyen":
      return { kind: "renter", tab: "viewings", filter: "online" };
    case "/nguoi-thue/da-luu":
      return { kind: "saved", tab: "saved" };
    case "/nguoi-thue/phong-da-xem":
      return { kind: "saved", tab: "viewed" };
    case "/nguoi-thue/chi-phi":
      return { kind: "pms", page: "usage", side: "renter" };
    case "/tim-kiem":
      return { kind: "listings" };
    case "/cam-nang":
      return { kind: "handbook" };
    case "/tin-nhan":
    case "/chu-nha/hop-thu":
      return { kind: "inbox" };
    case "/chu-nha/tong-quan":
      return { kind: "pms", page: "dashboard", side: "landlord" };
    case "/chu-nha/hop-dong":
      return { kind: "pms", page: "leases", side: "landlord" };
    case "/chu-nha/hoa-don":
      return { kind: "pms", page: "billing", side: "landlord" };
    case "/chu-nha/sua-chua":
      return { kind: "pms", page: "maintenance", side: "landlord" };
    case "/nguoi-thue/hop-dong":
      return { kind: "pms", page: "leases", side: "renter" };
    case "/nguoi-thue/hoa-don":
      return { kind: "pms", page: "billing", side: "renter" };
    case "/nguoi-thue/sua-chua":
      return { kind: "pms", page: "maintenance", side: "renter" };
    // Đã bỏ: trang duyệt gợi ý (05/11/2026) và Khách tiềm năng (19/11/2026).
    case "/chu-nha/duyet-goi-y":
    case "/chu-nha/khach-tiem-nang":
      return { kind: "redirect", to: "/chu-nha/tong-quan" };
    case "/chu-nha/phong":
      return { kind: "landlord", tab: "catalog" };
    case "/chu-nha/lich-xem":
      return { kind: "landlord", tab: "viewings" };
    case "/quan-tri/hoi-thoai":
    case "/quan-tri/chuyen-giao":
    case "/quan-tri/ho-tro":
    case "/quan-tri/tai-khoan":
    case "/quan-tri/tin-dang":
    case "/quan-tri/dieu-phoi":
    case "/quan-tri/van-hanh":
      return {
        kind: "admin",
        section: path.split("/")[2] as AdminSection,
      };
    case "/tai-khoan/ho-so":
      return { kind: "account", section: "ho-so" };
    case "/tai-khoan/bao-mat":
      return { kind: "account", section: "bao-mat" };
    default:
      if (path.startsWith("/tin/") && path.split("/").length === 3)
        return {
          kind: "public-listing",
          id: decodeURIComponent(path.split("/")[2]),
        };
      return { kind: "not-found" };
  }
}
export default function App() {
  return (
    <RouterProvider>
      <AppShell />
    </RouterProvider>
  );
}
function AppShell() {
  const { path, navigate } = useRouter();
  const route = resolveRoute(path);
  const [token, setToken] = useState<string | null>(() =>
      sessionStorage.getItem("homematch.token"),
    ),
    [actor, setActor] = useState<Actor | null>(null),
    [boot, setBoot] = useState(Boolean(token)),
    [error, setError] = useState<string | null>(null),
    [pendingNeed, setPendingNeed] = useState<string | null>(null);
  // Thanh điều hướng thu gọn hay mở rộng là lựa chọn của người dùng, giữ nguyên
  // khi chuyển trang (chỉ trong bộ nhớ, không ghi storage). Người thuê mặc định
  // thu gọn để màn trợ lý đủ chỗ cho chat + bản đồ; chủ nhà/quản trị mở rộng.
  const [navCollapsed, setNavCollapsed] = useState<Record<Role, boolean>>({
    renter: true,
    owner: false,
    admin: false,
  });
  const currentToken = useRef(token);
  currentToken.current = token;
  // Token vừa nhận từ phản hồi đăng nhập: actor đã có, không cần màn "boot" kiểm
  // /auth/me (nó gỡ RenterWorkspace giữa lúc đang gửi nhu cầu từ trang chủ).
  const trustedToken = useRef<string | null>(null);
  const clear = useCallback(() => {
    currentToken.current = null;
    trustedToken.current = null;
    clearLocal();
    setToken(null);
    setActor(null);
    setPendingNeed(null);
  }, []);
  const api = useMemo(
    () =>
      new Api(token, () => {
        if (currentToken.current !== token) return;
        clear();
        navigate("/dang-nhap", { replace: true });
        setError("Phiên đăng nhập đã hết hiệu lực. Vui lòng đăng nhập lại.");
      }),
    [token, clear, navigate],
  );
  useEffect(() => {
    if (!token) {
      setBoot(false);
      return;
    }
    if (trustedToken.current === token) {
      setBoot(false);
      return;
    }
    let active = true;
    setBoot(true);
    api
      .get<Actor>("/auth/me")
      .then((value) => {
        if (active) {
          setActor(value);
          setError(null);
        }
      })
      .catch((err) => {
        if (active) {
          clear();
          setError(err.message);
        }
      })
      .finally(() => {
        if (active) setBoot(false);
      });
    return () => {
      active = false;
    };
  }, [api, token, clear]);
  const onAuthenticated = useCallback(
    (accessToken: string, nextActor: Actor) => {
      // Đăng nhập/chuyển trải nghiệm: xoá dữ liệu riêng tư nhưng giữ khoá phiên
      // tư vấn của từng tài khoản để quay lại vai là dùng được trợ lý ngay.
      clearLoginStorage();
      sessionStorage.setItem("homematch.token", accessToken);
      currentToken.current = accessToken;
      trustedToken.current = accessToken;
      setToken(accessToken);
      setActor(nextActor);
      setError(null);
      // Nhu cầu chia sẻ trên trang chủ chỉ áp dụng cho người thuê; vai trò
      // khác đăng nhập thì bỏ nhu cầu pending như hành vi cũ. Có nhu cầu thì
      // đi thẳng vào màn trợ lý để mở phiên mới, không thì về Tổng quan.
      if (nextActor.role !== "renter") setPendingNeed(null);
      navigate(
        nextActor.role === "renter" && pendingNeed
          ? "/tro-ly-ai"
          : roleHomes[nextActor.role],
      );
    },
    [clear, navigate, pendingNeed],
  );
  const logout = async () => {
    const previous = api;
    clear();
    navigate("/dang-nhap", { replace: true });
    try {
      await previous.post("/auth/logout");
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401))
        setError(
          "Đã xóa phiên trên thiết bị. Chưa kết nối được máy chủ để thu hồi token; token sẽ hết hạn theo cấu hình server.",
        );
    }
  };
  // Trang tin công khai (đích link chia sẻ) xem được dù đã hay chưa đăng nhập.
  if (route.kind === "public-listing")
    return <PublicListing roomId={route.id} />;
  if (boot)
    return (
      <div className="boot">
        <Brand />
        <LoadingState label="Đang kiểm tra phiên đăng nhập…" />
      </div>
    );
  if (!actor)
    return publicKinds.includes(route.kind) ? (
      route.kind === "landing" ? (
        <Landing
          onLogin={() => {
            setError(null);
            navigate("/dang-nhap");
          }}
          onNeed={(need) => {
            setPendingNeed(need);
            navigate("/dang-nhap");
          }}
        />
      ) : route.kind === "login" ? (
        <Login
          error={error}
          onError={setError}
          pendingNeed={pendingNeed}
          onAuthenticated={onAuthenticated}
          onBack={() => {
            setPendingNeed(null);
            setError(null);
            navigate("/");
          }}
        />
      ) : (
        <Register />
      )
    ) : (
      // Deep link vào khu vực cần đăng nhập khi chưa có phiên: đưa tới đăng
      // nhập, không flash dữ liệu và không giả định quyền.
      <Redirect to="/dang-nhap" />
    );
  // Màn auth sau khi đã có phiên: đưa về cổng đúng vai trò. Riêng trang chủ
  // giữ nguyên — người đã đăng nhập vẫn xem được landing,
  // CTA chuyển thành "mở trợ lý" thay vì đăng nhập lại.
  if (route.kind === "login" || route.kind === "register")
    return <Redirect to={roleHomes[actor.role]} />;
  if (route.kind === "landing")
    return (
      <Landing
        loggedIn
        account={{
          api,
          initials: avatarInitials[actor.role],
          label: `Tài khoản ${actor.id}`,
          onNavigate: (to) => navigate(to),
          onLogout: () => void logout(),
        }}
        onLogin={() => navigate(roleHomes[actor.role])}
        onNeed={(need) => {
          setError(null);
          if (actor.role === "renter") {
            // Nhu cầu chia sẻ từ trang chủ đi thẳng vào phiên trợ lý đang mở.
            setPendingNeed(need);
            navigate("/tro-ly-ai");
          } else {
            navigate(roleHomes[actor.role]);
          }
        }}
      />
    );
  const allowed = routeRoles[route.kind];
  if (allowed && !allowed.includes(actor.role))
    return (
      <Forbidden
        homePath={roleHomes[actor.role]}
        homeLabel={`Về ${breadcrumbRoles[actor.role].toLowerCase()}`}
      />
    );
  if (route.kind === "redirect") return <Redirect to={route.to} />;
  const links = navByRole[actor.role];
  const flatLinks = links.flatMap((group) => group.items);
  const cleanPath = path.replace(/\/+$/, "");
  const activeLink =
    flatLinks.find((link) => link.path === cleanPath) ||
    flatLinks.find((link) => cleanPath.startsWith(`${link.path}/`)) ||
    null;
  const extraTitles: Record<string, string> = {
    "/tim-kiem": "Tìm phòng",
    "/tin-nhan": "Tin nhắn",
    "/cam-nang": "Cẩm nang",
  };
  const pageTitle =
    activeLink?.label ||
    extraTitles[cleanPath] ||
    (cleanPath.startsWith("/tai-khoan") ? "Tài khoản" : "Trang");
  const collapsed = navCollapsed[actor.role];
  // Màn trợ lý của người thuê không có topbar/footer (cột chat + bản đồ + danh
  // sách chiếm trọn chiều cao), nhưng dùng CHUNG thanh điều hướng với mọi trang:
  // thanh nằm cùng vị trí trong cây nên không bị dựng lại khi chuyển trang, và
  // hình dạng của nó chỉ đổi khi người dùng bấm thu gọn/mở rộng.
  const agentScreen = route.kind === "renter" && route.tab === "search";
  // Trợ lý AI là màn riêng của từng vai: không nằm trong sidebar, chỉ mở qua
  // nút topbar/nút nổi; trên chính màn trợ lý thì ẩn hai nút này đi.
  const assistantPath = actor.role === "renter" ? "/tro-ly-ai" : null;
  const assistantEntry = assistantPath != null && !agentScreen;
  const layoutClass = [
    "app-layout",
    agentScreen ? "agent-screen" : "",
    collapsed ? "nav-collapsed" : "",
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={layoutClass}>
      <a className="skip-link" href="#main-content">
        Chuyển đến nội dung
      </a>
      {agentScreen ? (
        <AgentBar actor={actor} api={api} onLogout={() => void logout()} />
      ) : (
        <SideNav
          actor={actor}
          api={api}
          links={links}
          collapsed={collapsed}
          showBell={agentScreen}
          onToggle={() =>
            setNavCollapsed((value) => ({
              ...value,
              [actor.role]: !value[actor.role],
            }))
          }
        />
      )}
      {agentScreen ? (
        <main className="agent-main" id="main-content" tabIndex={-1}>
          <RenterWorkspace
            key={`${actor.id}:renter`}
            api={api}
            actor={actor}
            tab={route.tab}
            initialNeed={pendingNeed}
            onNeedHandled={() => setPendingNeed(null)}
            sideViewRequest={route.focus === "profile" ? "profile" : null}
          />
        </main>
      ) : (
        <main className="app-main" id="main-content" tabIndex={-1}>
          <header className="topbar">
            <div className="breadcrumb">
              <span>{breadcrumbRoles[actor.role]}</span>
              <Icon name="chevron" size={13} />
              <strong>{pageTitle}</strong>
            </div>
            <div className="topbar-actions">
              {/* Thông báo nằm trên topbar mọi trang thường; màn agent riêng
                  không có topbar nên bell vẫn ở chân sidebar (xem showBell). */}
              <NotificationBell
                api={api}
                onNavigate={(to) => navigate(to)}
                placement="topbar"
              />
              {assistantEntry && assistantPath && (
                <button
                  type="button"
                  className="button small ask-ai-button"
                  onClick={() => navigate(assistantPath)}
                >
                  <Icon name="sparkles" size={15} /> Hỏi trợ lý AI
                </button>
              )}
            </div>
          </header>
          <div className="page-content">
            {/* FE-02: chủ nhà chờ duyệt thấy banner cố định trên mọi trang /chu-nha/*. */}
            {actor.role === "owner" &&
              actor.landlord_status === "pending" &&
              path.startsWith("/chu-nha") && (
                <div className="notice warning" role="status">
                  <span>{landlordPendingNote}</span>
                </div>
              )}
            {route.kind === "renter" ? (
              <RenterWorkspace
                key={`${actor.id}:renter`}
                api={api}
                actor={actor}
                tab={route.tab}
                initialNeed={pendingNeed}
                onNeedHandled={() => setPendingNeed(null)}
                sideViewRequest={route.focus === "profile" ? "profile" : null}
                viewingsFilter={route.filter ?? null}
              />
            ) : route.kind === "saved" ? (
              <SavedPage
                key={`${actor.id}:saved`}
                api={api}
                initialTab={route.tab ?? "saved"}
              />
            ) : route.kind === "listings" ? (
              <SearchPage key={`${actor.id}:listings`} api={api} />
            ) : route.kind === "handbook" ? (
              <HandbookPage api={api} />
            ) : route.kind === "pms" ? (
              route.side ===
              (actor.role === "owner" ? "landlord" : "renter") ? (
                route.page === "dashboard" ? (
                  route.side === "renter" ? (
                    <RenterOverview
                      key={`${actor.id}:overview`}
                      api={api}
                      actor={actor}
                    />
                  ) : (
                    <LandlordDashboard api={api} />
                  )
                ) : route.page === "leases" ? (
                  <LeasesPage key={route.side} api={api} side={route.side} />
                ) : route.page === "billing" ? (
                  <BillingPage key={route.side} api={api} side={route.side} />
                ) : route.page === "usage" ? (
                  <UsagePage key={route.side} side={route.side} />
                ) : (
                  <MaintenancePage
                    key={route.side}
                    api={api}
                    side={route.side}
                  />
                )
              ) : (
                <Forbidden
                  homePath={roleHomes[actor.role]}
                  homeLabel={`Về ${breadcrumbRoles[actor.role].toLowerCase()}`}
                />
              )
            ) : route.kind === "inbox" ? (
              <InboxPage
                key={`${actor.id}:inbox`}
                api={api}
                role={actor.role}
              />
            ) : route.kind === "landlord" ? (
              <LandlordWorkspace
                key={`${actor.id}:landlord`}
                api={api}
                tab={route.tab}
                publishLocked={actor.landlord_status === "pending"}
              />
            ) : route.kind === "admin" ? (
              <AdminWorkspace api={api} section={route.section} />
            ) : route.kind === "account" ? (
              <AccountPage
                actor={actor}
                section={route.section}
                api={api}
                onLogout={() => void logout()}
                onAuthenticated={onAuthenticated}
              />
            ) : (
              <NotFound />
            )}
          </div>
          <footer className="app-footer">
            HomeMatch · Phòng giả lập phục vụ nghiên cứu · Chi phí là ước tính
            theo kịch bản đã xác nhận
          </footer>
        </main>
      )}
      {/* Trợ lý chủ nhà: khung chat nổi ở mọi trang của cổng chủ nhà. */}
      {actor.role === "owner" && (
        <LandlordAgentDock key={actor.id} api={api} actorId={actor.id} />
      )}
    </div>
  );
}
// Trợ lý AI là trang riêng, không nằm trong không gian người thuê: chỉ có thanh
// đầu gọn (logo, quay lại không gian của tôi, thông báo, tài khoản).
function AgentBar({
  actor,
  api,
  onLogout,
}: {
  actor: Actor;
  api: Api;
  onLogout: () => void;
}) {
  const { navigate } = useRouter();
  const go = (to: string) => (event: React.MouseEvent) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey
    )
      return;
    event.preventDefault();
    navigate(to);
  };
  return (
    <header className="agent-bar">
      <a
        href="/"
        className="agent-bar-brand"
        aria-label="Trang chủ HomeMatch"
        onClick={go("/")}
      >
        <Brand />
      </a>
      <a
        href={roleHomes[actor.role]}
        className="agent-bar-back"
        onClick={go(roleHomes[actor.role])}
      >
        <span className="agent-bar-back-icon" aria-hidden="true">
          <Icon name="chevron" size={14} />
        </span>
        Không gian của tôi
      </a>
      <div className="topbar-actions agent-bar-actions">
        <NotificationBell
          api={api}
          onNavigate={(to) => navigate(to)}
          placement="topbar"
        />
        <AccountMenu
          initials={avatarInitials[actor.role]}
          label={`Tài khoản ${actor.id}`}
          onProfile={() => navigate("/tai-khoan/ho-so")}
          onLogout={onLogout}
        />
      </div>
    </header>
  );
}
// Thanh điều hướng chung cho mọi trang sau đăng nhập. Hình dạng chỉ đổi khi
// người dùng bấm thu gọn/mở rộng (có chuyển động), không đổi theo trang. Thu
// gọn: tên mục hiện bằng tooltip ngay cạnh icon; nền "đang ở trang này" trượt
// theo mục đang mở. Nhãn nhóm chỉ hiện khi mở rộng; thu gọn thì thay bằng vạch.
function SideNav({
  actor,
  api,
  links,
  collapsed,
  showBell,
  onToggle,
}: {
  actor: Actor;
  api: Api;
  links: NavGroup[];
  collapsed: boolean;
  // Bell chỉ ở chân sidebar trên màn agent riêng (không có topbar); các trang
  // còn lại bell nằm trên topbar để tránh trùng hai nút.
  showBell: boolean;
  onToggle: () => void;
}) {
  const { path, navigate } = useRouter();
  const [tip, setTip] = useState<{
    label: string;
    y: number;
    show: boolean;
    instant: boolean;
  } | null>(null);
  const tipTimer = useRef<number | undefined>(undefined);
  const navRef = useRef<HTMLElement>(null);
  const [marker, setMarker] = useState<{
    y: number;
    h: number;
    instant: boolean;
  } | null>(null);
  const current = path.replace(/\/+$/, "") || "/";
  const activePath =
    links
      .flatMap((group) => group.items)
      .find((link) => link.path === current || link.also?.includes(current))
      ?.path ?? null;
  useLayoutEffect(() => {
    const measure = (instant: boolean) => {
      const element = navRef.current?.querySelector<HTMLElement>(
        '[aria-current="page"]',
      );
      setMarker((previous) =>
        element
          ? {
              y: element.offsetTop,
              h: element.offsetHeight,
              instant: instant || previous === null,
            }
          : null,
      );
    };
    measure(false);
    const onResize = () => measure(true);
    window.addEventListener("resize", onResize);
    // Nhãn nhóm đổi thành đường kẻ khi thu gọn (và ngược lại) làm các mục dịch
    // chỗ: đo lại ngay mỗi khi nav đổi kích thước để thanh highlight luôn khớp.
    const nav = navRef.current;
    const observer =
      nav && typeof ResizeObserver !== "undefined"
        ? new ResizeObserver(() => measure(true))
        : null;
    if (nav) observer?.observe(nav);
    return () => {
      window.removeEventListener("resize", onResize);
      observer?.disconnect();
    };
  }, [activePath, collapsed]);
  // Di động: thanh tab dưới cuộn ngang, đưa mục đang mở vào giữa.
  useEffect(() => {
    if (!window.matchMedia?.("(max-width: 680px)").matches) return;
    navRef.current
      ?.querySelector<HTMLElement>('[aria-current="page"]')
      ?.scrollIntoView?.({ inline: "center", block: "nearest" });
  }, [activePath]);
  useEffect(() => () => window.clearTimeout(tipTimer.current), []);
  useEffect(() => {
    if (!collapsed) setTip(null);
  }, [collapsed]);
  const showTip =
    (label: string) => (event: React.SyntheticEvent<HTMLElement>) => {
      if (!collapsed) return;
      window.clearTimeout(tipTimer.current);
      const rect = event.currentTarget.getBoundingClientRect();
      setTip((previous) => ({
        label,
        y: rect.top + rect.height / 2,
        show: true,
        instant: !previous?.show,
      }));
    };
  const hideTip = () => {
    window.clearTimeout(tipTimer.current);
    tipTimer.current = window.setTimeout(
      () => setTip((value) => value && { ...value, show: false }),
      90,
    );
  };
  const hint = (label: string) => ({
    onMouseEnter: showTip(label),
    onMouseLeave: hideTip,
    onFocus: showTip(label),
    onBlur: hideTip,
  });
  const go = (to: string) => (event: React.MouseEvent) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    event.preventDefault();
    navigate(to);
  };
  return (
    <aside className="sidebar" aria-label="Điều hướng chính">
      <div className="nav-head">
        <a
          href="/"
          className="nav-brand"
          aria-label={
            collapsed ? "Mở rộng thanh điều hướng" : "Trang chủ HomeMatch"
          }
          onClick={(event) => {
            // Đang thu gọn: bấm logo để mở rộng (trừ màn di động, nơi sidebar là thanh tab).
            if (
              collapsed &&
              !window.matchMedia?.("(max-width: 680px)").matches
            ) {
              event.preventDefault();
              setTip(null);
              onToggle();
              return;
            }
            go("/")(event);
          }}
          {...hint("Mở rộng")}
        >
          <Brand />
        </a>
        <button
          type="button"
          className="nav-toggle"
          aria-label={
            collapsed ? "Mở rộng thanh điều hướng" : "Thu gọn thanh điều hướng"
          }
          aria-expanded={!collapsed}
          tabIndex={collapsed ? -1 : undefined}
          onClick={() => {
            setTip(null);
            onToggle();
          }}
        >
          <Icon name="panel" size={18} />
        </button>
      </div>
      <div className="workspace-label">{workspaceLabels[actor.role]}</div>
      <nav aria-label="Điều hướng workspace" ref={navRef}>
        {marker && (
          <span
            className="nav-marker"
            aria-hidden="true"
            data-instant={marker.instant}
            style={{
              transform: `translateY(${marker.y}px)`,
              height: marker.h,
            }}
          />
        )}
        {links.map((group, groupIndex) => (
          <Fragment key={group.label ?? groupIndex}>
            {group.label ? (
              collapsed ? (
                <div className="nav-group-rule" aria-hidden="true" />
              ) : (
                <div className="nav-group-label">{group.label}</div>
              )
            ) : groupIndex > 0 ? (
              // Nhóm cuối (Hồ sơ, Trung tâm trợ giúp) luôn nằm sát đáy sidebar.
              <div
                className={
                  groupIndex === links.length - 1
                    ? "nav-group-rule nav-group-end"
                    : "nav-group-rule"
                }
                aria-hidden="true"
              />
            ) : null}
            {group.items.map((link) => {
              const active = activePath === link.path;
              return (
                <a
                  key={link.path}
                  href={link.path}
                  className={active ? "nav-link active" : "nav-link"}
                  aria-current={active ? "page" : undefined}
                  onClick={go(link.path)}
                  {...hint(link.label)}
                >
                  <Icon name={link.icon} />
                  <span className="nav-label">{link.label}</span>
                </a>
              );
            })}
          </Fragment>
        ))}
      </nav>
      <div className="nav-bottom">
        {/* Tài khoản mở từ mục "Hồ sơ" trong menu; chân sidebar chỉ còn chuông. */}
        <div className="nav-foot">
          {showBell && (
            <div {...hint("Thông báo")} onClickCapture={() => setTip(null)}>
              <NotificationBell api={api} onNavigate={(to) => navigate(to)} />
            </div>
          )}
        </div>
      </div>
      <div
        className={tip?.show ? "nav-tip show" : "nav-tip"}
        aria-hidden="true"
        data-instant={tip?.instant ?? true}
        style={{ transform: `translateY(${tip?.y ?? 0}px) translateY(-50%)` }}
      >
        {tip?.label}
      </div>
    </aside>
  );
}
