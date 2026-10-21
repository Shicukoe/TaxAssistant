#!/usr/bin/env bash
# Demo chatbot thuế trong terminal: vừa chat vừa xem state sau từng bước.
#
#   bash scripts/run_model_server.sh     (cửa sổ 1 — model)
#   bash scripts/chat_demo.sh            (cửa sổ 2 — chat)
#
# Lệnh trong lúc chat: /moi (hội thoại mới), /lichsu (state sau từng bước), /thoat
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
cd "$project_root"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8
# Windows không bật symlink → cache HuggingFace vẫn chạy, chỉ tốn chỗ hơn; tắt cảnh báo lặp lại mỗi lần chạy.
export HF_HUB_DISABLE_SYMLINKS_WARNING=1

if [ -x .venv/bin/python ]; then python=.venv/bin/python; else python=.venv/Scripts/python.exe; fi

if ! curl -s --max-time 3 http://127.0.0.1:9931/health | grep -q '"ok"'; then
    echo "llama-server chưa chạy — mở cửa sổ khác: bash scripts/run_model_server.sh" >&2
    exit 1
fi
# -u: không đệm đầu ra, để dòng debug hiện ngay trên Git Bash
exec "$python" -u -m app.answer.chat_in_terminal
