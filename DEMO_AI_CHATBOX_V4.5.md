# 🤖 KỊCH BẢN DEMO AI DEVOPS ASSISTANT (24/7 AIOps COPILOT v4.5)

Tài liệu này hướng dẫn chi tiết kịch bản trình diễn (Demo) tính năng **AI DevOps Copilot Chatbox 24/7** được tích hợp sâu vào hệ điều hành Linux CentOS 10 trước Thầy Cô / Hội đồng bảo vệ đồ án.

---

## 🎙️ Lời Dẫn Mở Đầu (Giới thiệu trước Hội đồng)
> *"Kính thưa Thầy Cô, một điểm khác biệt và đột phá nhất của đồ án **AI Service Monitor v4.5** so với các hệ thống giám sát truyền thống chính là **AI DevOps Copilot Chatbox 24/7**.*
>
> *Khác với các Chatbot AI thông thường chỉ trả lời lý thuyết chung chung trên Web, AI của em (**Groq Llama 3.1**) được kết nối trực tiếp với nhân Linux (Kernel) và có quyền thực thi lệnh bash an toàn theo thời gian thực. Nó đóng vai trò như một Kỹ sư System Admin lão luyện ngồi trực trực tiếp trong Server, sẵn sàng nhận lệnh bằng tiếng Việt tự nhiên và tự động hóa toàn bộ quy trình xử lý sự cố!"*

---

## 🧹 Bước 0: Chuẩn Bị & Làm Sạch Môi Trường (Clean Setup từ con số 0)
Trước khi bắt đầu buổi trình diễn, chạy cụm lệnh dưới đây với quyền `root` (hoặc `sudo`) để xóa trắng các cài đặt/tiến trình cũ, bảo toàn API Key và khởi động lại môi trường sạch:

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

## 🌟 Kịch bản 1: Hỏi đáp nhanh & Phân tích tài nguyên thực tế (30 giây)
- **Thao tác trên Web Dashboard:** Bấm vào icon robot `🤖` ở góc phải dưới màn hình để mở hộp thoại AI.
- **Gõ câu lệnh (hoặc bấm nút gợi ý `🧠 Top RAM`):**
  ```text
  Kiểm tra giúp tôi 5 tiến trình đang tiêu tốn RAM nhất trên server lúc này và giải thích chi tiết
  ```
- **Hiệu ứng trình diễn:**
  1. AI hiển thị trạng thái suy nghĩ: `⏳ AI đang suy nghĩ & thao tác trên máy chủ...`
  2. Chỉ **1 - 1.5 giây sau**, AI tự động chuyển hóa câu lệnh tiếng Việt thành lệnh Linux (`ps aux --sort=-%mem | head -6`) và thực thi ngầm trên CentOS 10.
  3. **Kết quả trả về trên khung Chat:** AI hiển thị khối mã `🛠️ Đã thực thi bash trên CentOS:` kèm bảng danh sách tiến trình RAM thực tế của máy chủ, sau đó tóm tắt và phân tích bằng tiếng Việt cực kỳ súc tích, chuyên nghiệp!

---

## 🛡️ Kịch bản 2: Khảo sát An ninh & Truy vết Log SOC (1 phút - Siêu ngầu)
- **Lời dẫn:** *"Tiếp theo, em xin trình diễn khả năng kiểm tra an ninh và truy vết log hệ thống (SOC Auditing) bằng ngôn ngữ tự nhiên."*
- **Gõ vào khung Chat AI:**
  ```text
  Kiểm tra xem hiện tại có ai đang đăng nhập vào server (w) và kiểm tra 5 dòng log sshd gần nhất xem có lỗi gì không?
  ```
- **Hiệu ứng trình diễn:**
  1. AI tự động gõ lệnh Linux tổng hợp: `w && journalctl -u sshd -n 5 --no-pager`
  2. AI trả về danh sách user đang online (ví dụ: `root logged in via SSH`) và dịch log `sshd` ra tiếng Việt cho quản trị viên:
     > *"Hiện tại có 1 phiên đăng nhập SSH hoạt động bình thường từ địa chỉ IP hợp lệ. Không phát hiện dấu hiệu tấn công Brute-force hay đăng nhập sai mật khẩu trong 5 dòng log gần nhất."*

---

## ⚡ Kịch bản 3: Ra lệnh cho AI tự động khởi động lại dịch vụ & khắc phục sự cố (1 phút)
- **Lời dẫn:** *"Cuối cùng, thay vì quản trị viên phải nhớ và gõ từng lệnh systemctl phức tạp, chúng ta có thể ra lệnh bằng tiếng Việt tự nhiên để AI tự động bảo trì dịch vụ."*
- **Thao tác:** Bạn có thể bấm ngay vào nút **`⚡ Khởi động lại CROND`** trong thanh gợi ý nhanh trên Chatbox hoặc gõ câu lệnh sau:
  ```text
  Hãy khởi động lại dịch vụ crond và kiểm tra trạng thái mới nhất giúp tôi
  ```
- **Hiệu ứng trình diễn:**
  1. AI tự động phân tích và gõ chuỗi lệnh bảo trì Linux: `systemctl restart crond && systemctl status crond --no-pager`
  2. Trả lời ngay lập tức:
     > `🛠️ Đã thực thi bash trên CentOS: systemctl restart crond && systemctl status crond --no-pager`
     > **Dịch vụ `crond` đã được khởi động lại thành công (`active running`) vào lúc [Thời gian thực].**
  3. **Điểm ăn tiền:** Nhìn sang bảng **⚙️ Core Daemons** trên Web Dashboard, Thầy Cô sẽ thấy dịch vụ `crond` chuyển sang màu xanh **`✅ HEALTHY`** kèm thời gian kiểm tra `Last check` vừa nhảy số mới nhất tức thì!

---

## 🎯 Lời Chốt Kết Thúc Demo AI Chatbox
> *"Nhờ sự tích hợp sâu của Llama 3.1 vào Linux Terminal, toàn bộ chu trình giám sát SOC — từ theo dõi tài nguyên, chẩn đoán nguyên nhân đến khắc phục lỗi tự động — đều được vận hành khép kín và có thể điều khiển bằng ngôn ngữ tự nhiên, giúp giảm 95% thao tác thủ công và ngăn chặn hoàn toàn lỗi sai con người (human error) ạ!"*
