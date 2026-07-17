import os, smtplib, threading, time, subprocess, re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from flask import Flask, request, jsonify, render_template
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)

# ── Cấu hình Groq AI ────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = None
if GROQ_API_KEY and GROQ_API_KEY.startswith("gsk_"):
    groq_client = Groq(api_key=GROQ_API_KEY)

# ── Cấu hình Email ──────────────────────────────────────────────
SMTP_EMAIL        = os.getenv("SMTP_EMAIL")
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD")

# ── Ngưỡng cảnh báo tài nguyên ──────────────────────────────────
THRESHOLD_CPU  = 90   # %
THRESHOLD_MEM  = 85   # %
THRESHOLD_DISK = 90   # %
RESOURCE_ALERT_COOLDOWN = 10   # 10 giây cooldown giữa các lần cảnh báo (mode Demo/Test)

# ── Trạng thái hệ thống ─────────────────────────────────────────
monitored_services = {}
incidents_log = []
resource_metrics = {"cpu": 0, "mem": 0, "disk": 0, "last_update": "N/A"}
last_resource_alert_time = 0  # timestamp lần cảnh báo gần nhất

def get_or_create_service(name):
    if name not in monitored_services:
        monitored_services[name] = {
            "service_name": name,
            "status": "unknown",
            "last_check": "Chưa kiểm tra"
        }
    return monitored_services[name]

# ── Chuyển trạng thái CRASHED → RECOVERED sau delay ─────────────
def delayed_recover(service_name, delay=3):
    """Giữ trạng thái CRASHED trên Dashboard 3 giây rồi mới chuyển RECOVERED."""
    time.sleep(delay)
    if service_name in monitored_services:
        if monitored_services[service_name]["status"] == "crashed":
            monitored_services[service_name]["status"] = "recovered"
            print(f"[{datetime.now()}] ⚡ {service_name} → RECOVERED")

# ── Gửi Email chung ─────────────────────────────────────────────
def send_email(subject, body_text):
    """Gửi email qua Gmail SMTP."""
    if not (SMTP_EMAIL and SMTP_APP_PASSWORD):
        print(f"[{datetime.now()}] ⚠️ Email chưa cấu hình")
        return

    try:
        msg = MIMEMultipart()
        msg['From']    = SMTP_EMAIL
        msg['To']      = SMTP_EMAIL
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))

        srv = smtplib.SMTP('smtp.gmail.com', 587, timeout=15)
        srv.ehlo()
        srv.starttls()
        srv.ehlo()
        srv.login(SMTP_EMAIL, SMTP_APP_PASSWORD)
        srv.sendmail(SMTP_EMAIL, SMTP_EMAIL, msg.as_string())
        srv.quit()
        print(f"[{datetime.now()}] ✅ Email đã gửi thành công!")
    except smtplib.SMTPAuthenticationError as e:
        print(f"[{datetime.now()}] ❌ SAI MẬT KHẨU EMAIL: {e}")
    except smtplib.SMTPException as e:
        print(f"[{datetime.now()}] ❌ Lỗi SMTP: {e}")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Lỗi email khác: {type(e).__name__}: {e}")

# ── Thread: AI phân tích sự cố service + Gửi Email ──────────────
def analyze_and_notify(incident_index, service, logs, action_taken):
    analysis = ""

    # 1. Gọi Groq AI
    if groq_client:
        try:
            prompt = f"""Bạn là Kỹ sư Trưởng DevOps AIOps (Tuân thủ nghiêm ngặt nguyên tắc Zero Hallucination).
Dịch vụ '{service}' trên CentOS 10 vừa bị dừng hoạt động.

Log hệ thống thu thập được (30 dòng cuối):
```text
{logs[:2000]}
```

QUY TẮC BẮT BUỘC TUYỆT ĐỐI (KHÔNG ĐƯỢC SUY DIỄN HAY TỰ TẠO RA LỖI KHÔNG CÓ TRONG LOG):
1. Phân loại sự cố dựa TRỰC TIẾP VÀ CHÍNH XÁC theo từ khóa trong Log:
   - Nếu log có chữ "Stopping", "Stopped", "Deactivated successfully", "shutting down", hoặc log trống/không xuất hiện lỗi nghiêm trọng:
     → KẾT LUẬN NGAY: **Dịch vụ được tắt thủ công hợp lệ bởi Quản trị viên (Graceful Stop qua lệnh `systemctl stop`). KHÔNG phải lỗi hệ thống hay Segfault.** Mức độ: **LOW (Thông tin)**.
   - Nếu log xuất hiện chữ "signal 11", "SIGSEGV", "Segmentation fault":
     → KẾT LUẬN: **Lỗi tràn bộ nhớ / truy cập vùng nhớ cấm (Segfault - Signal 11).** Mức độ: **CRITICAL**.
   - Nếu log xuất hiện chữ "signal 9", "SIGKILL", "OOM", "Out of memory":
     → KẾT LUẬN: **Tiến trình bị tiêu diệt cưỡng chế (OOM Killer hoặc `kill -9`).** Mức độ: **HIGH**.
   - Nếu log có lỗi cú pháp / cấu hình sai ("Syntax error", "Failed to start", v.v.):
     → KẾT LUẬN: **Lỗi cấu hình dịch vụ.** Mức độ: **HIGH**.

2. Trình bày báo cáo ngắn gọn bằng tiếng Việt (Markdown):
   - **Phân loại:** [Tắt thủ công / Crash Segfault / Bị Kill / Lỗi cấu hình]
   - **Nguyên nhân gốc rễ:** [Trích dẫn chính xác từ log theo đúng quy tắc 1. KHÔNG BAO GIỜ tự tạo ra lỗi Segfault nếu log chỉ là Stopping/Stopped]
   - **Hành động tự động:** {action_taken}
   - **Đánh giá & Khuyến nghị:** [Lời khuyên cụ thể và lệnh Linux phù hợp]"""

            chat = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Bạn là AI DevOps chuyên phân tích chính xác tuyệt đối theo log thực tế (Zero Hallucination). Không bao giờ suy diễn hay tự bịa ra lỗi Segfault nếu log chỉ là tắt thủ công (Stopping/Stopped)."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
            )
            analysis = chat.choices[0].message.content
            print(f"[{datetime.now()}] ✅ AI phân tích xong cho {service}")
        except Exception as e:
            analysis = f"## ❌ Lỗi Groq API\n`{str(e)}`"
            print(f"[{datetime.now()}] ❌ Lỗi AI: {e}")
    else:
        analysis = "⚠️ Groq API chưa được cấu hình. Kiểm tra file `.env`."

    # 2. Cập nhật incident
    if incident_index < len(incidents_log):
        incidents_log[incident_index]["ai_analysis"] = analysis
        incidents_log[incident_index]["ai_done"] = True

    # 3. Gửi Email
    subject = f"[AI MONITOR] {service} - Su co & Tu phuc hoi"
    body = f"""CANH BAO TU DONG - AI Service Monitor
{'='*50}
Dich vu: {service}
Thoi diem: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Hanh dong: {action_taken}
{'='*50}

PHAN TICH AI:
{analysis}
{'='*50}
Gui boi AI Service Monitor v4.0
"""
    send_email(subject, body)


# ── Thread: AI phân tích cảnh báo tài nguyên ────────────────────
def analyze_resource_alert(cpu, mem, disk):
    """Gọi AI phân tích khi tài nguyên vượt ngưỡng."""
    global last_resource_alert_time

    alerts = []
    if cpu >= THRESHOLD_CPU:
        alerts.append(f"CPU: {cpu}% (ngưỡng: {THRESHOLD_CPU}%)")
    if mem >= THRESHOLD_MEM:
        alerts.append(f"RAM: {mem}% (ngưỡng: {THRESHOLD_MEM}%)")
    if disk >= THRESHOLD_DISK:
        alerts.append(f"Disk: {disk}% (ngưỡng: {THRESHOLD_DISK}%)")

    alert_summary = ", ".join(alerts)
    print(f"[{datetime.now()}] ⚠️ RESOURCE ALERT: {alert_summary}")

    analysis = ""
    if groq_client:
        try:
            prompt = f"""Bạn là chuyên gia DevOps Senior. Máy chủ CentOS 10 đang có cảnh báo tài nguyên:

Chỉ số hiện tại:
- CPU: {cpu}%
- RAM: {mem}%
- Disk: {disk}%

Các chỉ số vượt ngưỡng: {alert_summary}

Nhiệm vụ:
1. Phân tích nguyên nhân có thể gây ra tình trạng này (ví dụ: tiến trình zombie, memory leak, log file phình to, v.v.).
2. Đưa ra các lệnh Linux cụ thể để điều tra nguyên nhân:
   - Nếu CPU cao: top, ps aux --sort=-%cpu | head
   - Nếu RAM cao: ps aux --sort=-%mem | head, free -m, cat /proc/meminfo
   - Nếu Disk cao: du -sh /var/log/*, df -h, find / -type f -size +100M
3. Đề xuất hành động khắc phục khẩn cấp (xóa log cũ, kill tiến trình zombie, v.v.).
4. Đánh giá mức độ nghiêm trọng: WARNING / HIGH / CRITICAL.
5. Cảnh báo: nếu không xử lý kịp thời, service nào có thể bị ảnh hưởng (OOM-Kill, Disk Full → log không ghi được)?

Trả lời ngắn gọn, chuyên nghiệp, bằng tiếng Việt, định dạng Markdown."""

            chat = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Bạn là AI chuyên giám sát và tối ưu tài nguyên máy chủ Linux. Trả lời chuyên nghiệp, ngắn gọn."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
            )
            analysis = chat.choices[0].message.content
            print(f"[{datetime.now()}] ✅ AI phân tích tài nguyên xong")
        except Exception as e:
            analysis = f"## ❌ Lỗi Groq API\n`{str(e)}`"
            print(f"[{datetime.now()}] ❌ Lỗi AI Resource: {e}")
    else:
        analysis = "⚠️ Groq API chưa được cấu hình."

    # Tạo incident cho resource alert
    incident = {
        "time":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "service":     f"⚙️ Resource Alert ({alert_summary})",
        "action":      "monitoring",
        "ai_analysis": analysis,
        "ai_done":     True
    }
    incidents_log.insert(0, incident)

    # Gửi Email
    subject = f"[AI MONITOR] CANH BAO TAI NGUYEN - {alert_summary}"
    body = f"""CANH BAO TAI NGUYEN - AI Service Monitor
{'='*50}
CPU:  {cpu}%  {'⚠️ VUOT NGUONG!' if cpu >= THRESHOLD_CPU else '✅ OK'}
RAM:  {mem}%  {'⚠️ VUOT NGUONG!' if mem >= THRESHOLD_MEM else '✅ OK'}
Disk: {disk}% {'⚠️ VUOT NGUONG!' if disk >= THRESHOLD_DISK else '✅ OK'}
{'='*50}

PHAN TICH AI:
{analysis}
{'='*50}
Gui boi AI Service Monitor v4.0
"""
    send_email(subject, body)
    last_resource_alert_time = time.time()


# ── API ROUTES ───────────────────────────────────────────────────

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        "services": monitored_services,
        "incidents": incidents_log,
        "resources": resource_metrics,
        "ai_connected": groq_client is not None,
        "email_configured": bool(SMTP_EMAIL and SMTP_APP_PASSWORD)
    })

@app.route('/api/report', methods=['POST'])
def receive_report():
    """Agent gửi báo cáo trạng thái service vào đây."""
    data = request.json
    service = data.get("service", "unknown")
    status  = data.get("status", "unknown")
    logs    = data.get("logs", "")
    action  = data.get("action", "none")
    ts      = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Cập nhật resource metrics
    cpu  = data.get("cpu_pct", 0)
    mem  = data.get("mem_pct", 0)
    disk = data.get("disk_pct", 0)
    resource_metrics["cpu"]  = cpu
    resource_metrics["mem"]  = mem
    resource_metrics["disk"] = disk
    resource_metrics["last_update"] = ts

    svc = get_or_create_service(service)
    svc["last_check"] = ts

    if status == "active":
        if svc["status"] != "crashed":
            svc["status"] = "healthy"

        now = time.time()
        if (cpu >= THRESHOLD_CPU or mem >= THRESHOLD_MEM or disk >= THRESHOLD_DISK):
            if (now - last_resource_alert_time) > RESOURCE_ALERT_COOLDOWN:
                threading.Thread(
                    target=analyze_resource_alert,
                    args=(cpu, mem, disk),
                    daemon=True
                ).start()

        return jsonify({"ok": True}), 200

    # ═══ Service bị DOWN! ═══
    svc["status"] = "crashed"
    print(f"[{ts}] 🚨 CRASH: {service} | Action: {action}")

    incident = {
        "time":        ts,
        "service":     service,
        "action":      action,
        "ai_analysis": "⏳ **AI (Llama 3.1) đang phân tích log...**",
        "ai_done":     False
    }
    incidents_log.insert(0, incident)

    if action == "restarted":
        threading.Thread(
            target=delayed_recover,
            args=(service, 3),
            daemon=True
        ).start()

    threading.Thread(
        target=analyze_and_notify,
        args=(0, service, logs, action),
        daemon=True
    ).start()

    return jsonify({"ok": True, "msg": "Incident recorded"}), 200


# ── v4.0 API: AI DevOps Copilot Chat (Có quyền thực thi bash trên Linux) ──
@app.route('/api/chat', methods=['POST'])
def ai_copilot_chat():
    if not groq_client:
        return jsonify({"reply": "⚠️ Groq AI chưa kết nối. Vui lòng cấu hình `GROQ_API_KEY` trong `.env`."}), 400

    data = request.json
    user_msg = data.get("message", "").strip()
    if not user_msg:
        return jsonify({"reply": "Vui lòng nhập câu hỏi."}), 400

    try:
        system_prompt = """Bạn là AI DevOps Assistant chạy trực tiếp trên máy chủ CentOS 10 của hệ thống AI Service Monitor v4.0.
Bạn có khả năng tương tác với máy chủ Linux và hỗ trợ quản trị viên 24/7.

QUY TẮC QUAN TRỌNG VỀ THỰC THI LỆNH LINUX:
- Nếu yêu cầu của Admin cần kiểm tra số liệu thực tế trên máy chủ, tìm file chiếm ổ cứng, kiểm tra tiến trình, tạo file giả lập (fallocate), xóa file dọn ổ đĩa, kiểm tra dịch vụ hay chạy bất kỳ lệnh bash nào để xử lý, BẠN PHẢI TRẢ VỀ ĐÚNG MỘT DÒNG DUY NHẤT THEO CÚ PHÁP SAU:
[[RUN_COMMAND: <lệnh bash>]]

Ví dụ các trường hợp:
- Admin: "Kiểm tra ổ cứng và tìm 5 thư mục chiếm nhiều chỗ nhất"
  → Bạn trả lời chính xác: [[RUN_COMMAND: df -h / && echo "--- TOP FOLDERS ---" && du -sh /var/* /tmp/* /usr/* 2>/dev/null | sort -rh | head -5]]
- Admin: "Tạo giúp tôi file giả lập 2GB ở /tmp/test.img để kiểm tra cảnh báo ổ cứng"
  → Bạn trả lời chính xác: [[RUN_COMMAND: fallocate -l 2G /tmp/test.img && echo "Đã tạo file /tmp/test.img 2GB:" && ls -lh /tmp/test.img]]
- Admin: "Xóa file /tmp/test.img giúp tôi để giải phóng ổ đĩa"
  → Bạn trả lời chính xác: [[RUN_COMMAND: rm -f /tmp/test.img && echo "Đã xóa thành công file /tmp/test.img. Dung lượng hiện tại:" && df -h /]]
- Admin: "Kiểm tra top 5 tiến trình đang ăn RAM nhất"
  → Bạn trả lời chính xác: [[RUN_COMMAND: ps aux --sort=-%mem | head -6]]
- Admin: "Khởi động lại dịch vụ apache"
  → Bạn trả lời chính xác: [[RUN_COMMAND: systemctl restart httpd && systemctl status httpd --no-pager]]

Nếu yêu cầu chỉ là hỏi đáp kiến thức lý thuyết hay giải thích khái niệm không cần chạy bash, hãy trả lời bằng tiếng Việt chuyên nghiệp dạng Markdown, đầy đủ và thân thiện."""

        chat = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg}
            ],
            model="llama-3.1-8b-instant",
        )
        first_reply = chat.choices[0].message.content.strip()

        # Kiểm tra xem AI có muốn chạy lệnh không
        match = re.search(r'\[\[RUN_COMMAND:\s*(.+?)\]\]', first_reply, re.DOTALL)
        if match:
            cmd_to_run = match.group(1).strip()
            print(f"[{datetime.now()}] 🤖 AI Copilot thực thi bash: {cmd_to_run}")
            try:
                # Thực thi bash trên CentOS
                result = subprocess.run(cmd_to_run, shell=True, capture_output=True, text=True, timeout=15)
                terminal_output = (result.stdout + "\n" + result.stderr).strip()
                if not terminal_output:
                    terminal_output = "Lệnh đã thực thi thành công (không có output trả về)."
            except Exception as e:
                terminal_output = f"Lỗi khi thực thi lệnh: {e}"

            # Gọi lại AI để giải thích kết quả terminal cho Admin
            second_prompt = f"""Admin đã hỏi: "{user_msg}"
Bạn đã ra lệnh bash: `{cmd_to_run}`
Kết quả từ máy chủ CentOS 10:
```text
{terminal_output[:3500]}
```

Hãy báo cáo và giải thích rõ ràng kết quả trên cho Admin bằng tiếng Việt định dạng Markdown. Nếu là chẩn đoán dung lượng/tài nguyên, hãy chỉ rõ số liệu và đưa lời khuyên hữu ích."""

            chat2 = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Bạn là chuyên gia DevOps tóm tắt kết quả terminal một cách chuyên nghiệp, dễ hiểu."},
                    {"role": "user", "content": second_prompt}
                ],
                model="llama-3.1-8b-instant",
            )
            final_reply = chat2.choices[0].message.content
            return jsonify({
                "reply": final_reply,
                "executed_command": cmd_to_run,
                "terminal_output": terminal_output
            })

        return jsonify({"reply": first_reply})

    except Exception as e:
        return jsonify({"reply": f"❌ Lỗi xử lý AI Copilot: {e}"}), 500


# ── v4.0 API: Thực thi lệnh chẩn đoán nhanh (One-Click Terminal Modal) ──
@app.route('/api/execute_fix', methods=['POST'])
def execute_fix():
    data = request.json
    cmd = data.get("command", "").strip()
    if not cmd:
        return jsonify({"output": "Lệnh trống.", "status": "error"}), 400

    print(f"[{datetime.now()}] ⚡ One-Click Execute: {cmd}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        out = (result.stdout + "\n" + result.stderr).strip()
        if not out:
            out = "Lệnh đã thực thi hoàn tất (Thành công - return code 0)."
        return jsonify({"output": out, "status": "success" if result.returncode == 0 else "error"})
    except Exception as e:
        return jsonify({"output": f"Lỗi thực thi: {e}", "status": "error"}), 500


# ── Thread Tự Động Giám Sát (Auto-Tracking Daemon) ──────────────────────────
DEFAULT_MONITOR_SERVICES = ["httpd", "sshd", "crond"]

def auto_tracker_loop():
    """Tự động theo dõi tài nguyên & dịch vụ trực tiếp trong Python mỗi 3 giây (đảm bảo 100% không bao giờ bị kẹt WAITING)."""
    # 0. Khởi tạo ngay trạng thái ban đầu
    for svc in DEFAULT_MONITOR_SERVICES:
        get_or_create_service(svc)
    
    while True:
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. Cập nhật số liệu tài nguyên trực tiếp (Từng khối try riêng biệt để tuyệt đối không bị block nhau)
        cpu_val = resource_metrics.get("cpu", 0)
        mem_val = resource_metrics.get("mem", 0)
        disk_val = resource_metrics.get("disk", 0)
        
        try:
            top_out = subprocess.check_output("top -bn1 2>/dev/null | grep -i 'Cpu(s)'", shell=True, text=True, timeout=3)
            nums = re.findall(r'([0-9.]+)', top_out)
            if len(nums) >= 2:
                cpu_val = int(float(nums[0]) + float(nums[1]))
        except Exception:
            pass
        
        try:
            free_out = subprocess.check_output("free 2>/dev/null | grep -i 'Mem:'", shell=True, text=True, timeout=3)
            parts = free_out.split()
            if len(parts) >= 3:
                mem_val = int(float(parts[2]) / float(parts[1]) * 100)
        except Exception:
            pass
        
        try:
            df_out = subprocess.check_output("df / 2>/dev/null | awk 'NR==2 {print $5}'", shell=True, text=True, timeout=3)
            clean_str = re.sub(r'[^0-9]', '', df_out.strip() if df_out else '0')
            if clean_str:
                disk_val = int(clean_str)
        except Exception:
            pass
        
        resource_metrics["cpu"] = cpu_val
        resource_metrics["mem"] = mem_val
        resource_metrics["disk"] = disk_val
        resource_metrics["last_update"] = now_ts
        
        # 2. Cập nhật trạng thái từng service trực tiếp (Khối try riêng cho mỗi service)
        for svc_name in DEFAULT_MONITOR_SERVICES:
            try:
                svc = get_or_create_service(svc_name)
                res = subprocess.run(["systemctl", "is-active", "--quiet", svc_name], timeout=3)
                if res.returncode == 0:
                    svc["status"] = "healthy"
                else:
                    # Nếu phát hiện down mà trước đó chưa crashed -> ghi nhận crash & tự phục hồi
                    if svc["status"] != "crashed":
                        svc["status"] = "crashed"
                        print(f"[{now_ts}] 🚨 Auto-Tracker phát hiện CRASH: {svc_name}")
                        def handle_crash(s_name):
                            try:
                                logs_out = subprocess.check_output(f"journalctl -u {s_name} -n 30 --no-pager 2>/dev/null", shell=True, text=True, timeout=5)
                            except:
                                logs_out = "Không có log"
                            subprocess.run(["systemctl", "restart", s_name], timeout=5)
                            time.sleep(1)
                            is_up = (subprocess.run(["systemctl", "is-active", "--quiet", s_name]).returncode == 0)
                            action = "restarted" if is_up else "restart_failed"
                            incident = {
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "service": s_name,
                                "action": action,
                                "ai_analysis": "⏳ **AI (Llama 3.1) đang phân tích log...**",
                                "ai_done": False
                            }
                            incidents_log.insert(0, incident)
                            if is_up:
                                delayed_recover(s_name, 3)
                            analyze_and_notify(0, s_name, logs_out, action)
                        threading.Thread(target=handle_crash, args=(svc_name,), daemon=True).start()
                svc["last_check"] = now_ts
            except Exception:
                pass
        
        # 3. Kiểm tra cảnh báo tài nguyên vượt ngưỡng
        try:
            now = time.time()
            if (cpu_val >= THRESHOLD_CPU or mem_val >= THRESHOLD_MEM or disk_val >= THRESHOLD_DISK):
                if (now - last_resource_alert_time) > RESOURCE_ALERT_COOLDOWN:
                    threading.Thread(
                        target=analyze_resource_alert,
                        args=(cpu_val, mem_val, disk_val),
                        daemon=True
                    ).start()
        except Exception:
            pass
        
        time.sleep(3)

# Khởi động ngay luồng theo dõi tự động ngầm bên dưới
auto_thread = threading.Thread(target=auto_tracker_loop, daemon=True)
auto_thread.start()


if __name__ == '__main__':
    print("=" * 60)
    print("  🚀 AI SERVICE MONITOR DASHBOARD v4.0 (Enterprise SOC)")
    print("     + Resource Monitoring (CPU/RAM/Disk)")
    print("     + AI DevOps Copilot Chat 24/7 (Server Execution)")
    print("     + One-Click Remediation & Terminal Modal")
    print("=" * 60)
    print(f"  Groq AI : {'✅ Connected' if groq_client else '❌ Not configured'}")
    print(f"  Email   : {'✅ ' + SMTP_EMAIL if SMTP_EMAIL else '❌ Not configured'}")
    print(f"  Password: {'✅ Set (' + SMTP_APP_PASSWORD[:4] + '****)' if SMTP_APP_PASSWORD else '❌ Not set'}")
    print(f"  Thresholds: CPU>{THRESHOLD_CPU}% | RAM>{THRESHOLD_MEM}% | Disk>{THRESHOLD_DISK}%")
    print(f"  URL     : http://0.0.0.0:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=False)
