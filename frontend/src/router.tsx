import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type AnchorHTMLAttributes,
  type ReactNode,
} from "react";
// Bộ định tuyến lịch sử gọn của HomeMatch (FE-02): deep link, back/forward và
// Link/navigate. Không thêm dependency mới; jsdom/tests chạy offline được.
// Chỉ đồng bộ pathname; filter công khai sẽ đồng bộ query string ở FE-05.
type RouterValue = {
  path: string;
  navigate: (to: string, options?: { replace?: boolean }) => void;
};
const RouterContext = createContext<RouterValue | null>(null);
const currentPath = () => window.location.pathname || "/";
export function RouterProvider({ children }: { children: ReactNode }) {
  const [path, setPath] = useState(currentPath);
  useEffect(() => {
    const onPop = () => setPath(currentPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  const navigate = useCallback(
    (to: string, options?: { replace?: boolean }) => {
      if (options?.replace) window.history.replaceState(null, "", to);
      else window.history.pushState(null, "", to);
      setPath(currentPath());
    },
    [],
  );
  const value = useMemo(() => ({ path, navigate }), [path, navigate]);
  return (
    <RouterContext.Provider value={value}>{children}</RouterContext.Provider>
  );
}
export function useRouter(): RouterValue {
  const value = useContext(RouterContext);
  if (!value) throw new Error("useRouter phải nằm trong RouterProvider");
  return value;
}
export function useNavigate() {
  return useRouter().navigate;
}
export function Link({
  to,
  children,
  ...rest
}: {
  to: string;
  children: ReactNode;
} & AnchorHTMLAttributes<HTMLAnchorElement>) {
  const navigate = useNavigate();
  return (
    <a
      href={to}
      {...rest}
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
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}
// Chuyển hướng sau khi render (không đổi state trong lúc render).
export function Redirect({ to }: { to: string }) {
  const navigate = useNavigate();
  useEffect(() => {
    navigate(to, { replace: true });
  }, [navigate, to]);
  return null;
}
export type RouteParams = Record<string, string>;
// So khớp mẫu kiểu "/nguoi-thue/lich-xem/:viewingId"; ":" là một đoạn, "*"
// khớp phần còn lại. Trả về null nếu không khớp.
export function matchPath(pattern: string, path: string): RouteParams | null {
  const patternParts = pattern.split("/").filter(Boolean);
  const pathParts = path.split("/").filter(Boolean);
  const params: RouteParams = {};
  for (let i = 0; i < patternParts.length; i++) {
    const part = patternParts[i];
    if (part === "*") return { ...params, "*": pathParts.slice(i).join("/") };
    if (pathParts.length === i) return null;
    if (part.startsWith(":"))
      params[part.slice(1)] = decodeURIComponent(pathParts[i]);
    else if (part !== pathParts[i]) return null;
  }
  return patternParts.length === pathParts.length ? params : null;
}
