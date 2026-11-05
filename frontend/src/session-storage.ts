// Lưu trữ phiên phía trình duyệt. `clearLocal` xoá toàn bộ dữ liệu riêng tư
// (dùng khi đăng xuất). `clearLoginStorage` dùng khi đăng nhập/chuyển trải
// nghiệm: giữ lại khoá `homematch.session.<user>` — chỉ là mã phiên ngẫu nhiên,
// không phải dữ liệu cá nhân, nội dung hội thoại vẫn thuộc máy chủ (đã PII
// mask) — để quay lại đúng vai là dùng được trợ lý ngay, không phải tạo phiên
// mới. Token phiên server vẫn theo TTL và bị từ chối thì UI xoá khoá + báo lỗi.
const PREFIX = "homematch.";
const SESSION_PREFIX = "homematch.session.";
export function clearLocal(): void {
  Object.keys(sessionStorage)
    .filter((key) => key.startsWith(PREFIX))
    .forEach((key) => sessionStorage.removeItem(key));
}
export function clearLoginStorage(): void {
  Object.keys(sessionStorage)
    .filter((key) => key.startsWith(PREFIX) && !key.startsWith(SESSION_PREFIX))
    .forEach((key) => sessionStorage.removeItem(key));
}
