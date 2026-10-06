// Tên chuẩn thành phố/khu vực, đồng bộ với backend/app/locations.py
// (backend/tests/test_locations.py kiểm tra hai danh sách khớp nhau).
// Ô khu vực vẫn cho nhập tự do; backend tự nhận các cách gọi khác như "Q7".
export const cityAreas: Record<string, string[]> = {
  "TP.HCM": [
    "Quận 1",
    "Quận 3",
    "Quận 4",
    "Quận 5",
    "Quận 6",
    "Quận 7",
    "Quận 8",
    "Quận 10",
    "Quận 11",
    "Quận 12",
    "Quận Bình Thạnh",
    "Quận Gò Vấp",
    "Quận Phú Nhuận",
    "Quận Tân Bình",
    "Quận Tân Phú",
    "Quận Bình Tân",
    "TP. Thủ Đức",
    "Huyện Bình Chánh",
    "Huyện Nhà Bè",
  ],
  "Hà Nội": [
    "Quận Ba Đình",
    "Quận Hoàn Kiếm",
    "Quận Đống Đa",
    "Quận Hai Bà Trưng",
    "Quận Cầu Giấy",
    "Quận Thanh Xuân",
    "Quận Hoàng Mai",
    "Quận Long Biên",
    "Quận Tây Hồ",
    "Quận Bắc Từ Liêm",
    "Quận Nam Từ Liêm",
    "Quận Hà Đông",
  ],
};
export const defaultDestination: Record<
  string,
  { latitude: number; longitude: number }
> = {
  "TP.HCM": { latitude: 10.735, longitude: 106.721 },
  "Hà Nội": { latitude: 21.034, longitude: 105.794 },
};
