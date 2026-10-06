export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}
export class Api {
  constructor(
    private token: string | null,
    private onUnauthorized: () => void = () => {},
    private base = import.meta.env.VITE_API_BASE_URL || "/api",
  ) {}
  async request<T>(
    path: string,
    options: { method?: string; body?: unknown; signal?: AbortSignal } = {},
  ): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.base}${path}`, {
        method: options.method || "GET",
        signal: options.signal,
        headers: {
          "Content-Type": "application/json",
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        },
        ...(options.body !== undefined
          ? { body: JSON.stringify(options.body) }
          : {}),
      });
    } catch (error) {
      if (error instanceof Error && error.name === "AbortError") throw error;
      throw new ApiError(
        0,
        "network_error",
        "Không kết nối được máy chủ. Kiểm tra kết nối rồi đọc lại trạng thái; yêu cầu chưa được tự gửi lại.",
      );
    }
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401) this.onUnauthorized();
      const detail = Array.isArray(data?.detail)
        ? data.detail
            .map(
              (d: { loc?: string[]; msg?: string }) =>
                `${(d.loc || []).filter((x) => x !== "body").join(".")}: ${d.msg || "không hợp lệ"}`,
            )
            .join("; ")
        : typeof data?.detail === "string"
          ? data.detail
          : null;
      throw new ApiError(
        response.status,
        data?.error?.code || "request_failed",
        data?.error?.message ||
          detail ||
          `Yêu cầu chưa hoàn tất (${response.status}).`,
      );
    }
    return data as T;
  }
  get<T>(path: string, signal?: AbortSignal) {
    return this.request<T>(path, { signal });
  }
  post<T>(path: string, body?: unknown) {
    return this.request<T>(path, { method: "POST", body });
  }
  patch<T>(path: string, body: unknown) {
    return this.request<T>(path, { method: "PATCH", body });
  }
  put<T>(path: string, body: unknown) {
    return this.request<T>(path, { method: "PUT", body });
  }
  delete<T>(path: string) {
    return this.request<T>(path, { method: "DELETE" });
  }
}
// No automatic mutation retries. Keyed actions must retain the exact payload/key.
export const mutationKey = () => crypto.randomUUID();
// Namespace v1 mục tiêu (docs/api-san-pham-v1.md) chưa được khóa ở P0: backend
// 0.4.0 phục vụ các endpoint tài khoản ở đường gốc (/auth/register, /me/...),
// không có tiền tố /v1. Helper giữ lại cho lúc BE mount /v1; UI bắt buộc hiển thị
// trạng thái lỗi thật khi 404, không được giả lập kết quả thành công.
export const v1Base = () => `${import.meta.env.VITE_API_BASE_URL || "/api"}/v1`;
export const v1Api = () => new Api(null, () => {}, v1Base());
export interface RegisterPayload {
  username: string;
  password: string;
  email: string;
  display_name?: string;
}
// Contract 0.4.0 (docs/api-contract.md): đăng ký luôn tạo tài khoản renter
// chưa xác minh; mã xác minh chỉ xuất hiện trong log dev-stub của máy chủ.
export interface RegisterResult {
  status?: string;
  user?: { id: string; role: string };
  delivery?: string;
  message?: string;
  [key: string]: unknown;
}
export const registerAccount = (body: RegisterPayload) =>
  new Api(null).post<RegisterResult>("/auth/register", body);
