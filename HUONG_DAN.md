# Threads Studio

Mở **MO_TOOL.cmd** trong thư mục `C:\Tool_Thred`. Khi có bản đóng gói, lệnh này mở `dist\ThreadsStudio\ThreadsStudio.exe`; nếu chưa có, chạy bằng Python.

## Tạo video

1. Dán link bài Threads và bấm **Lấy bài & bình luận**.
2. Bấm **Sửa, thêm & sắp xếp bình luận** để chỉnh chữ, bỏ bình luận không cần hoặc đổi thứ tự. Trong cửa sổ sửa, bấm **Lưu đoạn đang sửa** trước khi chọn đoạn khác. Mục đầu tiên là bài gốc.
3. Chọn một trong ba mẫu: **Thẻ giữa** (mẫu 3), **Thẻ trên** (mẫu 2), **Lưới xanh** (mẫu 1).
4. Có thể chọn video nền, nhạc nền, giọng đọc, số bài tối đa và độ phân giải 720p / 1080p. Số bài tối đa tính cả bài gốc. Nhạc được hạ âm lượng khi ghép với giọng đọc. Khi tắt giọng đọc, thời lượng dựa vào số từ và tốc độ từ/phút.
5. Dùng ◀ / ▶ để xem từng cảnh; bấm **XUẤT VIDEO MP4**, chọn tên chưa tồn tại, chờ tiến trình hoàn tất rồi **Mở video**.

Video xuất: H.264, AAC stereo, 30 fps, khung dọc 9:16. Nội dung dài tự chia trang; mẫu lưới giữ trang đầu bài gốc phía trên mỗi bình luận. Giọng đọc dùng Edge TTS trực tuyến; các đoạn đã tạo được lưu đệm trên máy. Mạng lỗi sẽ báo rõ để có thể thử lại hoặc tắt giọng đọc.

## Nền và nội dung

- Nền gameplay đi kèm được cắt vùng dưới không có thẻ chữ từ **video mẫu 2 do bạn cung cấp**, rồi phóng lên. Vì vậy góc nhìn hẹp và độ nét thấp hơn footage gốc. Để có nền toàn cảnh tương tự mẫu 2–3, chọn video gameplay sạch của bạn ở **Video nền**.
- Công cụ lấy nội dung, ảnh đại diện, tên tài khoản và số tương tác công khai, rồi dựng lại thẻ trắng theo bố cục mẫu. Không tạo số tương tác giả. Video không tự dịch nội dung; chọn giọng phù hợp hoặc sửa nội dung trước khi xuất.
- Threads có thể chỉ cho xem một phần bình luận khi chưa đăng nhập. Trong lần thử link của bạn lấy được bài gốc và 30 bình luận; con số trên nút bình luận có thể lớn hơn. Bài bị ẩn/xóa/chặn sẽ báo lỗi; vẫn có thể mở dự án cũ hoặc nhập nội dung bằng trình sửa.
- **Lưu** và **Mở dự án** dùng tệp JSON để giữ nội dung và thông tin tài khoản. Các lựa chọn xuất đặt trong giao diện. Mỗi lần xuất lưu thêm thư mục `_project` cạnh MP4 gồm nội dung nguồn, thẻ PNG, giọng đọc và timeline để kiểm tra hoặc chỉnh lại.
- **Hủy** dừng dựng tại bước kiểm tra tiếp theo; tải Threads và giọng đọc đang chờ mạng sẽ kết thúc yêu cầu hiện tại trước. Công cụ không xuất một tệp MP4 hoàn thành khi tác vụ bị hủy.

## Video đã thử với link yêu cầu

`https://www.threads.com/@aisyahhhh.hani/post/Df8vzcVCZ9L`

- `outputs\Threads_Df8vzcVCZ9L_FINAL.mp4`: thẻ giữa, bài gốc + 7 bình luận, giọng Malay Yasmin phù hợp nội dung nguồn.
- `outputs\Threads_Df8vzcVCZ9L_top.mp4`: thẻ phía trên, bài gốc + 2 bình luận.
- `outputs\Threads_Df8vzcVCZ9L_grid_FINAL.mp4`: lưới xanh, bài gốc + 2 bình luận; bài gốc dài được chia thành 2 cảnh.
- `outputs\test-project.json`: dữ liệu thật của bài thử để mở và dựng tiếp.

## Chạy từ mã nguồn

Yêu cầu Windows, Python 3.11+ và Microsoft Edge; FFmpeg / ffprobe trong PATH. Máy hiện tại đã có các thành phần này. `CAI_DAT.cmd` cài thư viện và FFmpeg nếu thiếu. Bản EXE đi kèm thư viện Python nhưng vẫn sử dụng Edge và FFmpeg trên máy.

```powershell
python app.py
python cli.py --url "https://www.threads.com/@aisyahhhh.hani/post/Df8vzcVCZ9L" --output outputs\video_moi.mp4 --style center --max-posts 8
python cli.py --project outputs\test-project.json --output outputs\video_offline.mp4 --style grid --no-speech
python -m unittest discover -s tests -v
```

Không cần tài khoản Threads cho bài công khai đã thử. Không đăng bài hoặc tương tác với tài khoản; các tệp xuất được lưu trên máy.
