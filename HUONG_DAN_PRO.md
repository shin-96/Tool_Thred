# Threads Studio Pro

## Bản 2.1 — API giọng đọc và chèn media

### Kết nối thêm giọng đọc

1. Mở tab **API giọng đọc**, chọn **Cấu hình mới** và loại dịch vụ.
2. Đặt tên, endpoint, Voice/Voice ID, model và API key. Mẫu mặc định có sẵn cho **OpenAI/tương thích**, **ElevenLabs**, **Azure Speech**. Có thể tạo nhiều cấu hình cho nhiều giọng hoặc nhiều dịch vụ.
3. **Lưu cấu hình**, rồi dùng **Nghe thử cấu hình đã lưu** với đoạn ngắn. Khi nghe thử sẽ gửi nội dung đến dịch vụ và có thể dùng hạn mức/tính phí theo tài khoản API của bạn. Các bài test bàn giao sử dụng API mô phỏng và HTTP localhost; chưa gọi dịch vụ trả phí bằng key cá nhân.
4. Tại **Tạo hàng loạt**, chọn cấu hình trong menu dưới giọng Edge. Khi chọn API, các lựa chọn Edge được khóa để tránh nhầm. Cấu hình có thể lưu trong preset và sửa riêng cho từng tác vụ chờ/lỗi.

Key lưu bằng DPAPI trong dữ liệu ứng dụng, không đưa vào job, preset, timeline hoặc CSV. Có thể để trống ô key khi cập nhật để giữ key cũ. Khi đổi đích endpoint/xác thực, cần nhập lại key cho đích mới. Gỡ cấu hình không thu hồi key trên dịch vụ; các tác vụ tham chiếu cấu hình đã gỡ cần chọn giọng lại.

API trả âm thanh được kiểm tra bằng ffprobe, chuẩn hóa MP3 và lưu đệm trước khi ghép. Khi API lỗi, tool báo lỗi cho tác vụ, không tự đổi sang giọng Edge và không tự gửi lại yêu cầu có thể phát sinh phí. Tốc độ và Voice ID phải được model/dịch vụ hỗ trợ.

**HTTP JSON tùy chỉnh** dành cho dịch vụ khác:

- Endpoint đầy đủ, header API key và tiền tố key có thể cấu hình. Ví dụ `Authorization` và `Bearer ` (có dấu cách cuối), hoặc `xi-api-key` và tiền tố rỗng.
- Body là JSON object, dùng `{text}`, `{voice}`, `{model}`, `{speed}`. Thay thế là dữ liệu, không thực thi mã.
- `audio`: response chứa trực tiếp tệp âm thanh.
- `base64`: response JSON chứa chuỗi base64 tại đường dẫn đã chọn, ví dụ `data.audio`.
- `url`: response JSON chứa URL HTTPS âm thanh đã sẵn sàng, ví dụ `data.audio_url`. Tool tải URL không kèm API key. API yêu cầu polling/job bất đồng bộ riêng hoặc quy trình xác thực khác cần adapter bổ sung; cấu hình URL chưa sẵn sàng sẽ báo lỗi, không tự tạo lại giọng.
- API từ xa dùng HTTPS. HTTP chỉ được phép với localhost cho dịch vụ chạy trên máy. Không đưa key vào endpoint, body hoặc nội dung nghe thử.

Tham khảo giao thức: [OpenAI Speech](https://developers.openai.com/api/reference/resources/audio/subresources/speech/methods/create), [ElevenLabs](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [Azure Speech](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech).

### Chèn meme, ảnh hoặc clip

1. Trong **Thư viện video**, chọn một video. Mở **Chèn meme / media**, bấm **Dùng video chọn trong Thư viện**.
2. **Chọn meme / ảnh / clip**, đặt thông số rồi **Lưu lớp media**. Nút Lưu cần bấm sau mỗi lần sửa thông số.
3. **Phủ lên video**: đặt thời điểm, thời lượng, X/Y, chiều rộng, độ hiện và âm lượng clip nếu có. Vị trí dựa trên 720×1280, tự nhân tỷ lệ khi video nguồn là 1080p. PNG giữ nền trong suốt. **Phủ toàn khung** đặt X/Y=0, rộng=720 và giữ tỷ lệ nguồn; ảnh/clip không đúng 9:16 có thể chưa phủ hết chiều cao.
4. **Chèn đoạn rồi tiếp tục**: chèn ảnh/clip thành một đoạn toàn khung, video gốc tạm dừng rồi tiếp tục với nội dung/âm thanh gốc. Đoạn giữ tỷ lệ, thêm nền đen khi khác tỷ lệ. Ở chế độ này X/Y, chiều rộng và độ hiện không áp dụng; dùng thời điểm, thời lượng, offset, âm thanh và âm lượng. Video kết quả dài thêm bằng tổng thời lượng các đoạn chèn.
5. `Offset` là thời điểm bắt đầu trong clip nguồn. Clip ngắn được lặp để đủ thời lượng đã đặt. Ảnh là khung tĩnh; GIF xử lý như clip động.
6. **Cảnh = 0**: điểm chèn đoạn tính trên video gốc; thời điểm lớp phủ tính trên video sau khi chèn. **Cảnh > 0**: dùng số cảnh trong timeline do tool tạo; thời điểm là số giây tính từ đầu cảnh. Tool báo lỗi nếu vượt cảnh/video. Video ngoài hoặc bản chỉnh không có timeline thì chọn 0.
7. Nhập thời điểm xem trước và bấm **Cập nhật xem trước** để thấy bố cục ở giây đó. Xem trước ảnh tĩnh không phát âm thanh; video xuất có âm thanh theo lựa chọn.
8. **XUẤT BẢN CHỈNH SỬA** đưa việc vào Hàng đợi; bấm **Bắt đầu chạy**. Video gốc giữ nguyên, bản mới vào Thư viện để chọn đăng TikTok.

Có thể thêm nhiều lớp, xóa lớp, lưu/mở bộ media JSON. Lớp sau nằm trên lớp trước. Khi chọn tệp qua giao diện và lưu lớp, tool sao chép media vào `data/media_assets` để tránh mất liên kết nếu tệp nguồn bị di chuyển. Bộ JSON mở từ máy khác vẫn cần các đường dẫn media hợp lệ.

Muốn dùng cùng bộ media cho nhiều video mới, bật **Áp dụng bộ media này khi thêm lô video mới**, rồi thêm link/dự án vào hàng đợi. Các tác vụ giữ bản sao cài đặt riêng. Chọn thời điểm phù hợp với tất cả video trong lô; mục vượt thời lượng sẽ báo lỗi riêng.

Video ví dụ: `outputs/PRO21_meme_reaction_demo.mp4`, dùng meme/clip trích từ video mẫu 2 bạn cung cấp. Bộ mẫu: `outputs/demo_media_set.json`.

Mở **MO_PRO.cmd** hoặc **MO_TOOL.cmd** trong `C:\Tool_Thred`. Cả hai ưu tiên bản 2.1 tại `dist\ThreadsStudioPro21\ThreadsStudioPro.exe`. Bản 2.0 vẫn giữ ở thư mục cũ. Giữ EXE cùng thư mục `_internal`, `assets` và `data`; không chỉ sao chép riêng EXE. Trước khi tự đóng gói lại bằng PyInstaller, đóng ứng dụng và sao lưu thư mục `data`.

## Tạo nhiều video

1. Trong **Tạo hàng loạt**, dán nhiều link Threads, mỗi dòng một link; hoặc nhập TXT / CSV.
2. Chọn mẫu thẻ giữa, thẻ trên hoặc lưới xanh. Bật **Tạo cả 3 mẫu** nếu muốn ba video cho mỗi nguồn.
3. Chọn video nền, nhạc, giọng đọc, số bài tối đa, 720p/1080p và thư mục xuất. Số bài tính cả bài gốc. Có thể lưu cài đặt thành preset.
4. Bấm **THÊM LINK VÀO HÀNG ĐỢI**, rồi **Bắt đầu chạy**.
5. Máy mặc định dựng tối đa 2 tác vụ đồng thời; có thể chọn 1–3 ở **Cài đặt**. Tạm dừng chỉ ngừng nhận việc mới; **Hủy mục chọn** dừng tác vụ đã chọn.
6. Video thành công tự vào **Thư viện video**. Tác vụ lỗi có thông tin riêng, không làm hỏng cả lô. Có thể **Sửa tác vụ**, đổi giọng/tắt giọng, rồi **Thử lại mục lỗi** và **Bắt đầu chạy**.

Hàng đợi, lịch sử và preset được lưu trong SQLite. Sau khi đóng giữa chừng, tác vụ chưa xong chuyển sang **Gián đoạn**, không tự chạy lại. Chọn Thử lại khi muốn tiếp tục. Video đã hoàn tất được khôi phục vào thư viện mà không dựng lại.

## Chỉnh nội dung trước khi dựng

**Mở trình sửa & xem trước** mở cửa sổ chỉnh từng dự án. Lấy bài, sửa/thêm/xóa/sắp xếp bình luận, chọn mẫu và xem trước, rồi **Lưu** dự án. Quay lại Pro, dùng **Nhập dự án** để đưa một hoặc nhiều dự án đã chỉnh vào hàng đợi.

Threads chỉ cho lấy phần nội dung/bình luận công khai mà trang trả về. Đã sửa lỗi nhận nhầm link `/media` ở bài có ảnh; có phương án lấy bài gốc từ metadata công khai nếu phần giao diện chưa tải được. Khi dùng phương án dự phòng, tool nói rõ chưa có bình luận, không tự tạo bình luận hoặc số tương tác.

## Giọng đọc

Có giọng Việt Hoài My/Nam Minh, Malay, English và Emma đa ngôn ngữ. Một số thời điểm dịch vụ giọng Việt trả rỗng; tool thử lại và kiểm tra tệp âm thanh trước khi ghép. Lựa chọn **Dự phòng giọng đa ngôn ngữ** cho phép dùng Emma khi giọng Việt lỗi. Giọng thực dùng được ghi trong `timeline.json` cạnh video. Có thể tắt lựa chọn này nếu chỉ muốn đúng giọng đã chọn. Công cụ không tự dịch nội dung.

## Thư viện và chọn video đăng

- Video do Pro dựng xong tự xuất hiện trong thư viện; **Nhập MP4 có sẵn** cũng nhận các video có sẵn trên máy.
- Chọn một mục để xem ảnh, caption và đường dẫn; **Xem video** mở bằng trình phát của Windows.
- **Sửa caption** chỉnh caption và hashtag riêng cho từng video.
- Ctrl / Shift để chọn nhiều mục, rồi **Chọn để đăng TikTok**. Việc dựng xong không tự gửi hoặc đăng.

## TikTok Studio qua trình duyệt

Không cần tài khoản nhà phát triển TikTok cho cách này.

1. Tại tab TikTok, đặt tên hồ sơ (ví dụ `main`, `kenh_2`), bấm **Mở / đăng nhập**.
2. Đăng nhập hoặc quét QR trực tiếp trong cửa sổ Microsoft Edge. Tool dùng thư mục hồ sơ riêng, không đọc hồ sơ Edge/Chrome mặc định. Nếu có CAPTCHA, hoàn tất thủ công trên trang TikTok.
3. Chọn **một video** trong Thư viện, kiểm tra caption, bấm **Tải video đã chọn** và xác nhận.
4. Tool chọn tệp và điền caption vào TikTok Studio. Chờ tải xong, kiểm tra đúng tài khoản, quyền xem và các lựa chọn trên TikTok, rồi **bấm Đăng tại TikTok**.
5. Mỗi lượt dùng tab riêng. Tool không tự bấm Đăng và không coi “đã chọn tệp” là “đã đăng”. Sau khi nhìn thấy bài trên TikTok, có thể chọn lịch sử và bấm **Xác nhận đã đăng trên web** để ghi nhận thủ công.

TikTok thay đổi giao diện có thể khiến thao tác chọn tệp/điền caption cần làm thủ công; tool giữ tab và báo đường dẫn video. Đây là hỗ trợ trình duyệt, không phải API đã được TikTok bảo đảm. Chưa kiểm thử đăng thật khi chưa có phiên tài khoản của bạn.

## TikTok API — nhiều video đã chọn

Đây là lựa chọn bổ sung cho tài khoản có access token TikTok hợp lệ, đã được cấp quyền Content Posting API.

1. Trong Cài đặt nhập tên gợi nhớ và token được TikTok cấp. **Không gửi token vào cuộc trò chuyện.** Token lưu bằng Windows DPAPI của người dùng hiện tại, không ghi vào log hoặc CSV.
2. Chọn tài khoản và hình thức gửi ở tab TikTok:
   - **Gửi vào hộp thư TikTok** cần `video.upload`. TikTok gửi thông báo trong hộp thư; bạn mở TikTok để hoàn tất, chưa phải đã đăng. Caption lưu trong tool để tham khảo khi hoàn tất; API hộp thư không nhận caption.
   - **Đăng trực tiếp** cần `video.publish`. Bấm **Kiểm tra tài khoản**, xem đúng tên tài khoản, chọn quyền xem TikTok trả về. Không có quyền xem mặc định. Có lựa chọn nhãn AI và quyền bình luận; duet/stitch được tắt trong tích hợp hiện tại.
3. Chọn các video trong Thư viện. Trước khi gửi, tool hiển thị danh sách, tài khoản, hình thức và caption để xác nhận. Mỗi mục giữ một caption riêng.
4. Xem lịch sử và bấm **Tra cứu mục API đã chọn**. Chỉ `PUBLISH_COMPLETE` là API xác nhận đăng xong; `SEND_TO_USER_INBOX` là đã gửi vào hộp thư.

Ứng dụng API chưa qua audit bị TikTok hạn chế quyền đăng, bao gồm chế độ riêng tư. Giới hạn thời lượng/quyền xem lấy từ thông tin creator cho Direct Post; tool kiểm tra kích thước và gửi các phần video tuần tự. Token hết hạn cần cập nhật lại; chưa tích hợp màn hình OAuth tự xin/refresh token.

Tool lưu publish_id ngay sau khởi tạo, trước khi gửi dữ liệu. Nếu mất mạng hoặc đóng app giữa chừng, trạng thái **Cần kiểm tra** chặn tự gửi lại để tránh trùng bài. Kiểm tra TikTok hoặc tra cứu publish_id; chỉ dùng **Cho phép gửi lại sau kiểm tra** khi đã chắc chắn chưa đăng/chưa chờ xử lý. Chưa có chế độ hẹn giờ đăng hoặc tự chạy khi Windows đã tắt.

Tài liệu chính thức: [Direct Post](https://developers.tiktok.com/docs/en/content-posting-api-reference-direct-post), [Upload vào hộp thư](https://developers.tiktok.com/docs/en/content-posting-api-reference-upload-video), [Trạng thái](https://developers.tiktok.com/docs/en/content-posting-api-reference-get-video-status).

## Dữ liệu và sao lưu

- `data/studio.db`: hàng đợi, thư viện, preset, lịch sử và token được bảo vệ bằng Windows.
- `data/browser_profiles/`: phiên đăng nhập TikTok riêng. Đây là dữ liệu tài khoản; giữ trên máy của bạn.
- `outputs/`: video và thư mục `_project` chứa nội dung, thẻ PNG, âm thanh và timeline.
- `assets/`: nền gameplay và bộ nhớ đệm giọng đọc. Nền có sẵn là vùng cắt sạch từ video mẫu 2 nên góc nhìn hẹp; chọn footage sạch để đẹp hơn.
- **Xuất báo cáo CSV** xuất tình trạng sản xuất, không xuất token.
- Không xóa/di chuyển MP4 bên ngoài tool nếu vẫn muốn mở đúng đường dẫn trong thư viện. Muốn mang sang máy khác, nhập lại MP4/dự án và đăng nhập lại TikTok; DPAPI không giải mã được trên tài khoản Windows khác.

## Kiểm thử và chạy mã nguồn

Đã kiểm tra bài trong ảnh `@nguyenhoang9292/post/DgJ0tcYj8Rp`, lấy bài gốc + 30 bình luận; tạo video có giọng đọc tại `outputs/PRO_fixed_nguyenhoang_VN.mp4`. Kiểm thử lô ba mẫu nằm ở `outputs/pro_batch/` và báo cáo đo hai tác vụ dựng đồng thời tại `inspection/batch_verification/report.json`.

```powershell
python -m pip install -r requirements.txt
python pro.py
python -m unittest discover -s tests -v
python -m PyInstaller --noconfirm ThreadsStudioPro.spec
```

Windows cần Microsoft Edge, FFmpeg và ffprobe. Mã nguồn tách thành các phần: `store.py` (dữ liệu), `production.py` (hàng đợi), `source.py` (Threads), `render.py` (dựng), `browser_publish.py` (TikTok Studio), `tiktok.py` (API), `secrets.py` (DPAPI), `pro.py` (giao diện).
