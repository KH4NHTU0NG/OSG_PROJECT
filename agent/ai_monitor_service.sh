#!/bin/bash

# =================================================================
# AI SERVICE MONITOR AGENT v3.1 (POSIX Compliant & Robust Telemetry)
# =================================================================

DASHBOARD_URL="http://localhost:5000/api/report"

if [ $# -eq 0 ]; then
    echo "Cách dùng: $0 <service1> [service2] ..."
    exit 1
fi

# ── Thu thập tài nguyên hệ thống (Tuân thủ POSIX & LC_ALL=C chống lỗi locale/0-division) ──
CPU_PCT=$(LC_ALL=C top -bn1 2>/dev/null | grep -i "Cpu(s)" | awk '{for(i=1;i<=NF;i++) if($i~/id/ || $(i+1)~/id/) {print int(100 - $(i-1)); break}}' 2>/dev/null | head -n 1)
MEM_PCT=$(LC_ALL=C free 2>/dev/null | awk '/Mem:/ {if ($2 > 0) printf "%d", $3/$2*100; else print 0}' 2>/dev/null | head -n 1)
DISK_PCT=$(LC_ALL=C df -P / 2>/dev/null | awk 'NR==2 {print int($5)}' 2>/dev/null | head -n 1)

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
try:
    urllib.request.urlopen(req, timeout=5)
except Exception as e:
    print(f'Failed to send active report for {sys.argv[1]}: {e}', file=sys.stderr)
    sys.exit(1)
" "$SERVICE" "$CPU_PCT" "$MEM_PCT" "$DISK_PCT" "$DASHBOARD_URL"

    else
        # 🚨 Service bị DOWN → lấy log, restart, gửi báo cáo
        LOGS=$(journalctl -u "$SERVICE" -n 50 --no-pager 2>/dev/null || echo "Không có log")
        if systemctl restart "$SERVICE" 2>/dev/null; then
            # Poll up to 5 seconds to verify stable active status
            for i in {1..5}; do
                sleep 1
                if systemctl is-active --quiet "$SERVICE"; then
                    ACTION="restarted"
                    break
                else
                    ACTION="restart_failed"
                fi
            done
        else
            ACTION="restart_failed"
        fi

        echo "$LOGS" | python3 -c "
import sys, json, urllib.request
def s_int(v):
    try: return int(float(v))
    except: return 0
logs = sys.stdin.buffer.read().decode('utf-8', errors='replace')
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
try:
    urllib.request.urlopen(req, timeout=5)
except Exception as e:
    print(f'Lỗi gửi report cho {sys.argv[1]}: {e}', file=sys.stderr)
    sys.exit(1)
" "$SERVICE" "$ACTION" "$DASHBOARD_URL" "$CPU_PCT" "$MEM_PCT" "$DISK_PCT"

    fi
done
