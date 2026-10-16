#!/usr/bin/env bash
# Chạy pipeline dữ liệu (Dagster) của TaxAssistant. Chạy được trên Git Bash (Windows) và Linux.
#
#   bash scripts/run_pipeline.sh        chạy toàn bộ một lần rồi thoát
#   bash scripts/run_pipeline.sh ui     mở giao diện web http://127.0.0.1:3000 và bật lịch hằng tuần
#
# Mở bằng "ui" thì lịch hằng tuần của Dagster cũng chạy (thứ Hai 9:00); lỡ giờ thì chạy bù một lần
# ngay khi mở. Phải để cửa sổ này mở tới khi chạy xong. Lịch sử chạy và log lưu ở dagster_home/ —
# mở giao diện để xem lần chạy nào lỗi, ở công đoạn nào, văn bản nào.
set -euo pipefail

# Git Bash: "pwd -W" cho đường dẫn kiểu D:/... mà dagster.exe (chương trình Windows) hiểu được.
# Linux không có "-W" nên dùng pwd thường.
project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
cd "$project_root"
export DAGSTER_HOME="$project_root/dagster_home"
export PYTHONIOENCODING=utf-8

# venv trên Linux để chương trình ở .venv/bin, trên Windows ở .venv/Scripts.
if [ -x .venv/bin/dagster ]; then
    dagster=.venv/bin/dagster
else
    dagster=.venv/Scripts/dagster.exe
fi

case "${1:-}" in
    "") exec "$dagster" job execute -m app.pipeline.definitions -j cap_nhat_du_lieu ;;
    ui) exec "$dagster" dev -m app.pipeline.definitions ;;
    *)  echo "Cách dùng: bash scripts/run_pipeline.sh [ui]" >&2; exit 2 ;;
esac
