# Kịch bản video báo cáo — BeautyPrice Intelligence

- **Thời lượng dự kiến:** khoảng 7 phút 56 giây (lời thuyết minh), cộng thêm thời gian thao tác trên màn hình.
- **Phụ đề:** `reports/demo/phu_de_video.srt` — khớp sẵn với lời thuyết minh bên dưới, nạp thẳng vào phần mềm dựng phim.
- **Tư liệu có sẵn:** `reports/demo/demo.mp4` (bản quay màn hình toàn bộ 21 test case), `reports/demo/screens/` (ảnh từng bước), `reports/SLIDES_BAO_CAO.pptx`.

> Các chỗ «…» là thông tin nhóm tự điền. Lời thuyết minh viết theo văn nói để đọc cho tự nhiên.

## 1. Yêu cầu kỹ thuật cần đáp ứng

| Yêu cầu của đề bài | Cách thực hiện |
|---|---|
| Giới thiệu tên đồ án, nhóm, GVHD, nội dung, lời cảm ơn | Cảnh 1, 2, 3 và 15 |
| Logo trường, khoa trực thuộc và Khoa CNTT xuyên suốt | Đặt cụm logo ở góc trên bên phải, hiện trên mọi cảnh |
| Có thuyết minh | Lời đọc ở cột “Lời thuyết minh” bên dưới |
| Có phụ đề | Nạp `phu_de_video.srt`; kiểm tra lại nếu đọc nhanh hoặc chậm hơn dự kiến |
| Nhạc nền nhẹ xuyên suốt | Nhạc không lời, âm lượng khoảng 10–15% so với giọng đọc |
| Hình ảnh rõ, sắc nét | Quay màn hình ở độ phân giải 1920×1080, 30 khung hình/giây |
| Đủ các chức năng đã thực hiện | Cảnh 5 đến 12 đi qua toàn bộ chức năng |
| Có thành viên nhóm xuất hiện trình bày | Cảnh 1, 2 và 15 quay người thật; các cảnh còn lại lồng khung hình nhỏ ở góc |

## 2. Chuẩn bị trước khi quay

1. Chạy `reset.bat` để đưa cơ sở dữ liệu về đúng dữ liệu gốc, tránh số liệu lệch so với báo cáo.
2. Chạy `run.bat`, đăng nhập sẵn bằng `admin / Admin@123`.
3. Đặt trình duyệt ở chế độ toàn màn hình, thu nhỏ thanh dấu trang cho gọn.
4. Tăng cỡ chữ trình duyệt lên 110–125% để chữ rõ khi xem trên điện thoại.
5. Chuẩn bị sẵn một sản phẩm để demo sửa giá và một sản phẩm để demo xóa rồi phục hồi.

## 3. Kịch bản chi tiết

### 1. Mở đầu

**Thời lượng:** 00:00 – 00:26

**Hình ảnh:** Trang bìa có logo trường, logo Khoa Công nghệ Thông tin và Khoa Kinh tế. Tên đề tài hiện dần.

**Lời thuyết minh:**

> Xin chào thầy cô và các bạn.
> Chúng em là nhóm «số nhóm», lớp học phần ABDA433708, môn Phân tích dữ liệu lớn trong kinh doanh.
> Giảng viên hướng dẫn: «điền họ tên giảng viên».
> Hôm nay nhóm em xin trình bày đồ án BeautyPrice Intelligence: hệ thống thu thập, phân tích và dự đoán giá mỹ phẩm từ năm nhà bán lẻ trực tuyến tại Việt Nam.

### 2. Giới thiệu nhóm

**Thời lượng:** 00:26 – 00:48

**Hình ảnh:** Quay cận cảnh từng thành viên hoặc ảnh thẻ kèm tên, hiện lần lượt.

**Lời thuyết minh:**

> Nhóm em gồm năm thành viên.
> Bạn «tên» phụ trách dữ liệu thu thập ban đầu; bạn «tên» thiết kế cơ sở dữ liệu.
> Bạn «tên» làm phân tích khám phá và dashboard; bạn «tên» xây dựng các mô hình học máy.
> Và em, «tên», phụ trách công cụ thu thập và toàn bộ website.

### 3. Nội dung trình bày

**Thời lượng:** 00:48 – 01:07

**Hình ảnh:** Slide mục lục, mỗi mục sáng lên khi được nhắc tới.

**Lời thuyết minh:**

> Phần trình bày của nhóm gồm sáu nội dung.
> Một, bài toán và dữ liệu. Hai, công cụ thu thập đa nguồn.
> Ba, làm sạch và thiết kế cơ sở dữ liệu. Bốn, trực quan hóa dữ liệu.
> Năm, các mô hình học máy. Và sáu, demo website hoàn chỉnh.

### 4. Bài toán và dữ liệu

**Thời lượng:** 01:07 – 01:44

**Hình ảnh:** Slide 2 của bộ slides: vấn đề thực tế, mục tiêu và bốn ô số liệu.

**Lời thuyết minh:**

> Trên thị trường mỹ phẩm trực tuyến, cùng một sản phẩm có giá chênh lệch đáng kể giữa các website, và khuyến mãi thay đổi liên tục.
> Người mua khó so sánh thủ công, còn doanh nghiệp thì thiếu bức tranh tổng hợp để định giá.
> Nhóm em đã thu thập được năm nghìn sáu trăm năm mươi bảy sản phẩm, sáu nghìn ba trăm năm mươi bản ghi giá và sáu nghìn sáu trăm bảy mươi ba đánh giá của khách hàng.
> Dữ liệu trải trên sáu danh mục chăm sóc da và cơ thể, với bốn trăm mười tám thương hiệu.

### 5. Công cụ thu thập đa nguồn

**Thời lượng:** 01:44 – 02:27

**Hình ảnh:** Quay màn hình trang Thu thập dữ liệu: chọn nguồn, chọn danh mục, bấm Chạy thu thập ngay, nhật ký chạy dần.

**Lời thuyết minh:**

> Nhóm em tự xây dựng công cụ thu thập, chỉ dùng thư viện chuẩn của Python.
> Quản trị viên chọn nguồn, chọn danh mục và lượng dữ liệu muốn lấy, hệ thống sẽ ước tính thời gian trước khi chạy.
> Công việc chạy nền, nhật ký cập nhật liên tục và có thể dừng bất cứ lúc nào.
> Ngoài ra có thể đặt lịch tự động để hệ thống tự cập nhật giá theo chu kỳ.
> Một điểm nhóm em đặc biệt chú ý là đạo đức thu thập dữ liệu: công cụ đọc và tuân thủ robots dot txt, giãn cách giữa các yêu cầu, và khi website bật cơ chế chống bot thì chỉ ghi nhận trạng thái chứ không tìm cách vượt qua.

### 6. Làm sạch và cơ sở dữ liệu

**Thời lượng:** 02:27 – 03:12

**Hình ảnh:** Quay trang Báo cáo thống kê, cuộn xuống mục Chất lượng dữ liệu và quy trình làm sạch.

**Lời thuyết minh:**

> Dữ liệu thô có rất nhiều vấn đề: thương hiệu viết nhiều kiểu khác nhau, phần trăm giảm giá sai lệch, rating bằng không bị hiểu nhầm là không sao.
> Nhóm em viết chương trình làm sạch riêng, và điều quan trọng là mỗi bước xử lý đều được ghi lại.
> Thầy cô có thể xem toàn bộ quy trình ngay trên trang Báo cáo: bước nào, tác động lên bao nhiêu dòng.
> Dữ liệu sau khi làm sạch được nạp vào cơ sở dữ liệu SQLite gồm mười bảy bảng và hai view.
> Nhóm còn viết thêm một chương trình kiểm chứng độc lập: đọc thẳng tệp CSV bằng Python thuần, tự tính lại rồi so với kết quả truy vấn SQL. Hiện tất cả các mục đều đạt.

### 7. Trực quan hóa dữ liệu

**Thời lượng:** 03:12 – 03:47

**Hình ảnh:** Quay trang Tổng quan: đổi bộ lọc nhà bán lẻ, các biểu đồ cập nhật theo. Sau đó sang trang Báo cáo, phần min – max.

**Lời thuyết minh:**

> Trang Tổng quan cho biết bức tranh thị trường: tỷ trọng theo nhà bán lẻ, phân bố khoảng giá, giá theo danh mục và mức khuyến mãi.
> Mọi biểu đồ đều phản ứng theo bộ lọc. Khi em chọn một nhà bán lẻ, toàn bộ chỉ số và biểu đồ cập nhật ngay.
> Trang Báo cáo có riêng mục danh sách giá trị nhỏ nhất và lớn nhất theo danh mục, theo nhà bán lẻ và theo từng chỉ số.
> Nhóm em dùng tám loại biểu đồ khác nhau, với bảng màu đã kiểm tra khả năng phân biệt cho người mù màu.

### 8. Tra cứu và CRUD

**Thời lượng:** 03:47 – 04:20

**Hình ảnh:** Quay trang Tra cứu: gõ tìm kiếm không dấu, mở chi tiết sản phẩm xem lịch sử giá và đánh giá, rồi sửa giá một sản phẩm.

**Lời thuyết minh:**

> Trang Tra cứu hỗ trợ tìm kiếm không dấu, nên gõ không dấu vẫn ra đúng kết quả.
> Mở chi tiết một sản phẩm, ta thấy lịch sử giá theo thời gian và các đánh giá của khách hàng.
> Quản trị viên có thể thêm, sửa, xóa sản phẩm. Khi sửa giá, hệ thống không ghi đè mà thêm một bản ghi giá mới, nhờ vậy lịch sử giá được giữ nguyên.
> Dữ liệu nhập vào đều được kiểm tra: giá phải lớn hơn không, giá niêm yết không được nhỏ hơn giá bán.

### 9. Mô hình học máy

**Thời lượng:** 04:20 – 05:11

**Hình ảnh:** Lần lượt quay ba trang: Dự đoán giá, Phân khúc K-Means, Phát hiện bất thường.

**Lời thuyết minh:**

> Nhóm em xây dựng bốn bài toán học máy.
> Bài toán thứ nhất là dự đoán giá bán. Nhóm so sánh bốn mô hình và chọn Random Forest, đạt sai số trung bình chín mươi nghìn đồng.
> Bài toán thứ hai là phân loại phân khúc giá thành ba mức thấp, trung bình và cao, đạt độ chính xác bảy mươi ba phẩy năm phần trăm.
> Bài toán thứ ba là phân cụm sản phẩm bằng K-Means. Nhóm thử k từ hai đến mười và chọn k bằng bảy theo chỉ số silhouette.
> Bài toán thứ tư là phát hiện bất thường bằng Isolation Forest, đánh dấu hai trăm tám mươi ba sản phẩm có giá hoặc mức giảm khác thường, kèm lý do cụ thể.
> Mô hình cho thấy thương hiệu là yếu tố quyết định giá, chiếm ba mươi tám phần trăm độ quan trọng.

### 10. Phân quyền

**Thời lượng:** 05:11 – 05:32

**Hình ảnh:** Đăng xuất, đăng nhập lại bằng tài khoản user, cho thấy mất nút Thêm Sửa Xóa và mất menu quản trị.

**Lời thuyết minh:**

> Hệ thống có hai vai trò: quản trị viên và người dùng.
> Khi đăng nhập bằng tài khoản người dùng thường, các nút thêm, sửa, xóa bị ẩn và menu quản trị biến mất.
> Phân quyền được kiểm tra ở cả hai phía. Nếu gọi thẳng vào API, máy chủ vẫn từ chối với mã bốn trăm lẻ ba.

### 11. Kết xuất và sao lưu

**Thời lượng:** 05:32 – 06:05

**Hình ảnh:** Bấm Xuất CSV ở trang Tra cứu, bấm In PDF ở trang Báo cáo. Sau đó sang trang Sao lưu, tạo bản sao lưu, xóa một sản phẩm rồi phục hồi.

**Lời thuyết minh:**

> Dữ liệu có thể xuất ra tệp CSV ở bốn màn hình, và trang Báo cáo còn in được ra PDF.
> Về an toàn dữ liệu, hệ thống có chức năng sao lưu và phục hồi.
> Em tạo một bản sao lưu, sau đó cố tình xóa một sản phẩm để giả lập mất dữ liệu.
> Khi phục hồi, hệ thống tự tạo một bản an toàn trước, rồi so sánh số dòng của mười ba bảng với bản sao lưu.
> Kết quả hiển thị khớp một trăm phần trăm, và sản phẩm vừa xóa đã xuất hiện trở lại.

### 12. Kiểm thử

**Thời lượng:** 06:05 – 06:26

**Hình ảnh:** Chạy lệnh kiểm thử trong terminal, cho thấy kết quả OK; rồi chiếu bảng test case trong reports.

**Lời thuyết minh:**

> Toàn bộ hệ thống được kiểm thử tự động.
> Phía máy chủ có hai mươi mốt kiểm thử, phía giao diện có hai mươi mốt test case chạy thật trên trình duyệt.
> Tất cả đều đạt, không có lỗi JavaScript nào. Ảnh chụp và video của từng bước được lưu làm bằng chứng.

### 13. Nhận định về dữ liệu

**Thời lượng:** 06:26 – 06:58

**Hình ảnh:** Slide nhận định với bốn ô số liệu lớn.

**Lời thuyết minh:**

> Từ dữ liệu, nhóm em rút ra ba nhận định chính.
> Thứ nhất, giảm giá là trạng thái bình thường chứ không phải ngoại lệ: bảy mươi sáu phần trăm sản phẩm đang giảm giá.
> Thứ hai, thị trường rất phân mảnh. Có bốn trăm mười tám thương hiệu nhưng tám thương hiệu dẫn đầu chỉ chiếm hai mươi mốt phần trăm.
> Thứ ba, điểm đánh giá gần như mất khả năng phân biệt chất lượng, vì gần chín mươi phần trăm đánh giá đều là năm sao.

### 14. Kết luận

**Thời lượng:** 06:58 – 07:33

**Hình ảnh:** Slide đối chiếu yêu cầu đề bài, các dòng lần lượt hiện dấu Đạt.

**Lời thuyết minh:**

> Đối chiếu với yêu cầu của đề bài, nhóm em đã hoàn thành đầy đủ các nội dung bắt buộc.
> Cả bốn chức năng điểm cộng cũng đã thực hiện: công cụ thu thập đa nguồn, tìm kiếm và lọc, CRUD, và kết xuất báo cáo ra tệp.
> Nhóm cũng nhìn nhận các hạn chế: dữ liệu mới trải trên bốn ngày, và mô hình còn thiếu thông tin về thành phần, xuất xứ sản phẩm.
> Hướng phát triển tiếp theo là bật lịch thu thập hằng ngày để tích lũy lịch sử giá đủ dài cho việc dự báo xu hướng.

### 15. Cảm ơn

**Thời lượng:** 07:33 – 07:56

**Hình ảnh:** Toàn nhóm xuất hiện trên khung hình. Slide cuối với lời cảm ơn và địa chỉ kho mã nguồn.

**Lời thuyết minh:**

> Phần trình bày của nhóm em đến đây là kết thúc.
> Nhóm em xin chân thành cảm ơn thầy cô đã hướng dẫn, và cảm ơn các bạn đã theo dõi.
> Toàn bộ mã nguồn của đồ án được lưu công khai trên GitHub tại địa chỉ hiển thị trên màn hình.
> Nhóm em rất mong nhận được góp ý từ thầy cô và các bạn.

## 4. Sau khi dựng xong

- Xem lại toàn bộ video một lượt, kiểm tra phụ đề có khớp với giọng đọc không.
- Kiểm tra logo hiện đủ ở mọi cảnh và không che mất nội dung quan trọng.
- Xuất ở định dạng MP4, độ phân giải 1920×1080.
- Đặt tên tệp theo cấu trúc nộp bài và để trong thư mục `reports/`.
