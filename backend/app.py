import os, smtplib, threading
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

# ── Trạng thái hệ thống (hỗ trợ NHIỀU service) ─────────────────
monitored_services = {}
incidents_log = []

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
    import time
    time.sleep(delay)
    if service_name in monitored_services:
        if monitored_services[service_name]["status"] == "crashed":
            monitored_services[service_name]["status"] = "recovered"
            print(f"[{datetime.now()}] ⚡ {service_name} → RECOVERED")

# ── Thread: AI phân tích + Gửi Email ────────────────────────────
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
    print(f"[{datetime.now()}] 📧 Chuẩn bị gửi email...")
    print(f"    SMTP_EMAIL = '{SMTP_EMAIL}'")
    print(f"    SMTP_APP_PASSWORD = '{SMTP_APP_PASSWORD[:4]}****' (ẩn)")

    if SMTP_EMAIL and SMTP_APP_PASSWORD:
        try:
            msg = MIMEMultipart()
            msg['From']    = SMTP_EMAIL
            msg['To']      = SMTP_EMAIL
            msg['Subject'] = f"[AI MONITOR] {service} - Su co & Tu phuc hoi"

            body = f"""CANH BAO TU DONG - AI Service Monitor
{'='*50}
Dich vu: {service}
Thoi diem: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Hanh dong: {action_taken}
{'='*50}

PHAN TICH AI:
{analysis}
{'='*50}
Gui boi AI Service Monitor v2.0
"""
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

            print(f"[{datetime.now()}] 📧 Đang kết nối SMTP Gmail...")
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
    else:
        print(f"[{datetime.now()}] ⚠️ Email chưa cấu hình (SMTP_EMAIL hoặc SMTP_APP_PASSWORD trống)")


# ── API ROUTES ───────────────────────────────────────────────────

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        "services": monitored_services,
        "incidents": incidents_log,
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

    svc = get_or_create_service(service)
    svc["last_check"] = ts

    if status == "active":
        # Chỉ chuyển healthy nếu đang ở trạng thái recovered hoặc unknown
        if svc["status"] != "crashed":
            svc["status"] = "healthy"
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
    print("  🚀 AI SERVICE MONITOR DASHBOARD v2.0")
    print("=" * 55)
    print(f"  Groq AI : {'✅ Connected' if groq_client else '❌ Not configured'}")
    print(f"  Email   : {'✅ ' + SMTP_EMAIL if SMTP_EMAIL else '❌ Not configured'}")
    print(f"  Password: {'✅ Set (' + SMTP_APP_PASSWORD[:4] + '****)' if SMTP_APP_PASSWORD else '❌ Not set'}")
    print(f"  URL     : http://0.0.0.0:5000")
    print("=" * 55)
    app.run(host='0.0.0.0', port=5000, debug=False)
