# Backup và phục hồi local

**Trạng thái:** scripts đã kiểm tra cú pháp; dump/restore nghiệp vụ chưa chạy do bước cấp quyền bị giới hạn. Không coi hướng dẫn này là bằng chứng phục hồi thành công.

## PostgreSQL

Các scripts chỉ nhắm cluster local 127.0.0.1:55432 và `homematch_dev`, không dịch vụ hệ thống/cloud. Backup chứa ledger, account/token hashes, catalog và bảng checkpoint; giữ riêng tư trong `.local/backups` đã ignore.

```bash
bash infra/local-backup.sh
bash infra/local-restore.sh /absolute/path/to/homematch_dev_TIMESTAMP.dump
```

Restore kiểm SHA-256 rồi tạo **DB mới** tên `homematch_restore_<timestamp>`, không drop/overwrite dev/test. Nếu lỗi, DB đích chưa đầy đủ không được dùng release. Sau restore kiểm extension vector, số bản ghi `hm_sessions/hm_runs/hm_rooms/hm_viewings` và các bảng checkpoint; chọn một pending run, đăng nhập bằng token mới và tiếp tục manager review/retry, rồi results/compare. Ghi hash dump và bảng đếm trước/sau; không đưa dump vào report công khai.

## SQLite

Dừng API trước khi sao lưu. Cần cả file ledger và file `<db_path>.checkpoints.sqlite`; không copy khi process đang ghi. Dùng SQLite backup API hoặc copy hai file sau khi connection đã đóng, tạo hash và restore vào thư mục thử mới. Chỉ đổi DB_PATH khi đã kiểm cả hai file; thiếu checkpoint không được coi recovery hoàn tất.

## Nghiệm thu chưa hoàn thành

- [ ] PG dump và checksum thực tế.
- [ ] Restore DB mới, counts và extension khớp.
- [ ] Pending/reviewed được phục hồi mà không lặp side effect.
- [ ] Results vẫn tuân thủ HITL/stale sau restore.

Container volume hoặc checkpoint đơn lẻ không thay backup ledger đầy đủ. Không xoá DB phục hồi tự động; người vận hành kiểm tra xong mới dọn theo nhu cầu.
