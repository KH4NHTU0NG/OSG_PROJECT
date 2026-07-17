#!/bin/bash

# =================================================================
# AI SERVICE MONITOR AGENT v3.0 (Resource Monitoring)
# =================================================================

DASHBOARD_URL="http://localhost:5000/api/report"

if [ $# -eq 0 ]; then
    echo "Cách dùng: $0 <service1> [service2] ..."
    exit 1
fi

# ── Thu thập tài nguyên hệ thống (An toàn chống rỗng) ────────────
CPU_PCT=$(top -bn1 2>/dev/null | grep -i "Cpu(s)" | awk '{print int($2 + $4)}' 2>/dev/null | head -n 1)
MEM_PCT=$(free 2>/dev/null | awk '/Mem:/ {printf "%d", $3/$2*100}' 2>/dev/null | head -n 1)
DISK_PCT=$(df / 2>/dev/null | awk 'NR==2 {print int($5)}' 2>/dev/null | head -n 1)

CPU_PCT=${CPU_PCT:-0}
MEM_PCT=${MEM_PCT:-0}
DISK_PCT=${DISK_PCT:-0}

for SERVICE in "$@"; do
    if systemctl is-active --quiet "$SERVICE"; then
        # ✅ Service đang chạy → gửi trạng thái active + resource metrics
        python3 -c "
import json, urllib.request, sys
def s_int(v):
    try: return int(float(v))
    except: return 0
payload = json.dumps({
    'service': sys.argv[1],
    'status': 'active',
    'logs': '',
    'action': 'none',
    'cpu_pct': s_int(sys.argv[2]),
    'mem_pct': s_int(sys.argv[3]),
    'disk_pct': s_int(sys.argv[4])
}).encode('utf-8')
req = urllib.request.Request(
    sys.argv[5],
    data=payload,
    headers={'Content-Type': 'application/json'}
)
try: urllib.request.urlopen(req, timeout=5)
except Exception: pass
" "$SERVICE" "$CPU_PCT" "$MEM_PCT" "$DISK_PCT" "$DASHBOARD_URL"

    else
        # 🚨 Service bị DOWN → lấy log, restart, gửi báo cáo
        LOGS=$(journalctl -u "$SERVICE" -n 50 --no-pager 2>/dev/null || echo "Không có log")
        systemctl restart "$SERVICE" 2>/dev/null
        sleep 1

        if systemctl is-active --quiet "$SERVICE"; then ACTION="restarted"
        else ACTION="restart_failed"; fi

        echo "$LOGS" | python3 -c "
import sys, json, urllib.request
def s_int(v):
    try: return int(float(v))
    except: return 0
logs = sys.stdin.read()
payload = json.dumps({
    'service': sys.argv[1],
    'status': 'inactive',
    'logs': logs,
    'action': sys.argv[2],
    'cpu_pct': s_int(sys.argv[4]),
    'mem_pct': s_int(sys.argv[5]),
    'disk_pct': s_int(sys.argv[6])
}).encode('utf-8')
req = urllib.request.Request(
    sys.argv[3],
    data=payload,
    headers={'Content-Type': 'application/json'}
)
try: urllib.request.urlopen(req, timeout=5)
except Exception as e: print(f'Lỗi gửi report: {e}')
" "$SERVICE" "$ACTION" "$DASHBOARD_URL" "$CPU_PCT" "$MEM_PCT" "$DISK_PCT"

    fi
done
