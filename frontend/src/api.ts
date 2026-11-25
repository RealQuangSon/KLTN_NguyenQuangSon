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
    // FE-05: multipart upload (FormData) không đặt Content-Type thủ công —
    // trình duyệt tự thêm boundary; các lời gọi khác vẫn là JSON.
    const isForm =
      typeof FormData !== "undefined" && options.body instanceof FormData;
    let response: Response;
    try {
      response = await fetch(`${this.base}${path}`, {
        method: options.method || "GET",
        signal: options.signal,
        headers: {
          ...(isForm ? {} : { "Content-Type": "application/json" }),
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        },
        ...(options.body !== undefined
          ? {
              body:
                isForm || typeof options.body === "string"
                  ? (options.body as FormData | string)
                  : JSON.stringify(options.body),
            }
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
  // FE-05: tải ảnh lên đúng hợp đồng multipart (README §7.5), field "file".
  upload<T>(path: string, file: File) {
    const form = new FormData();
    form.append("file", file);
    return this.request<T>(path, { method: "POST", body: form });
  }
  // WS-02: đọc luồng NDJSON các bước xử lý — từng dòng {"type":"step",...},
  // dòng cuối {"type":"done","data"} (hoặc {"type":"error","error"}).
  // Luồng đứt giữa chừng → ApiError để caller thử lại (tối đa 2 lần).
  async streamTurn<T>(
    path: string,
    body: unknown,
    onStep?: (step: { name: string; kind: string; detail: string }) => void,
    onDelta?: (event: { type: "delta" | "replace"; text: string }) => void,
  ): Promise<T> {
    let response: Response;
    try {
      response = await fetch(`${this.base}${path}`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        },
        body: JSON.stringify(body),
      });
    } catch {
      throw new ApiError(
        0,
        "network_error",
        "Không kết nối được máy chủ. Kiểm tra kết nối rồi thử lại.",
      );
    }
    if (!response.ok || !response.body) {
      const data = await response.json().catch(() => null);
      if (response.status === 401) this.onUnauthorized();
      throw new ApiError(
        response.status,
        data?.error?.code || "request_failed",
        data?.error?.message || `Yêu cầu chưa hoàn tất (${response.status}).`,
      );
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let done: T | null = null;
    while (true) {
      const { value, done: finished } = await reader.read();
      if (finished) break;
      buffer += decoder.decode(value, { stream: true });
      let index: number;
      while ((index = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, index).trim();
        buffer = buffer.slice(index + 1);
        if (!line) continue;
        const event = JSON.parse(line) as {
          type: string;
          step?: { name: string; kind: string; detail: string };
          data?: T;
          text?: string;
          error?: { code: string; message: string };
        };
        if (event.type === "step") onStep?.(event.step!);
        else if (event.type === "delta" || event.type === "replace")
          onDelta?.({ type: event.type, text: event.text ?? "" });
        else if (event.type === "done") done = event.data ?? null;
        else
          throw new ApiError(
            0,
            event.error?.code || "stream_error",
            event.error?.message || "Lượt xử lý bị gián đoạn.",
          );
      }
    }
    if (done === null)
      throw new ApiError(
        0,
        "stream_broken",
        "Luồng xử lý bị đứt trước khi hoàn tất.",
      );
    return done;
  }

  // Gửi một lượt chat: ưu tiên stream bước xử lý; đứt luồng thì thử lại tối đa
  // 2 lần; vẫn lỗi thì quay về endpoint trả một lần (hành vi cũ).
  async turn<T>(
    path: string,
    body: unknown,
    onStep?: (step: { name: string; kind: string; detail: string }) => void,
    onDelta?: (event: { type: "delta" | "replace"; text: string }) => void,
  ): Promise<T> {
    const streamPath = `${path}/stream`;
    // Một mã cho cả stream retry và POST dự phòng, tránh ghi nghiệp vụ hai lần.
    body = {
      ...(body as Record<string, unknown>),
      turn_id: crypto.randomUUID(),
    };
    let lastError: unknown = null;
    for (let attempt = 0; attempt < 2; attempt++) {
      try {
        return await this.streamTurn<T>(streamPath, body, onStep, onDelta);
      } catch (error) {
        if (
          error instanceof ApiError &&
          error.status >= 400 &&
          error.status < 500
        )
          throw error; // lỗi nghiệp vụ: không thử lại
        lastError = error;
      }
    }
    try {
      return await this.post<T>(path, body);
    } catch (error) {
      if (lastError instanceof ApiError && !(error instanceof ApiError))
        throw lastError;
      throw error;
    }
  }

  // Ảnh sự cố không công khai: cần bearer token nên phải fetch thủ công rồi
  // trả object URL; component gọi phải URL.revokeObjectURL khi unmount.
  async blobUrl(path: string): Promise<string> {
    let response: Response;
    try {
      response = await fetch(`${this.base}${path}`, {
        headers: this.token ? { Authorization: `Bearer ${this.token}` } : {},
      });
    } catch {
      throw new ApiError(
        0,
        "network_error",
        "Không kết nối được máy chủ. Kiểm tra kết nối rồi đọc lại trạng thái; yêu cầu chưa được tự gửi lại.",
      );
    }
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new ApiError(
        response.status,
        data?.error?.code || "media_failed",
        data?.error?.message || `Không tải được ảnh (${response.status}).`,
      );
    }
    return URL.createObjectURL(await response.blob());
  }
}
// No automatic mutation retries. Keyed actions must retain the exact payload/key.
export const mutationKey = () => crypto.randomUUID();
// FE-05: url ảnh trả về từ máy chủ là "/media/{id}"; hiển thị cần tiền tố API
// giống mọi lời gọi khác (VITE_API_BASE_URL, mặc định "/api").
export const apiBase = () => import.meta.env.VITE_API_BASE_URL || "/api";
export const mediaSrc = (url: string) => `${apiBase()}${url}`;
// Namespace v1 mục tiêu (docs/api-contract.md) chưa được mount: backend
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
  // Hợp đồng đăng ký (docs/api-contract.md): mặc định "renter";
  // "owner" tạo hồ sơ chủ nhà chờ quản trị viên duyệt.
  account_type?: "renter" | "owner";
}
// Đăng ký tạo tài khoản chưa xác minh (pending_verification); mã xác minh chỉ
// xuất hiện trong log dev-stub của máy chủ. Hồ sơ chủ nhà bắt đầu ở trạng thái
// landlord_status "pending" cho tới khi quản trị viên duyệt.
export interface RegisterResult {
  status?: string;
  user?: { id: string; role: string };
  delivery?: string;
  message?: string;
  [key: string]: unknown;
}
export const registerAccount = (body: RegisterPayload) =>
  new Api(null).post<RegisterResult>("/auth/register", body);
