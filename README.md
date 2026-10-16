# VinBus Blind Spot Guard

Cảnh báo người đi bộ cắt ngang điểm mù của xe buýt VinBus, dùng **webcam** (thấy người) kết hợp **IMU điện thoại** (biết xe đang rẽ hay rung).

> Camera thấy người, IMU biết xe đang làm gì; ghép lại để không báo động giả khi chính chiếc xe rẽ hoặc rung.

## Cách nhanh nhất: menu demo

```bash
python demo.py
```
Chọn số để chạy camera thật, mô phỏng, hoặc in bảng số liệu. Đóng cửa sổ đang chạy bằng phím `q` sẽ quay lại menu, nên khi trình bày có thể chuyển qua lại giữa camera và mô phỏng.

## 0. Mô phỏng (không cần webcam, không cần điện thoại)

```bash
python simulate.py              # mở cửa sổ mô phỏng, tự chạy kịch bản demo 24 giây lặp lại
python simulate.py --manual     # tự điều khiển bằng phím
python simulate.py --compare    # chạy nhanh 10 lần, in bảng số liệu so sánh
```

Thế giới ảo gồm xe buýt (camera đầu xe góc rộng + con quay) trên một con đường có người đi bộ. Từ bước "camera thấy box người" trở đi, mô phỏng dùng **đúng code thật** của hệ thống (`vision.py` → `tracker.py` → `risk.py` → `ui.py`). Vì biết vị trí thật của từng người, thanh dưới cùng tự tính số liệu **ground truth**: báo động giả, cảnh báo kịp thời, sai số khoảng cách. Ô vuông trắng trên bản đồ là vị trí thật.

**Kịch bản tự động** (chữ phụ đề ở dưới khung hình báo đang ở cảnh nào):
1. Ba người đứng yên bên đường.
2. Xe rẽ phải, trái nhiều lần: người đứng yên không được gây báo động. Bấm `i` để tắt bù IMU và xem báo động giả xuất hiện.
3. Người lớn cắt ngang trước xe.
4. Trẻ em cắt ngang: **ca lỗi**, vì thấp nên hệ thống tưởng ở xa hơn khoảng 50%.
5. Xe đi qua ổ gà: thanh "camera trust" tụt.
6. Người cắt ngang trong lúc xe đang rẽ.

| Phím | Chức năng |
|---|---|
| `p` | Bật/tắt kịch bản tự động |
| `1` / `2` | Người cắt ngang từ phải / trái |
| `3` | Người đứng yên bên đường |
| `4` | Trẻ em cắt ngang |
| `5` | Người đi bộ dọc vỉa hè |
| `a` / `d` | Xe rẽ trái / phải (1 giây, 45°) |
| `w` / `s` | Tăng / giảm tốc độ xe |
| `v` | Xóc ổ gà |
| `k` | Bật lỗi đồng bộ thời gian IMU 150 ms (ca lỗi) |
| `i` | Bật/tắt bù IMU |
| `g` | Hiện/ẩn vị trí thật |
| `z` | Đặt lại số liệu |
| `x` | Xóa hết người |
| `r` | Quay video màn hình (lưu trong `logs/`) |
| `h` / `q` | Hướng dẫn / thoát |

**Kết quả `python simulate.py --compare`** (10 lần kịch bản, 30 lượt người đứng yên, 30 lượt cắt ngang):

| Chế độ | Báo động giả | Cảnh báo kịp thời (≥ 0,5 s) | Thời gian báo trước TB | Sai số khoảng cách người lớn / trẻ em |
|---|---|---|---|---|
| Tắt bù IMU | 148 | 27/30 | 1,45 s | 4% / 46% |
| **Bật bù IMU** | **0** | **28/30** | **1,51 s** | 4% / 47% |
| Bật bù + lệch đồng bộ 150 ms | 198 | 24/30 | 1,24 s | 4% / 47% |

Đọc bảng: bù IMU xóa gần như toàn bộ báo động giả mà không làm mất cảnh báo thật; nhưng nếu đồng bộ thời gian sai 150 ms thì bù lệch pha và còn tệ hơn không bù. Đây là lý do phải đo độ trễ (phím `l` ở chế độ thật). Lưu ý đây là số trong mô phỏng, nhiễu được giả định; số đo thật trong lớp sẽ khác.

## 1. Cài đặt (làm trước buổi thi)

```bash
git clone <repo>
cd vinbus-blindspot
pip install -r requirements.txt
python main.py --imu sim        # chạy thử lần đầu: tự tải model yolo11n.pt (~5 MB)
```

Cần Python 3.9 trở lên. Phải chạy thử một lần khi có mạng để tải model.

## 2. Kết nối IMU điện thoại (Phyphox)

1. Cài app **Phyphox** (Android / iPhone, miễn phí).
2. Bật **hotspot** trên điện thoại, cho laptop kết nối vào hotspot đó (không phụ thuộc Wi-Fi lớp học).
3. Trong Phyphox mở thí nghiệm **Gyroscope (rotation rate)** → menu ⋮ → **Allow remote access**. App hiện một URL, ví dụ `http://192.168.43.1:8080`.
4. Kiểm tra từ laptop:
   ```bash
   python imu.py --probe http://192.168.43.1:8080
   ```
   Phải thấy danh sách buffer có `gyrX, gyrY, gyrZ, gyr_time`. Nếu tên khác, sửa mục `imu.buffers` trong `config.yaml`.
5. Dán điện thoại cố định lên mép màn hình laptop (để cùng quay với webcam).
6. Chạy:
   ```bash
   python main.py --url http://192.168.43.1:8080
   ```

## 3. Hiệu chuẩn (mỗi máy làm 1 lần, kết quả lưu vào `calib.json`)

| Phím | Việc | Cách làm |
|---|---|---|
| `c` | Tiêu cự camera | 1 người đứng cách webcam đúng 2 m (sửa `calibration.distance_m` nếu khác), bấm `c` |
| `b` | Bias con quay | Để laptop yên 1 giây, bấm `b` (khi mới kết nối hệ thống tự làm) |
| `t` | Trục quay | Xoay laptop **sang phải** một lần rồi bấm `t` ngay |
| `l` | Độ trễ camera/IMU | Bấm `l`, trong 5 giây gõ mạnh vài lần xuống bàn |

## 4. Phím tắt khi chạy

| Phím | Chức năng |
|---|---|
| `i` | Bật/tắt bù IMU (dùng khi demo so sánh) |
| `d` | Đo khoảng cách: 1 người đứng yên, ghi 30 khung hình |
| `m` | Sang lượt thử mới (đánh dấu trong log) |
| `r` | Bật/tắt quay video màn hình (video dự phòng) |
| `h` | Ẩn/hiện bảng phím tắt |
| `[` `]` `v` | Chế độ `--imu sim`: giữ để giả lập rẽ trái/phải, rung |
| `q` | Thoát |

## 5. Các chế độ chạy

```bash
python main.py                                   # webcam + Phyphox (theo config.yaml)
python main.py --imu sim                         # webcam + IMU giả lập bằng phím
python main.py --source video.mp4 --imu sim --loop   # chạy trên video (máy không có webcam)
python main.py --source video.mp4 --headless     # không mở cửa sổ, ghi ra logs/.../output.mp4
python analyze.py                                # tổng hợp số liệu phiên mới nhất
```

## 6. Hệ thống hoạt động thế nào

```
Webcam ─► YOLO (người) ─► Pinhole: Z = f·H/h ─┐
                                              ├─► Kalman (x, z, vx, vz) ─► Rủi ro (vùng + TTC) ─► Cảnh báo
Phyphox gyro ─► đồng bộ thời gian ─► góc quay ┘        ▲
            └─► độ rung ─► tăng nhiễu đo ──────────────┘
```

| File | Phần | Người phụ trách |
|---|---|---|
| `vision.py` | YOLO, mô hình pinhole ra mét | A – Vision |
| `ui.py` | Giao diện, bản đồ nhìn từ trên xuống (BEV) | A – Vision |
| `imu.py` | Đọc Phyphox, đồng bộ đồng hồ, bias, trục quay, độ rung, IMU giả lập | B – IMU |
| `latency.py` | Đo độ trễ camera so với IMU bằng tương quan chéo | B – IMU |
| `tracker.py` | Kalman vận tốc không đổi + bù quay, ghép detection vào track | C – Tracking |
| `risk.py` | Vùng nguy hiểm, hành lang đường đi, TTC, mức cảnh báo | C – Tracking |
| `recorder.py`, `analyze.py` | Ghi log CSV, tổng hợp số liệu | C – Bằng chứng |
| `main.py` | Ghép tất cả, phím tắt | Cả team |
| `simulate.py` | Thế giới ảo + kịch bản demo + số liệu ground truth | Cả team |

**Mức cảnh báo**
- **STOP**: người đã ở trong vùng nguy hiểm sát đầu xe (2 m).
- **DANGER**: người đang di chuyển, dự báo cắt vào đường đi của xe trong < 1,5 s.
- **CAUTION**: dự báo cắt vào trong 3 s, hoặc đang đứng trong đường đi.
- **SAFE**: còn lại.

Khi xe rẽ (theo gyro), vùng nguy hiểm nới rộng về phía rẽ. Khoảng cách dùng bản **thận trọng** (giả định người thấp 1,50 m, nên gần hơn) để cảnh báo sớm hơn.

**Đọc bản đồ BEV:** chấm đặc = vị trí sau Kalman; dấu × xám = đo thô từ một khung hình; elip = vùng bất định 2σ; vòng rỗng = vị trí thận trọng; mũi tên = vận tốc trong 1 s; chấm nhỏ = quỹ đạo dự báo; hai đường xám = góc nhìn camera.

## 7. Kịch bản demo (4 phút)

1. **Cắt ngang thật:** giám khảo đi ngang trước camera ở 2–3 m → CAUTION → DANGER (có TTC) → STOP khi bước vào vùng.
2. **Đứng yên + xoay laptop, TẮT bù IMU (`i`):** người đứng yên lệch sang một bên, xoay laptop → hệ thống tưởng người đang chạy ngang → **báo động giả**.
3. **Bật lại bù IMU (`i`), xoay y hệt:** mũi tên vận tốc gần như biến mất, không báo động. *Đây là khoảnh khắc chứng minh giá trị hợp nhất cảm biến.*
4. **Xoay sang phải:** vùng nguy hiểm nở rộng bên phải ("TURN RIGHT").
5. **Gõ bàn:** thanh "camera trust" tụt, elip bất định to ra, quỹ đạo vẫn mượt.

## 8. Lấy số liệu cho phần Bằng chứng

**Số chính – báo động giả khi xe rẽ:**
1. Bấm `m` (lượt 1), tắt bù (`i`). Một người đứng yên lệch bên, xoay laptop qua lại 10 lần.
2. Bấm `m` (lượt 2), bật bù (`i`). Lặp lại y hệt.
3. `python analyze.py` → bảng số sự kiện DANGER/STOP theo lượt và chế độ.

Kết quả mô phỏng của chính code này (12 người đứng yên ở các vị trí khác nhau, xe quay 40° rồi quay về): **không bù 17 lần báo động giả, có bù 2 lần**; người cắt ngang thật vẫn được phát hiện đủ 6/6 ở cả hai chế độ. Số đo thật trong lớp có thể khác, hãy dùng số team tự đo.

**Sai số khoảng cách:** đứng ở 1, 2, 3, 4 m (thước dây hoặc đếm gạch sàn), mỗi mốc bấm `d`. Mở `logs/<phiên>/distance.csv`, điền cột `true_distance_m`, chạy lại `analyze.py` để ra sai số %. So `raw_std` với `kf_std` để thấy Kalman giảm rung.

**Độ trễ:** phím `l`, kết quả ghi vào `latency.csv`.

## 9. Ca lỗi và giới hạn (nói thẳng với hội đồng)

- **Người ngồi, cúi, hoặc trẻ em:** box thấp nên bị tính xa hơn thực tế. Nguyên nhân: giả định chiều cao trong công thức pinhole. Giảm bớt bằng chế độ thận trọng nhưng không loại bỏ được.
- **Đứng quá gần, box bị cắt ở mép khung hình:** hiện "(cut?)", nhiễu đo bị tăng lên.
- **Xe đi thẳng nhanh:** gyro chỉ đo quay, không bù được chuyển động tịnh tiến (tích phân gia tốc bị trôi rất nhanh). Xe thật cần thêm tốc độ từ đồng hồ xe hoặc GPS.
- **Wi-Fi chập chờn:** độ trễ IMU thay đổi, bù lệch thời gian, báo động giả quay lại.
- **Quy mô:** trong lớp khoảng cách chỉ 1–5 m; trên xe thật cần chỉnh kích thước vùng và ngưỡng TTC theo xe.

## 10. Xử lý sự cố

| Lỗi | Cách sửa |
|---|---|
| `Khong mo duoc nguon video: 0` | Thử `--source 1`, hoặc đóng Zoom/Meet đang chiếm webcam |
| `phyphox error: ConnectTimeout` | Sai IP, laptop chưa vào hotspot, hoặc app chưa bật remote access |
| `phyphox: buffer ... not found` | Chạy `python imu.py --probe <url>`, sửa tên trong `config.yaml` |
| FPS thấp | Giảm `detector.imgsz` xuống 480 hoặc 320 |
| Khoảng cách sai nhiều | Hiệu chuẩn lại bằng `c` trên đúng máy demo |
