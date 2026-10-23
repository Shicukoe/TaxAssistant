#!/usr/bin/env bash
# Web app cho mẹ thử trong Wi-Fi nhà: Hỏi + Tra cứu (docs/ui-context.md).
#
#   bash scripts/run_model_server.sh     (cửa sổ 1 — model)
#   bash scripts/run_web_demo.sh         (cửa sổ 2 — web, cổng 8000)
#
# Máy khác trong cùng Wi-Fi mở http://<IP laptop>:8000 (script in IP ra). Lần đầu phải mở tường lửa Windows
# cho cổng 8000, chỉ với mạng Private — chạy MỘT lần trong PowerShell quyền Administrator:
#   New-NetFirewallRule -DisplayName "TaxAssistant web" -Direction Inbound -Protocol TCP -LocalPort 8000 -Profile Private -Action Allow
# Wi-Fi nhà phải đặt là Private (Settings → Network → Wi-Fi → Network profile type).
# Khung debug từng bước chỉ hiện khi mở trên chính laptop (http://127.0.0.1:8000).
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
cd "$project_root"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# Windows không bật symlink → cache HuggingFace vẫn chạy, chỉ tốn chỗ hơn; tắt cảnh báo lặp lại mỗi lần chạy.
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

if [ -x .venv/bin/python ]; then python=.venv/bin/python; else python=.venv/Scripts/python.exe; fi

if ! curl -s --max-time 3 http://127.0.0.1:9931/health | grep -q '"ok"'; then
    echo "Cảnh báo: llama-server chưa chạy — trang Tra cứu vẫn dùng được, Hỏi sẽ báo lỗi." >&2
    echo "Mở cửa sổ khác: bash scripts/run_model_server.sh" >&2
fi

echo "Mở trên laptop:  http://127.0.0.1:8000"
# IPv4 của máy trong mạng nhà (ipconfig trên Windows, hostname -I trên Linux)
if command -v ipconfig >/dev/null 2>&1; then
    ipconfig | grep -a "IPv4" | sed 's/.*: //' | tr -d '\r' | while read -r ip; do echo "Máy khác trong Wi-Fi: http://$ip:8000"; done
else
    for ip in $(hostname -I); do echo "Máy khác trong Wi-Fi: http://$ip:8000"; done
fi
exec "$python" -u -m app.web.server
