import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach, beforeEach, vi } from "vitest";
// Các test UI chạy song song trên nhiều worker; tăng thời gian chờ findBy* để
// tránh lỗi ngẫu nhiên khi máy bận, không đổi hành vi được kiểm tra.
configure({ asyncUtilTimeout: 4000 });
beforeEach(() => {
  sessionStorage.clear();
  // Router đọc location thật; jsdom dùng chung window trong một file test,
  // nên trả URL về "/" trước mỗi test để render(<App />) luôn bắt đầu ở landing.
  window.history.replaceState(null, "", "/");
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
