#!/usr/bin/env bash
# Web app: Hỏi đáp + Tra cứu, có đăng nhập (docs/ui-context.md, docs/architecture.md — Truy cập và phân quyền).
#
#   bash scripts/run_model_server.sh       (cửa sổ 1 — model viết, cổng 9931)
#   bash scripts/run_embedding_server.sh   (cửa sổ 2 — BGE-M3, cổng 9932; tắt thì chỉ tìm theo từ khoá)
#   bash scripts/run_web_demo.sh           (cửa sổ 3 — web, 127.0.0.1:8000)
#
# Máy khác (điện thoại, máy tính của mẹ) vào qua Tailscale — chạy MỘT lần, cấu hình giữ qua khởi động lại:
#   tailscale serve --bg 8000
# Lệnh in địa chỉ https://<tên-máy>.<tailnet>.ts.net — ghi vào WEB_PUBLIC_ORIGIN trong .env. Trên laptop cũng
# mở bằng địa chỉ này: cookie đăng nhập có cờ Secure.
# Tài khoản quản trị (thấy khung debug): đăng ký trên web, rồi  python -m app.web.manage_users --quan-tri <email> bat
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && { pwd -W 2>/dev/null || pwd; })"
cd "$project_root"
export PYTHONUTF8=1 PYTHONIOENCODING=utf-8

if [ -x .venv/bin/python ]; then python=.venv/bin/python; else python=.venv/Scripts/python.exe; fi

if ! curl -s --max-time 3 http://127.0.0.1:9931/health | grep -q '"ok"'; then
    echo "Cảnh báo: llama-server chưa chạy — trang Tra cứu vẫn dùng được, Hỏi sẽ báo lỗi." >&2
    echo "Mở cửa sổ khác: bash scripts/run_model_server.sh" >&2
fi

if command -v tailscale >/dev/null 2>&1 && tailscale serve status 2>/dev/null | grep -q "8000"; then
    tailscale serve status | grep -o "https://[^ ]*" | head -1 | sed 's/^/Mở (mọi máy trong tailnet): /'
else
    echo "Chưa bật tailscale serve — máy khác chưa vào được. Chạy một lần: tailscale serve --bg 8000" >&2
fi
exec "$python" -u -m app.web.server
