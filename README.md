# VinBus Blind Spot Guard

Cảnh báo người đi bộ cắt ngang điểm mù của xe buýt VinBus, dùng **webcam** (thấy người) kết hợp **IMU điện thoại** (biết xe đang rẽ hay rung).

> Camera thấy người, IMU biết xe đang làm gì; ghép lại để không báo động giả khi chính chiếc xe rẽ hoặc rung.

## Cài đặt và chạy mô phỏng (5 phút)

### Cách A: chỉ xem mô phỏng 3D, không cần cài gì

1. Tải code về: trên trang GitHub bấm nút xanh **Code → Download ZIP**, giải nén. Hoặc dùng git:
   ```bash
   git clone https://github.com/ngminhquyen2710-sketch/day13.git
   ```
2. Mở thư mục vừa tải, **nháy đúp file `sim.html`**. Trang mở trong Chrome hoặc Edge.
3. Bấm vào trang một lần cho trình duyệt nhận bàn phím, rồi chọn kịch bản ở thanh trên cùng.

`sim.html` đã nhúng sẵn thư viện 3D nên chạy được khi không có mạng. Nếu nháy đúp mà máy mở bằng ứng dụng khác, chuột phải vào file → **Open with** → **Google Chrome** hoặc **Microsoft Edge**.

### Cách B: chạy cả bản camera thật (Python)

Cần **Python 3.9 trở lên**. Kiểm tra bằng `python --version`; nếu chưa có, cài từ [python.org](https://www.python.org/downloads/) và nhớ tích **Add Python to PATH**.

```bash
cd day13                                    # thư mục chứa main.py
python -m pip install -r requirements.txt   # lần đầu, cần mạng, mất vài phút
python demo.py                              # menu: bấm 1 để mở mô phỏng, 2-3 để chạy camera
```

Lần đầu chạy camera, chương trình tự tải model YOLO (khoảng 5 MB), nên hãy chạy thử một lần khi có mạng trước buổi thi.

### Dùng mô phỏng thế nào

| Bước | Làm gì | Thấy gì |
|---|---|---|
| 1 | Chọn **Rẽ ở ngã tư** (phím `6`) | Xe rẽ phải, người đứng chờ ở góc đường giữ màu xanh |
| 2 | Bấm `R` để chạy lại, rồi bấm `I` để **tắt bù IMU** | Người đứng yên có mũi tên vận tốc dài, xe phanh oan |
| 3 | Chọn **Rời bến** (phím `5`) | Người chạy qua đầu xe, cảnh báo chuyển vàng → cam → đỏ, xe tự phanh |
| 4 | Chọn **Trẻ em lao ra** (phím `7`) | Ca lỗi: em bị che khuất và bị ước lượng xa hơn thực tế |
| 5 | Chọn **Lái tự do** (phím `8`), giữ `Q` để chạy, bấm `1`–`4` để thả người | Cho giám khảo tự thử |
| 6 | Bấm nút **Chạy so sánh số liệu** | Bảng số báo động giả, phanh oan, cảnh báo kịp thời ở cả 3 kịch bản |

**Lỗi thường gặp**

| Hiện tượng | Cách sửa |
|---|---|
| Bấm phím không có tác dụng | Bấm chuột vào trang một lần để trình duyệt nhận bàn phím |
| Màn hình 3D đen hoặc rất giật | Bật tăng tốc phần cứng: Chrome → Settings → System → **Use graphics acceleration when available** |
| Bấm phím hiện ô nhỏ có chữ và phải Enter (cửa sổ camera Python) | Bộ gõ tiếng Việt đang giữ phím; chuyển sang gõ tiếng Anh (Unikey: `Ctrl + Shift`) |
| `No module named 'cv2'` | Chưa cài thư viện: chạy `python -m pip install -r requirements.txt` |
| `python` không được nhận | Thử `py` thay cho `python` |

## Cách nhanh nhất

**Mô phỏng 3D:** mở thẳng file `sim.html` bằng Chrome hoặc Edge (nháy đúp). Không cần cài gì, không cần mạng, không cần webcam.

**Menu demo:** `python demo.py`, rồi bấm một phím số (không cần Enter). Đóng cửa sổ camera bằng `q` hoặc `Esc` để quay lại menu.

> Nếu bấm `q` mà hiện một ô nhỏ có chữ "q" và phải Enter mới nhận: đó là bộ gõ tiếng Việt (Unikey / Telex của Windows) đang giữ phím. Chuyển sang gõ tiếng Anh (Unikey: `Ctrl + Shift`, bộ gõ Windows: `Windows + Space`) trước khi demo. Trang `sim.html` đọc phím vật lý nên không bị ảnh hưởng.

## 0. Mô phỏng 3D (`sim.html`)

Xe buýt VinBus chạy trên phố 3D có người đi bộ, nhà, cây, xe đỗ. Khung trái là **camera đầu xe** (góc 90°), khung phải là **bản đồ nhìn từ trên xuống**, đầu xe luôn hướng lên. Từ bước "camera thấy box người" trở đi, mô phỏng chạy **cùng thuật toán** với code Python: pinhole ra mét, Kalman có bù quay bằng con quay + bù tịnh tiến bằng tốc độ xe, dự báo thời gian đến va chạm (TTC), phanh tự động.

Vì biết vị trí thật của từng người, trang tự tính số liệu **ground truth**: báo động giả (cảnh báo mà 2,5 s sau vẫn không có nguy hiểm thật), phanh không cần thiết, nguy hiểm được báo trước ít nhất 0,5 s, va chạm, sai số khoảng cách.

**Ba kịch bản dựng sẵn**

| Kịch bản | Chuyện gì xảy ra | Để chứng minh |
|---|---|---|
| **Rời bến** (phím `5`) | Xe rời bến, một người chạy băng qua đầu xe để kịp lên xe | Dự báo quỹ đạo, cảnh báo trước khoảng 1,7 s, phanh tự động tránh va chạm |
| **Rẽ phải ở ngã tư** (phím `6`) | Xe rẽ phải, nhiều người đứng chờ ở góc đường, một người đang qua đường ở nhánh xe rẽ vào | Bù IMU: tắt bù (`I`) thì người đứng yên bị tưởng đang chạy, xe phanh oan |
| **Trẻ em lao ra** (phím `7`) | Em nhỏ chạy ra từ khe giữa hai ô tô đỗ | Ca lỗi: bị che khuất nên thấy muộn, thấp hơn giả định nên bị ước lượng xa hơn khoảng 48% |
| **Lái tự do** (phím `8`) | Bạn tự lái và thả người đi bộ | Cho giám khảo tự thử |

**Phím**

| Phím | Chức năng |
|---|---|
| `↑` hoặc `Q` (giữ) | Tăng tốc |
| `↓` hoặc `E` (giữ) | Giảm tốc; giữ đủ lâu thì xe dừng hẳn |
| `←` `→` (giữ) | Đánh lái |
| `1` `2` `3` `4` | Thả người cắt ngang từ phải / từ trái / người đứng yên / trẻ em lao ra |
| `I` | Bật/tắt bù IMU |
| `U` | Bật/tắt phanh tự động |
| `K` | Bật lỗi đồng bộ IMU 150 ms (ca lỗi) |
| `G` | Hiện/ẩn vị trí thật |
| `V` | Xóc ổ gà |
| `R` | Chạy lại kịch bản |
| `P` hoặc `Space` | Tạm dừng |

Đang chạy kịch bản mà bấm phím lái thì bạn giành quyền lái ngay.

**Nút "Chạy so sánh số liệu"** chạy nhanh cả 3 kịch bản, mỗi kịch bản 6 lần với nhiễu khác nhau, ở 3 chế độ, rồi in bảng. Kết quả lần chạy thử:

| Kịch bản | Chế độ | Báo động giả | Phanh oan | Báo kịp thời | Báo trước TB | Va chạm |
|---|---|---|---|---|---|---|
| Rời bến | Bật bù IMU | 1 | 1 | 6/6 | 1,7 s | 0 |
| Rẽ phải ở ngã tư | **Bật bù IMU** | **9** | **0** | 6/6 | 1,3 s | 0 |
| Rẽ phải ở ngã tư | Tắt bù IMU | 16 | 6 | 6/6 | 3,4 s | 0 |
| Rẽ phải ở ngã tư | Bật bù + lệch đồng bộ 150 ms | 12 | 0 | 6/6 | 1,3 s | 0 |
| Trẻ em lao ra | Bật bù IMU | 0 | 0 | 3/6 | 0,5 s | 0 |

Đọc bảng: khi xe rẽ, tắt bù IMU làm xe **phanh oan 6 lần** trong 6 lượt; bật bù thì không lần nào. Trẻ em lao ra chỉ được báo trước 0,5 s (người lớn 1,7 s): đây là ca lỗi để trình bày. Đây là số trong mô phỏng với nhiễu giả định, không phải số đo thật.

**Sửa mô phỏng:** mã nguồn nằm trong thư mục `web/` (`core.js` là thuật toán, `render.js` là đồ họa 3D, `app.js` là giao diện). Sửa xong chạy `python web/build.py` để tạo lại `sim.html`.

Bản mô phỏng Python cũ vẫn còn (`python simulate.py`, `python simulate.py --compare`) nếu cần.

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
| `sim.html`, `web/` | Mô phỏng 3D trên trình duyệt, 3 kịch bản, số liệu ground truth | Cả team |
| `simulate.py` | Mô phỏng Python cũ (2D) | Cả team |

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
