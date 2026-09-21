# PJQT — nhận Potion Explore cho Esther (event 11)

Tool Python nhận phần thưởng Explore đã tích lũy. Workflow chạy trên GitHub
Actions, không cần bật máy cá nhân khi đã cấu hình phiên hợp lệ.

## Thiết lập

1. Lấy phiên đăng nhập game mới bằng `export_session.py` như hướng dẫn bên dưới.
2. Trong **Settings → Secrets and variables → Actions → Secrets**, tạo repository
   secret **`PJQT_SESSION`** chứa JSON của `.private/session.json`.
3. Vào **Actions → Auto Claim Potion → Run workflow**. Để `claim` không được chọn
   để kiểm tra phiên và số chu kỳ tích lũy từ GitHub runner.
4. Khi kiểm tra thành công và đã có Potion để nhận, chạy lại với `claim` được chọn.
   Xác nhận log có `COLLECTED` và số lượng nhận được.
5. Tạo repository variable **`PJQT_AUTO_CLAIM_ENABLED`** với giá trị **`true`** để
   bật tự nhận mỗi giờ theo lịch có sẵn. Đổi thành `false` để tắt tự nhận theo lịch.

Workflow dùng event **11**, đã được người dùng chọn. Không dùng lại secret
`PJQT_HEADERS`: chữ ký được tính lại từ token đăng nhập cho mỗi request.

Lịch GitHub có thể trễ hoặc bỏ lượt khi tải cao; xem
[tài liệu schedule](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Phiên đăng nhập

Với Cốc Cốc/Chrome: mở **F12 → Network**, bật **Preserve log**, tải lại game và
đợi vào game. Xuất HAR có nội dung phản hồi vào `.private/game.har`, rồi chạy:

```powershell
python export_session.py .private/game.har
```

Tool chọn lần đăng nhập thành công cuối cùng trong HAR và đối chiếu với một API
thành công thuộc cùng phiên. Nó không in token hoặc gửi HAR ra ngoài máy.

Nếu đã có bản ghi từ công cụ khảo sát cũ, vẫn có thể dùng cách sau.
Cần hai file bản ghi server chính từ cùng phiên:

- Phản hồi thành công `POST https://us.nkrpg.com/api/auth/login/user`.
- Một request API có xác thực, thành công, sau lần đăng nhập đó.

```powershell
python export_session.py "login-capture.json" "api-capture.json"
```

Script kiểm tra tài khoản và chữ ký, rồi ghi `.private/session.json`. Không commit
file phiên, bản ghi mạng, HAR hoặc mật khẩu; `.private/` đã được loại khỏi Git.
Script không ghi đè file phiên đã có. Có thể chọn file mới với `--output`.

**Chưa có tự đăng nhập lại.** Khi phiên hết hiệu lực, tool trả lỗi
`11009 REQUIRE_LOGIN`; cần lấy phiên mới và cập nhật `PJQT_SESSION`.
Tuổi thọ phiên và khả năng sử dụng phiên từ GitHub runner cần được kiểm chứng thực tế.

## Chạy cục bộ

```powershell
# Chỉ đọc trạng thái, không nhận thưởng.
python main.py --session-file .private/session.json --event-id 11

# Nhận một lần khi có phần thưởng tích lũy.
python main.py --session-file .private/session.json --event-id 11 --claim

# Kiểm thử không gọi server game.
python -m unittest discover -s tests -v
```

Tool kiểm tra tài khoản, sự kiện và tier trước khi nhận. Các lượt chạy không nhận
song song. Khi request nhận bị lỗi mạng, tool không tự gửi lại vì server có thể
đã xử lý. Lượt sau đọc lại trạng thái trước khi quyết định nhận.
