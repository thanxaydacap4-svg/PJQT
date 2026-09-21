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
5. Thiết lập lịch gọi workflow từ **cron-job.org** theo phần dưới. Bật job sau khi
   một lượt thử từ dịch vụ này đã gọi được GitHub và hoàn tất bước `Run Script`.

Workflow dùng event **11**, đã được người dùng chọn. Không dùng lại secret
`PJQT_HEADERS`: chữ ký được tính lại từ token đăng nhập cho mỗi request.

## Lịch tự động qua cron-job.org

GitHub vẫn chạy script và giữ secret game; cron-job.org chỉ gọi API để kích hoạt
workflow. Lịch `schedule` cũ trên GitHub được bỏ khi chuyển sang dịch vụ này.

Tạo **fine-grained personal access token** trên GitHub: chỉ chọn repo `PJQT`,
quyền **Actions: Read and write** (Metadata chỉ đọc là quyền bắt buộc). Ghi nhớ
ngày hết hạn để thay token trước khi lịch ngừng kích hoạt được workflow.

Cấu hình job trên cron-job.org:

- URL: `https://api.github.com/repos/thanxaydacap4-svg/PJQT/actions/workflows/auto_claim.yml/dispatches`.
- Method: `POST`; body: `{"ref":"main","inputs":{"claim":true}}`.
- Lịch: `35 * * * *`, múi giờ `Asia/Bangkok` (UTC+7).
- Header `Authorization`: `Bearer <TOKEN_GITHUB>`.
- Header `Accept`: `application/vnd.github+json`.
- Header `Content-Type`: `application/json`.
- Header `X-GitHub-Api-Version`: `2026-03-10`.
- Bật **Save responses in job history** để đối chiếu kết quả gọi GitHub.

Không ghi token thật vào repo hoặc chat. Token game `PJQT_SESSION` chỉ lưu trên
GitHub; header Authorization ở cron-job.org dùng token GitHub riêng.

Kiểm tra cả hai nơi: HTTP thành công ở cron-job.org chứng minh GitHub nhận yêu
cầu, còn log **Run Script** trên GitHub mới cho biết đã nhận Potion, chưa đủ
chu kỳ hay phiên game hết hạn. Những lượt này có event `workflow_dispatch` nên
GitHub có thể ghi **Manually run** dù được cron-job.org gọi tự động; đối chiếu
với lịch sử thực thi theo lịch của cron-job.org.

Để tạm dừng tự nhận, tắt **Enable job** trên cron-job.org. Biến cũ
`PJQT_AUTO_CLAIM_ENABLED` không điều khiển các lượt gọi qua API này.
Khi token GitHub hết hạn hoặc bị thu hồi, cập nhật header Authorization của
job; khi game báo `11009 REQUIRE_LOGIN`, cập nhật secret `PJQT_SESSION`.

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
