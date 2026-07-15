#!/bin/bash

# =================================================================
# AI SERVICE MONITOR AGENT v2.0 (Fixed)
# =================================================================

DASHBOARD_URL="http://localhost:5000/api/report"

if [ $# -eq 0 ]; then
    echo "Cách dùng: $0 <service1> [service2] ..."
    exit 1
fi

for SERVICE in "$@"; do
    if systemctl is-active --quiet "$SERVICE"; then
        # ✅ Service đang chạy → gửi trạng thái healthy
        curl -s -X POST "$DASHBOARD_URL" \
            -H "Content-Type: application/json" \
            -d "{\"service\":\"$SERVICE\",\"status\":\"active\",\"logs\":\"\",\"action\":\"none\"}" > /dev/null 2>&1

    else
        # 🚨 Service bị DOWN → lấy log, restart, gửi báo cáo
        LOGS=$(journalctl -u "$SERVICE" -n 50 --no-pager 2>/dev/null || echo "Không có log")

        # Restart service
        systemctl restart "$SERVICE" 2>/dev/null
        sleep 1

        if systemctl is-active --quiet "$SERVICE"; then
            ACTION="restarted"
        else
            ACTION="restart_failed"
        fi

        # Gửi báo cáo crash — dùng python3 để escape JSON an toàn 100%
        echo "$LOGS" | python3 -c "
import sys, json, urllib.request
logs = sys.stdin.read()
payload = json.dumps({
    'service': sys.argv[1],
    'status': 'inactive',
    'logs': logs,
    'action': sys.argv[2]
}).encode('utf-8')
req = urllib.request.Request(
    sys.argv[3],
    data=payload,
    headers={'Content-Type': 'application/json'}
)
try:
    urllib.request.urlopen(req, timeout=5)
except Exception as e:
    print(f'Lỗi gửi report: {e}')
" "$SERVICE" "$ACTION" "$DASHBOARD_URL"

    fi
done
