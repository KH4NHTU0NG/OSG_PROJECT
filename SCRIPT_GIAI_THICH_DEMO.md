# 🎓 KỊCH BẢN THUYẾT TRÌNH & GIẢI THÍCH CHI TIẾT TỪNG FILE ĐỒ ÁN
**Tên đồ án:** Hệ thống Giám sát, Tự phục hồi Dịch vụ & Chẩn đoán tự động bằng AI (AI Service Monitor v4.0 - Enterprise SOC)  
**Mục tiêu:** Cung cấp kịch bản giải thích mạch lạc, chuyên sâu cho từng tệp tin trong mã nguồn khi trình diễn trước Thầy Cô / Hội đồng bảo vệ đồ án.

---

## 🏗️ PHẦN 1: KIẾN TRÚC TỔNG THỂ & VAI TRÒ CỦA TỪNG THƯ MỤC/FILE

### 1. Thư mục `backend/` (Trung tâm xử lý - Core Brain & SOC Dashboard)

#### 📄 `backend/app.py` (Trái tim của hệ thống - Backend Controller)
- **Vai trò chính:** Là máy chủ web API (dựa trên Flask) chịu trách nhiệm toàn bộ logic giám sát, tự khôi phục dịch vụ (`Auto-Remediation`), xử lý cảnh báo tài nguyên và tích hợp trí tuệ nhân tạo (LLM Groq API).
- **Điểm nổi bật về kỹ thuật (Cần nhấn mạnh với Hội đồng):**
  - **Luồng giám sát ngầm đa luồng (`auto_tracker_loop` daemon thread):** Tự động lặp lại mỗi 3 giây để kiểm tra trực tiếp trạng thái `systemctl is-active` của các dịch vụ cốt lõi (`httpd`, `sshd`, `crond`). Đảm bảo hệ thống luôn tự động phản ứng mà không cần tác động thủ công.
  - **Cơ chế Tự phục hồi & Phân tích nguyên nhân (`handle_crash` & `analyze_and_notify`):** Ngay khi phát hiện dịch vụ bị sập (`crashed`), Backend tự động thu thập 30 dòng log gần nhất qua `journalctl -u <service>`, ra lệnh `systemctl restart <service>` để cứu sống dịch vụ trong tích tắc, đồng thời gửi log cho LLM Llama-3.1-8b-instant để phân tích nguyên nhân gốc rễ (`Root Cause Analysis`).
  - **Tuân thủ nguyên tắc Zero Hallucination (Không suy diễn ảo):** Prompt AI được khóa chặt với các quy tắc kỹ thuật nghiêm ngặt. Nếu log hiển thị `Stopping` / `Stopped`, AI bắt buộc kết luận là **Quản trị viên tắt thủ công hợp lệ (`Graceful Stop`)**; chỉ khi có `SIGSEGV` / `Signal 11` hoặc `OOM` thì mới báo lỗi nghiêm trọng (`CRITICAL / HIGH`).
  - **Giám sát tài nguyên an toàn POSIX (`get_system_metrics_safe`):** Đọc trực tiếp từ `/proc/stat` và `ps` để tính toán phần trăm CPU, RAM, Disk một cách độc lập, không phụ thuộc vào ngôn ngữ hay vùng cấu hình (`locale`) của hệ điều hành CentOS.
  - **Trợ lý ảo AI DevOps Copilot (`/api/chat`) & Cửa sổ lệnh One-Click (`/api/execute_fix`):** Cho phép Quản trị viên hỏi đáp 24/7 và ra lệnh Linux bằng tiếng tự nhiên. Khi AI trả về lệnh dạng `[[RUN_COMMAND: <bash>]]`, Backend tự động thực thi bash ngầm trên CentOS và báo cáo kết quả.
  - **Cảnh báo qua Email (Gmail SMTP tự động):** Tự động gửi email tức thì cho Admin ngay khi phát hiện dịch vụ sập, tài nguyên vượt ngưỡng (`CPU > 90%`, `RAM > 85%`) hoặc **khi người dùng ra lệnh khởi động lại (`restart / systemctl`) qua AI Copilot**.

---

#### 📄 `backend/templates/index.html` (Giao diện Trung tâm Điều hành SOC - Frontend Dashboard)
- **Vai trò chính:** Là giao diện Web Single-Page Application (SPA) hiển thị trực quan toàn bộ trạng thái hệ thống theo thời gian thực theo phong cách Enterprise SOC (Security Operations Center).
- **Điểm nổi bật về kỹ thuật:**
  - **Thiết kế Glassmorphism & Dark Mode hiện đại:** Tông màu xanh navy đậm tinh tế, hiệu ứng bóng mờ cao cấp, giúp bảng điều khiển mang dáng dấp chuyên nghiệp của hệ thống giám sát doanh nghiệp lớn.
  - **Cập nhật thời gian thực bằng Polling không đồng bộ (`pollingTimer` & `updateUI`):** Định kỳ mỗi 1 giây tự động gọi API `/api/status` để vẽ biểu đồ dòng thời gian CPU/RAM bằng **Chart.js**, cập nhật danh sách dịch vụ `Online/Offline` và hiển thị nhật ký chẩn đoán AI (`Incident Log`).
  - **Bộ chuyển đổi Markdown & Bảng biểu nâng cao (`function md(text)`):** Tự động phân tích các bảng Markdown (`| Tham số | Giá trị |`) trả về từ AI Copilot thành bảng HTML với đường viền, màu sắc nổi bật, hỗ trợ hiển thị thẻ lệnh `code`, chữ đậm và danh sách gọn gàng mà không bao giờ bị lỗi hiển thị thẻ thô (`double-escaping protection`).
  - **Hộp thoại Terminal chẩn đoán nhanh (`termModal`):** Khi người dùng bấm nút **"Execute Diagnostic Fix"** trên thẻ sự cố, cửa sổ Terminal mô phỏng sẽ bật ra, hiển thị trực tiếp dòng lệnh đang chạy trên máy chủ CentOS và trả về output ngay lập tức.
  - **Khung Chat Copilot AI tích hợp (`chatPanel`):** Giao diện chat nổi 24/7 cho phép Admin nhập câu lệnh, hiển thị hộp `🛠️ Executed command` chuyên biệt mỗi khi AI thực thi lệnh trên hệ thống.

---

#### 📄 `backend/requirements.txt` & `backend/.env.example` (Cấu hình & Phụ thuộc)
- **`requirements.txt`:** Danh sách các thư viện Python tối giản, mạnh mẽ (`Flask`, `flask-cors`, `groq`, `requests`), đảm bảo cài đặt nhanh chóng và không gây nặng máy ảo.
- **`.env.example`:** Mẫu tệp cấu hình chứa khóa API Groq (`GROQ_API_KEY`) và thông tin đăng nhập Gmail SMTP (`SMTP_EMAIL`, `SMTP_APP_PASSWORD`), tách biệt hoàn toàn mã nguồn khỏi dữ liệu nhạy cảm.

---

### 2. Thư mục `agent/` (Hệ thống giám sát phân tán - Systemd Agent Template)

#### 📄 `agent/ai_monitor_service.sh` (Kịch bản giám sát Bash chuẩn POSIX)
- **Vai trò chính:** Là Agent thu thập số liệu chạy độc lập bên dưới hệ điều hành Linux, được systemd gọi định kỳ để kiểm tra dịch vụ và báo cáo về Backend.
- **Điểm nổi bật về kỹ thuật:**
  - **Tuân thủ chuẩn POSIX Shell (`#!/bin/sh`):** Không phụ thuộc vào Bash cụ thể, có thể chạy trên cả CentOS, Ubuntu, Debian hay Alpine Linux.
  - **Thu thập đa chiều:** Kiểm tra trạng thái dịch vụ (`systemctl is-active`), tự tính toán lượng CPU và RAM mà tiến trình đó đang chiếm giữ bằng `ps aux`, lấy thời gian kiểm tra chính xác.
  - **Báo cáo HTTP POST an toàn:** Sử dụng `curl -s -X POST -H "Content-Type: application/json"` để gửi payload JSON về `http://127.0.0.1:5000/api/report`. Có xử lý lỗi nếu Backend tạm thời không phản hồi.

---

#### 📄 `agent/ai-monitor@.service` & `agent/ai-monitor@.timer` (Template Systemd chuyên nghiệp)
- **Vai trò chính:** Tận dụng cơ chế **Systemd Template Unit (`@`)** của Linux để biến kịch bản bash thành tiến trình giám sát tự động cho bất kỳ dịch vụ nào mà không cần viết lại code.
- **Điểm nổi bật về kỹ thuật:**
  - **`ai-monitor@.service`:** Định nghĩa unit chạy lệnh `/opt/ai-service-monitor/agent/ai_monitor_service.sh %i` (trong đó `%i` là tên dịch vụ truyền vào, ví dụ `httpd`, `sshd`, `docker`).
  - **`ai-monitor@.timer`:** Định nghĩa bộ định thời gian (`OnUnitActiveSec=5s`), ra lệnh cho systemd tự động kích hoạt service trên mỗi 5 giây một cách chuẩn xác ở cấp độ nhân hệ điều hành (`Kernel/Systemd level`).

---

### 3. Các tệp Tài liệu Hướng dẫn & Kịch bản (`README.md`, `README_CENTOS.md`, `DEMO_AI_CHATBOX_V4.5.md`)

#### 📄 `README.md` & `README_CENTOS.md` (Sổ tay cài đặt & Kịch bản Demo chuẩn SOC)
- **Vai trò chính:** Tài liệu hướng dẫn từ A-Z, bao gồm lệnh cài đặt nhanh trên CentOS 10, cách cấu hình tường lửa (`firewall-cmd`), xử lý quyền sở hữu Git (`safe.directory`) và danh sách 6 kịch bản demo thực tế.
- **Điểm nổi bật:**
  - Cung cấp các lệnh **stress test cực mạnh trong 20 giây** (`stress --cpu 16 --timeout 20` và `stress --vm 2 --vm-bytes 1024M --timeout 20`) giúp trình diễn khả năng cảnh báo tài nguyên và gửi mail siêu tốc trước Hội đồng mà không làm treo máy.

#### 📄 `DEMO_AI_CHATBOX_V4.5.md` (Kịch bản thuyết trình trực tiếp - Live Presentation Script)
- **Vai trò chính:** Kịch bản từng lời nói, từng bước gõ lệnh được thiết kế riêng cho buổi bảo vệ đồ án, giúp Quản trị viên tự tin làm chủ sân khấu và phô diễn đầy đủ tính năng ưu việt của AI Service Monitor.

---

## 🎬 PHẦN 2: KỊCH BẢN NÓI KHI TRÌNH DIỄN (SUGGESTED TALKING POINTS)

1. **Khi mở mã nguồn `app.py` giới thiệu kiến thức Linux/Python:**
   > *"Kính thưa Hội đồng, điểm cốt lõi trong kiến trúc Backend của nhóm em nằm ở tệp `app.py`. Thay vì chỉ giám sát thụ động, hệ thống tích hợp một luồng ngầm `auto_tracker_loop` và cơ chế `handle_crash`. Ngay khi một dịch vụ như `crond` hay `httpd` bị sập, hệ thống chỉ mất chưa tới 0.1 giây để tự động `restart` khôi phục dịch vụ, đồng thời trích xuất 30 dòng log hệ thống gửi lên mô hình LLM Llama-3.1 nhằm phân tích nguyên nhân gốc rễ theo đúng nguyên tắc Zero Hallucination."*

2. **Khi mở giao diện `index.html` và demo tính năng Chat / One-Click:**
   > *"Trên giao diện SOC Dashboard (`index.html`), nhóm em thiết kế theo phong cách Glassmorphism hiện đại. Đặc biệt, trợ lý ảo AI DevOps Copilot không chỉ trả lời lý thuyết mà có khả năng thực thi trực tiếp các lệnh chẩn đoán Linux (`df -h`, `top`, `systemctl status`) khi Quản trị viên yêu cầu. Bất cứ khi nào có thao tác khởi động lại dịch vụ từ AI hoặc từ nút One-Click, hệ thống đều tự động gửi một Email thông báo chi tiết kèm Terminal Output về hộp thư quản trị để kiểm toán bảo mật."*

3. **Khi giải thích thư mục `agent/` và cơ chế Systemd:**
   > *"Để đảm bảo tính mở rộng cao (Scalability), tệp `ai_monitor_service.sh` và bộ `ai-monitor@.timer` được thiết kế dưới dạng Systemd Template. Quản trị viên muốn theo dõi thêm bất kỳ dịch vụ nào (như Nginx, MySQL hay Docker) chỉ cần chạy đúng 1 lệnh `sudo systemctl enable --now ai-monitor@<tên-dịch-vụ>.timer` mà không cần sửa dù chỉ 1 dòng code."*
