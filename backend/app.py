import os, smtplib, threading, time
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
RESOURCE_ALERT_COOLDOWN = 300  # 5 phút cooldown giữa các lần cảnh báo

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
            prompt = f"""Bạn là chuyên gia DevOps Senior. Dịch vụ '{service}' trên CentOS 10 vừa bị phát hiện KHÔNG hoạt động.

Log hệ thống (50 dòng cuối):
{logs[:2000]}

Hành động hệ thống đã tự động thực hiện: {action_taken}

Nhiệm vụ:
1. Xác định đây là lỗi hệ thống (Crash/OOM/Segfault/Bị kill) hay do Admin tắt thủ công (systemctl stop)?
   - Nếu thấy "Stopped" / "Stopping" bình thường → Admin tắt thủ công.
   - Nếu thấy "killed" / "segfault" / "error" / "failed" → Lỗi hệ thống.
2. Phân tích nguyên nhân gốc rễ (Root Cause).
3. Đề xuất cách khắc phục cụ thể (với lệnh Linux).
4. Đánh giá mức độ nghiêm trọng: LOW / MEDIUM / HIGH / CRITICAL.

Trả lời ngắn gọn, chuyên nghiệp, bằng tiếng Việt, định dạng Markdown."""

            chat = groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "Bạn là AI chuyên phân tích sự cố hệ thống Linux. Trả lời chuyên nghiệp, ngắn gọn."},
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
Gui boi AI Service Monitor v3.0
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
Gui boi AI Service Monitor v3.0
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
        # Chỉ chuyển healthy nếu đang ở trạng thái recovered hoặc unknown
        if svc["status"] != "crashed":
            svc["status"] = "healthy"

        # ── Kiểm tra ngưỡng tài nguyên ──
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

    # ĐỢI 3 GIÂY cho Dashboard hiển thị CRASHED rồi mới chuyển RECOVERED
    if action == "restarted":
        threading.Thread(
            target=delayed_recover,
            args=(service, 3),
            daemon=True
        ).start()

    # Chạy AI + Email ở thread riêng
    threading.Thread(
        target=analyze_and_notify,
        args=(0, service, logs, action),
        daemon=True
    ).start()

    return jsonify({"ok": True, "msg": "Incident recorded"}), 200


if __name__ == '__main__':
    print("=" * 55)
    print("  🚀 AI SERVICE MONITOR DASHBOARD v3.0")
    print("     + Resource Monitoring (CPU/RAM/Disk)")
    print("=" * 55)
    print(f"  Groq AI : {'✅ Connected' if groq_client else '❌ Not configured'}")
    print(f"  Email   : {'✅ ' + SMTP_EMAIL if SMTP_EMAIL else '❌ Not configured'}")
    print(f"  Password: {'✅ Set (' + SMTP_APP_PASSWORD[:4] + '****)' if SMTP_APP_PASSWORD else '❌ Not set'}")
    print(f"  Thresholds: CPU>{THRESHOLD_CPU}% | RAM>{THRESHOLD_MEM}% | Disk>{THRESHOLD_DISK}%")
    print(f"  URL     : http://0.0.0.0:5000")
    print("=" * 55)
    app.run(host='0.0.0.0', port=5000, debug=False)
