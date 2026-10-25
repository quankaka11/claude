# Claude Architect Prep (CCAR-F / CCAR-P)

Ứng dụng luyện thi offline, gộp câu hỏi luyện tập miễn phí từ nhiều nguồn công khai.

| Nguồn | CCAR-F | CCAR-P | Ghi chú |
|---|---|---|---|
| FlashGenius (sample tests, tài khoản free) | 71 | 90 | + cheat sheet, FAQ |
| claudearchitectguide.com | 200 | 200 | có câu chọn nhiều đáp án và ghép cặp |
| open-exam-prep.com | 100 | 100 | |
| timolabs.dev (mock 20 câu) | 20 | 20 | |
| certsafari.com (sample) | 35 | 35 | |
| szymonpaluch.com | 60 | – | |
| GitHub OlivierAlter | 77 | – | |
| **Tổng (đã loại trùng)** | **563** | **445** | |

Tất cả là đề luyện không chính thức, không phải đề thi thật của Anthropic. Nội dung thuộc bản quyền
của từng trang, chỉ dùng để tự ôn tập, không phát tán lại.

## Dùng

Mở `docs/index.html` bằng trình duyệt (không cần server).

- **Thi thử có giờ**: 60 câu / 120 phút (CCAR-F), 63 câu / 120 phút (CCAR-P), chia theo tỷ trọng domain.
- **Luyện tập**: ngẫu nhiên, theo domain, câu chưa làm, ôn câu sai; xem đáp án và giải thích ngay.
- **Nguồn câu hỏi**: bật/tắt từng nguồn để luyện riêng.
- **Tài liệu**: cheat sheet, FAQ, duyệt/tìm kiếm toàn bộ câu hỏi (lọc theo domain, nguồn).
- Tiến độ và lịch sử thi lưu trong `localStorage` của trình duyệt.

## Cập nhật dữ liệu

```powershell
python crawl_free.py                 # các nguồn miễn phí -> data/free/
$env:FG_USER = "<tài khoản>"; $env:FG_PASS = "<mật khẩu>"; python crawl.py   # FlashGenius -> data/raw/ (tự chạy build)
python build.py                      # gộp, loại trùng -> docs/data.js
```

## Deploy lên GitHub Pages

Site GitHub Pages luôn công khai, nên chỉ bản **đã mã hoá** `docs/data.enc.json` được đưa lên
(gzip + AES-256-GCM, khoá dẫn xuất từ mật khẩu bằng PBKDF2-SHA256 600k vòng). `data/` và `docs/data.js`
nằm trong `.gitignore` — **không bao giờ commit hai thứ này**.

1. Tạo bản mã hoá (chạy lại mỗi khi dữ liệu thay đổi hoặc muốn đổi mật khẩu):
   ```powershell
   $env:CCAR_PASS = "<mật khẩu>"; python build.py
   ```
2. Commit và push nhánh `master`.
3. Trên GitHub: **Settings → Pages → Build and deployment → Source: Deploy from a branch**,
   chọn `master` và thư mục `/docs`. Trang sẽ ở `https://<user>.github.io/<repo>/`.

Mở trang, nhập mật khẩu (có tuỳ chọn ghi nhớ trên thiết bị). Đổi mật khẩu = chạy lại bước 1 rồi push;
thiết bị đã ghi nhớ sẽ tự hỏi lại mật khẩu mới.

`crawl_free.py <tên nguồn>` để chỉ crawl lại một nguồn (`open_exam_prep`, `szymonpaluch`,
`claudearchitectguide`, `timolabs`, `certsafari`, `github_olivieralter`). Cần `node` để đọc cheat sheet FlashGenius.
