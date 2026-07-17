# Hướng Dẫn Triển Khai AI Service Monitor trên CentOS 10

Dự án này sử dụng Python (Flask) cho Backend/Dashboard và Bash Script + systemd cho Agent giám sát.

## 1. Chuẩn Bị (Yêu cầu Root)

Đăng nhập vào máy CentOS 10 của bạn bằng quyền root, cài đặt các công cụ cần thiết:

```bash
sudo dnf install -y python3 python3-pip jq git nano
```

### ⚠️ Lệnh Dọn Dẹp / Reset Sạch (Khôi phục 0% để Demo cài đặt từ bước Setting Key)
Nếu bạn muốn **xóa trắng hoàn toàn hệ thống, kill tiến trình cũ và xóa cả cấu hình cũ** để trình diễn thực hành cài đặt từ con số 0 (bắt đầu từ bước copy code và bước tạo `.env`), hãy chạy cụm lệnh sau trước:
```bash
# 1. Dừng và xóa toàn bộ timer/service giám sát cũ
sudo systemctl stop ai-monitor@*.timer ai-monitor@*.service 2>/dev/null
sudo systemctl disable ai-monitor@*.timer 2>/dev/null
sudo rm -f /etc/systemd/system/ai-monitor@.*
sudo systemctl daemon-reload

# 2. Tiêu diệt triệt để tiến trình Backend cũ và giải phóng Port 5000
PID=$(sudo ss -lptn 'sport = :5000' 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1)
[ -n "$PID" ] && sudo kill -9 "$PID" 2>/dev/null
sudo fuser -k 5000/tcp 2>/dev/null
sudo pkill -9 -f app.py 2>/dev/null
sudo pkill -9 -f stress 2>/dev/null
sleep 1

# 3. Thoát ra thư mục gốc và xóa trắng toàn bộ thư mục dự án cũ (KHÔNG GIỮ LẠI .env cũ)
cd / && sudo rm -rf /opt/ai-service-monitor /tmp/backend_env.bak
```

---

## 2. Copy Mã Nguồn

Tải mã nguồn từ GitHub hoặc copy vào `/opt/ai-service-monitor` và phân quyền:

```bash
sudo git clone https://github.com/KH4NHTU0NG/OSG_PROJECT.git /opt/ai-service-monitor
sudo chown -R $USER:$USER /opt/ai-service-monitor
chmod +x /opt/ai-service-monitor/agent/ai_monitor_service.sh
```

## 3. Cấu Hình & Chạy Backend (Dashboard)

1. Đi tới thư mục backend:
   ```bash
   cd /opt/ai-service-monitor/backend
   ```
2. Cài đặt thư viện Python:
   ```bash
   sudo pip3 install --break-system-packages -r requirements.txt
   ```
3. Cấu hình biến môi trường:
   ```bash
   cp .env.example .env
   nano .env
   ```
   - Sửa `GROQ_API_KEY=` thành API Key thực tế của bạn (bắt đầu bằng `gsk_`).
   - Sửa `SMTP_EMAIL=` và `SMTP_APP_PASSWORD=` nếu muốn nhận email cảnh báo.
4. Mở Port tường lửa (nếu có dùng firewalld):
   ```bash
   sudo firewall-cmd --add-port=5000/tcp --permanent
   sudo firewall-cmd --reload
   ```
5. Chạy Backend (quyền sudo -E để AI có quyền restart dịch vụ):
   ```bash
   sudo -E nohup python3 app.py > backend.log 2>&1 &
   sleep 2 && sudo tail -n 15 backend.log
   ```

## 4. Cấu Hình Agent (Giám Sát)

1. Copy file systemd template vào hệ thống:
   ```bash
   sudo cp /opt/ai-service-monitor/agent/ai-monitor@.service /etc/systemd/system/
   sudo cp /opt/ai-service-monitor/agent/ai-monitor@.timer /etc/systemd/system/
   ```
2. Reload systemd daemon:
   ```bash
   sudo systemctl daemon-reload
   ```
3. Bật giám sát cho một dịch vụ cụ thể (Ví dụ: `httpd`):
   ```bash
   sudo systemctl enable --now ai-monitor@httpd.timer
   ```

## 5. Kịch Bản Demo (Action!)

### Bước 0: Dọn Dẹp / Reset Sạch Thư Mục Cũ (Clean Setup từ đầu)
Nếu bạn muốn làm lại demo từ đầu hoặc xóa sạch cài đặt cũ trên máy chủ CentOS, chạy cụm lệnh sau với quyền root (hoặc `sudo`):
```bash
# 1. Dừng & xóa toàn bộ systemd timer/service giám sát cũ
sudo systemctl stop ai-monitor@*.timer ai-monitor@*.service 2>/dev/null
sudo systemctl disable ai-monitor@*.timer 2>/dev/null
sudo rm -f /etc/systemd/system/ai-monitor@.*
sudo systemctl daemon-reload

# 2. Tiêu diệt triệt để tiến trình đang chiếm giữ Port 5000 và stress test
PID=$(sudo ss -lptn 'sport = :5000' 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | head -1)
[ -n "$PID" ] && sudo kill -9 "$PID" 2>/dev/null
sudo fuser -k 5000/tcp 2>/dev/null
sudo pkill -9 -f app.py 2>/dev/null
sudo pkill -9 -f stress 2>/dev/null
sleep 1

# 3. Sao lưu cấu hình .env (bảo toàn API Key), thoát ra thư mục gốc, xóa thư mục cũ và clone mới từ GitHub
sudo cp /opt/ai-service-monitor/backend/.env /tmp/backend_env.bak 2>/dev/null
cd / && sudo rm -rf /opt/ai-service-monitor
sudo git clone https://github.com/KH4NHTU0NG/OSG_PROJECT.git /opt/ai-service-monitor
sudo chown -R $USER:$USER /opt/ai-service-monitor

# 4. Phục hồi cấu hình .env, cài đặt systemd template, cấp quyền và chạy Backend
cp /tmp/backend_env.bak /opt/ai-service-monitor/backend/.env 2>/dev/null || cp /opt/ai-service-monitor/backend/.env.example /opt/ai-service-monitor/backend/.env
sudo cp /opt/ai-service-monitor/agent/ai-monitor@.service /etc/systemd/system/
sudo cp /opt/ai-service-monitor/agent/ai-monitor@.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo chmod +x /opt/ai-service-monitor/agent/ai_monitor_service.sh
cd /opt/ai-service-monitor/backend && sudo -E nohup python3 app.py > backend.log 2>&1 &
```

---

1. **Mở Trình Duyệt:** Truy cập `http://<IP_CENTOS_CỦA_BẠN>:5000`
   Bạn sẽ thấy Dashboard hiện "HEALTHY".
2. **Crash Dịch Vụ:** Trên terminal CentOS, gõ:
   ```bash
   sudo systemctl stop httpd
   # hoặc
   sudo kill -9 $(pgrep -o httpd)
   ```
3. **Xem Wow-Effect:**
   - Ngay lập tức Dashboard báo "CRASHED" (nháy đỏ).
   - Bash script tự khởi động lại `httpd` và gửi log cho Groq API (Llama 3.1).
   - Vài giây sau, Dashboard chuyển sang "RECOVERED" / "HEALTHY", đồng thời hiển thị Báo cáo chi tiết nguyên nhân từ AI và gửi Email cảnh báo.
