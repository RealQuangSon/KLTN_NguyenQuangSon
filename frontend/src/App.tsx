import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Api, ApiError } from "./api";
import type { Actor, Role } from "./types";
import { roleNames } from "./types";
import { Icon } from "./components/Shared";
import { RenterWorkspace } from "./pages/RenterWorkspace";
import { LandlordWorkspace } from "./pages/LandlordWorkspace";
import { SearchPage } from "./pages/SearchPage";
import { HandbookPage } from "./pages/Handbook";
import { InboxPage } from "./pages/Inbox";
import { CopilotPage } from "./pages/Copilot";
import { PublicListing } from "./pages/PublicListing";
import { NotificationBell } from "./components/NotificationBell";
import {
  BillingPage,
  LandlordDashboard,
  LeadsPage,
  LeasesPage,
  MaintenancePage,
} from "./pages/Pms";
import { Landing } from "./pages/Landing";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { AdminWorkspace, type AdminSection } from "./pages/AdminWorkspace";
import { AccountPage } from "./pages/Account";
import { Forbidden, NotFound } from "./pages/StatusPages";
import { RouterProvider, Redirect, useRouter } from "./router";
import { Brand } from "./components/Brand";
import { LoadingState } from "./components/LoadingState";
// FE-02: điều hướng theo route (deep link, back/forward) thay state tab.
// Route UI theo UI_SPEC mục 3; màn chưa có API v1 là khung trung thực.
type AppRoute =
  | { kind: "landing" }
  | { kind: "login" }
  | { kind: "register" }
  | { kind: "renter"; tab: "search" | "viewings" }
  | { kind: "listings" }
  | { kind: "handbook" }
  | { kind: "inbox" }
  | { kind: "copilot" }
  | { kind: "public-listing"; id: string }
  | {
      kind: "pms";
      page: "dashboard" | "leases" | "billing" | "maintenance" | "leads";
      side: "landlord" | "renter";
    }
  | { kind: "landlord"; tab: "review" | "catalog" | "viewings" }
  | { kind: "admin"; section: AdminSection }
  | { kind: "account"; section: "ho-so" | "bao-mat" }
  | { kind: "not-found" };
const publicKinds = ["landing", "login", "register"];
const routeRoles: Partial<Record<AppRoute["kind"], Role[]>> = {
  renter: ["renter"],
  listings: ["renter"],
  handbook: ["renter"],
  inbox: ["renter", "owner"],
  copilot: ["owner"],
  pms: ["renter", "owner"],
  landlord: ["owner"],
  admin: ["admin"],
  account: ["renter", "owner", "manager", "admin"],
};
const roleHomes: Record<Role, string> = {
  renter: "/tro-ly-ai",
  owner: "/chu-nha/tong-quan",
  manager: "/tai-khoan/ho-so",
  admin: "/quan-tri/hoi-thoai",
};
const workspaceLabels: Record<Role, string> = {
  renter: "KHÔNG GIAN NGƯỜI THUÊ",
  owner: "KHÔNG GIAN CHỦ NHÀ",
  manager: "KHÔNG GIAN QUẢN LÝ",
  admin: "KHÔNG GIAN QUẢN TRỊ",
};
const avatarLabels: Record<Role, string> = {
  renter: "NT",
  owner: "CN",
  manager: "QL",
  admin: "QT",
};
const breadcrumbRoles: Record<Role, string> = {
  renter: "Không gian của bạn",
  owner: "Chủ nhà",
  manager: "Quản lý",
  admin: "Quản trị",
};
const sidebarNotes: Record<Role, { title: string; text: string }> = {
  renter: {
    title: "Yên tâm với từng lựa chọn",
    text: "Mỗi phòng được chính chủ nhà duyệt trước khi giới thiệu tới bạn.",
  },
  owner: {
    title: "Quyền theo sở hữu",
    text: "Bạn chỉ làm việc với nhà, phòng và yêu cầu thuộc phạm vi của mình.",
  },
  manager: {
    title: "Yên tâm với từng lựa chọn",
    text: "Mỗi danh sách được quản lý kiểm tra trước khi giới thiệu tới khách.",
  },
  admin: {
    title: "Hành động có kiểm soát",
    text: "Thao tác nhạy cảm cần đúng capability và luôn được máy chủ ghi audit.",
  },
};
const navByRole: Record<Role, { path: string; label: string; icon: string }[]> =
  {
    renter: [
      { path: "/tro-ly-ai", label: "Tìm phòng", icon: "home" },
      { path: "/tim-kiem", label: "Tìm theo bộ lọc", icon: "search" },
      { path: "/tin-nhan", label: "Tin nhắn", icon: "chat" },
      { path: "/nguoi-thue/hop-dong", label: "Hợp đồng", icon: "compare" },
      { path: "/nguoi-thue/hoa-don", label: "Hóa đơn", icon: "clock" },
      { path: "/nguoi-thue/sua-chua", label: "Sửa chữa", icon: "refresh" },
      { path: "/cam-nang", label: "Cẩm nang", icon: "shield" },
      {
        path: "/nguoi-thue/lich-xem",
        label: "Lịch xem của tôi",
        icon: "calendar",
      },
      { path: "/tai-khoan/ho-so", label: "Tài khoản", icon: "shield" },
    ],
    owner: [
      { path: "/chu-nha/tong-quan", label: "Tổng quan", icon: "home" },
      { path: "/chu-nha/duyet-goi-y", label: "Duyệt gợi ý", icon: "shield" },
      { path: "/chu-nha/phong", label: "Phòng & tin", icon: "grid" },
      { path: "/chu-nha/lich-xem", label: "Lịch xem", icon: "calendar" },
      { path: "/chu-nha/hop-thu", label: "Hộp thư", icon: "chat" },
      {
        path: "/chu-nha/khach-tiem-nang",
        label: "Khách tiềm năng",
        icon: "search",
      },
      { path: "/chu-nha/hop-dong", label: "Hợp đồng", icon: "compare" },
      { path: "/chu-nha/hoa-don", label: "Hóa đơn & công nợ", icon: "clock" },
      { path: "/chu-nha/sua-chua", label: "Sửa chữa", icon: "refresh" },
      { path: "/chu-nha/tro-ly", label: "Trợ lý AI", icon: "chat" },
      { path: "/tai-khoan/ho-so", label: "Tài khoản", icon: "shield" },
    ],
    // Legacy staff role: the review work moved to landlords.
    manager: [{ path: "/tai-khoan/ho-so", label: "Tài khoản", icon: "shield" }],
    admin: [
      { path: "/quan-tri/hoi-thoai", label: "Hội thoại AI", icon: "chat" },
      { path: "/quan-tri/chuyen-giao", label: "Chuyển giao", icon: "compare" },
      { path: "/quan-tri/tai-khoan", label: "Người dùng", icon: "grid" },
      { path: "/quan-tri/tin-dang", label: "Tin đăng", icon: "home" },
      { path: "/quan-tri/van-hanh", label: "Vận hành", icon: "refresh" },
      { path: "/tai-khoan/ho-so", label: "Hồ sơ", icon: "shield" },
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
    case "/tro-ly-ai":
      return { kind: "renter", tab: "search" };
    case "/nguoi-thue/lich-xem":
      return { kind: "renter", tab: "viewings" };
    case "/tim-kiem":
      return { kind: "listings" };
    case "/cam-nang":
      return { kind: "handbook" };
    case "/chu-nha/tro-ly":
      return { kind: "copilot" };
    case "/tin-nhan":
    case "/chu-nha/hop-thu":
      return { kind: "inbox" };
    case "/chu-nha/tong-quan":
      return { kind: "pms", page: "dashboard", side: "landlord" };
    case "/chu-nha/khach-tiem-nang":
      return { kind: "pms", page: "leads", side: "landlord" };
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
    case "/chu-nha/duyet-goi-y":
      return { kind: "landlord", tab: "review" };
    case "/chu-nha/phong":
      return { kind: "landlord", tab: "catalog" };
    case "/chu-nha/lich-xem":
      return { kind: "landlord", tab: "viewings" };
    case "/quan-tri/hoi-thoai":
    case "/quan-tri/chuyen-giao":
    case "/quan-tri/tai-khoan":
    case "/quan-tri/tin-dang":
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
function clearLocal() {
  Object.keys(sessionStorage)
    .filter((key) => key.startsWith("homematch."))
    .forEach((key) => sessionStorage.removeItem(key));
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
  const currentToken = useRef(token);
  currentToken.current = token;
  const clear = useCallback(() => {
    currentToken.current = null;
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
      clearLocal();
      sessionStorage.setItem("homematch.token", accessToken);
      currentToken.current = accessToken;
      setToken(accessToken);
      setActor(nextActor);
      setError(null);
      // Nhu cầu chia sẻ trên trang chủ chỉ áp dụng cho người thuê; vai trò
      // khác đăng nhập thì bỏ nhu cầu pending như hành vi cũ.
      if (nextActor.role !== "renter") setPendingNeed(null);
      navigate(roleHomes[nextActor.role]);
    },
    [clear, navigate],
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
  if (publicKinds.includes(route.kind))
    // Đã đăng nhập thì không giữ màn auth; đưa về cổng đúng vai trò.
    return <Redirect to={roleHomes[actor.role]} />;
  const allowed = routeRoles[route.kind];
  if (allowed && !allowed.includes(actor.role))
    return (
      <Forbidden
        homePath={roleHomes[actor.role]}
        homeLabel={`Về ${breadcrumbRoles[actor.role].toLowerCase()}`}
      />
    );
  const links = navByRole[actor.role];
  const activeLink =
    links.find((link) => link.path === path.replace(/\/+$/, "")) || null;
  return (
    <div className="app-layout">
      <a className="skip-link" href="#main-content">
        Chuyển đến nội dung
      </a>
      <aside className="sidebar">
        <Brand />
        <div className="workspace-label">{workspaceLabels[actor.role]}</div>
        <nav aria-label="Điều hướng workspace">
          {links.map((link) => {
            const active = activeLink?.path === link.path;
            return (
              <a
                key={link.path}
                href={link.path}
                className={active ? "nav-link active" : "nav-link"}
                aria-current={active ? "page" : undefined}
                onClick={(event) => {
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
                  navigate(link.path);
                }}
              >
                <Icon name={link.icon} />
                {link.label}
                {active && <span className="active-dot" />}
              </a>
            );
          })}
        </nav>
        <div className="sidebar-note">
          <div className="sidebar-note-icon">
            <Icon name="shield" size={23} />
          </div>
          <strong>{sidebarNotes[actor.role].title}</strong>
          <p>{sidebarNotes[actor.role].text}</p>
        </div>
        <div className="account">
          <div className="avatar">{avatarLabels[actor.role]}</div>
          <div>
            <strong>{actor.id}</strong>
            <small>{roleNames[actor.role]}</small>
          </div>
          <button
            className="icon-button logout"
            onClick={() => void logout()}
            aria-label="Đăng xuất"
          >
            <Icon name="logout" size={19} />
          </button>
        </div>
      </aside>
      <main className="app-main" id="main-content" tabIndex={-1}>
        <header className="topbar">
          <div className="breadcrumb">
            <span>{breadcrumbRoles[actor.role]}</span>
            <Icon name="chevron" size={13} />
            <strong>{activeLink?.label || "Trang"}</strong>
          </div>
          <div className="topbar-actions">
            <NotificationBell api={api} onNavigate={(to) => navigate(to)} />
            <span className="private-label">
              <span className="status-dot" />
              <Icon name="shield" size={14} /> Phiên riêng của bạn
            </span>
          </div>
        </header>
        <div className="page-content">
          {route.kind === "renter" ? (
            <RenterWorkspace
              key={`${actor.id}:renter`}
              api={api}
              actor={actor}
              tab={route.tab}
              initialNeed={pendingNeed}
              onNeedHandled={() => setPendingNeed(null)}
            />
          ) : route.kind === "listings" ? (
            <SearchPage key={`${actor.id}:listings`} api={api} />
          ) : route.kind === "handbook" ? (
            <HandbookPage api={api} />
          ) : route.kind === "pms" ? (
            route.side === (actor.role === "owner" ? "landlord" : "renter") ? (
              route.page === "dashboard" ? (
                <LandlordDashboard api={api} />
              ) : route.page === "leads" ? (
                <LeadsPage api={api} />
              ) : route.page === "leases" ? (
                <LeasesPage key={route.side} api={api} side={route.side} />
              ) : route.page === "billing" ? (
                <BillingPage key={route.side} api={api} side={route.side} />
              ) : (
                <MaintenancePage key={route.side} api={api} side={route.side} />
              )
            ) : (
              <Forbidden
                homePath={roleHomes[actor.role]}
                homeLabel={`Về ${breadcrumbRoles[actor.role].toLowerCase()}`}
              />
            )
          ) : route.kind === "copilot" ? (
            <CopilotPage api={api} />
          ) : route.kind === "inbox" ? (
            <InboxPage key={`${actor.id}:inbox`} api={api} role={actor.role} />
          ) : route.kind === "landlord" ? (
            <LandlordWorkspace
              key={`${actor.id}:landlord`}
              api={api}
              tab={route.tab}
            />
          ) : route.kind === "admin" ? (
            <AdminWorkspace api={api} section={route.section} />
          ) : route.kind === "account" ? (
            <AccountPage actor={actor} section={route.section} api={api} />
          ) : (
            <NotFound />
          )}
        </div>
        <footer className="app-footer">
          HomeMatch · Phòng giả lập phục vụ nghiên cứu · Chi phí là ước tính
          theo kịch bản đã xác nhận
        </footer>
      </main>
    </div>
  );
}
