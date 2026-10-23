#!/usr/bin/env bash
# Chạy model trả lời trên laptop bằng llama.cpp llama-server. Chạy được trên Git Bash (Windows) và Linux.
#
#   bash scripts/run_model_server.sh        để cửa sổ mở; Ctrl+C để tắt
#
# Cờ lấy từ tools/server/README.md của đúng bản llama.cpp đang dùng (b11796). Đổi bản thì đọc lại README.
# File lớn (bản dựng llama.cpp, file GGUF) nằm ngoài repo, mặc định ở D:/models — đổi bằng biến môi trường.
set -euo pipefail

llama_server="${LLAMA_SERVER_EXE:-D:/models/llama.cpp/b11796/bin/llama-server.exe}"
model_file="${MODEL_FILE:-D:/models/qwen3.5-4b/Qwen3.5-4B-Q4_K_M.gguf}"

# -ngl all       đưa mọi lớp lên GPU (~3 GB VRAM với Qwen3.5-4B Q4_K_M)
# -c 16384       độ dài context; tăng thì KV cache tốn thêm VRAM
# -fa on         flash attention; -ctk/-ctv q8_0 lượng tử KV cache cho đỡ VRAM
# -np 1          một slot: một người hỏi một lúc
# --host         chỉ nghe trên máy này — không mở ra mạng
# --cors-origins localhost / --no-cors-credentials
#                mặc định CORS cho mọi nguồn: trang web lạ mở trong trình duyệt trên laptop gọi được model.
#                Backend gọi server trực tiếp, không cần CORS; giao diện web có sẵn (http://127.0.0.1:9931) vẫn dùng được.
# -a             tên model trong API, khớp LLM_MODEL trong .env
# -rea off       tắt chế độ suy luận (mốc gốc); bật hay không quyết định bằng bộ đo
#
# Lấy mẫu — mặc định cho client KHÔNG gửi tham số, ví dụ giao diện chat có sẵn. App luôn gửi rõ (config.py).
# Lý do và nguồn nghiên cứu: docs/danh-gia.md, mục "Thông số lấy mẫu khi viết câu trả lời".
# --temp 0.4     T=0 làm model nhỏ dễ lặp vô tận khi hỏi đáp trên tài liệu (Roig 2026); 0.4 là đầu thấp của khoảng khuyến nghị.
#                Mặc định của llama-server là 0.8.
# --top-p 0.8 --top-k 20 --min-p 0
#                theo model card Qwen3.5, chế độ không suy luận.
# --seed 42      cố định → cùng câu hỏi ra cùng câu trả lời, để debug.
# --repeat-penalty 1.0 / --presence-penalty 0
#                tắt phạt lặp: trích nguyên văn luật phải lặp đúng chữ, phạt lặp làm model đổi chữ → trượt kiểm trích dẫn.
exec "$llama_server" \
    -m "$model_file" \
    -ngl all -c 16384 -fa on -ctk q8_0 -ctv q8_0 -np 1 \
    --host 127.0.0.1 --port 9931 \
    --cors-origins localhost --no-cors-credentials \
    --temp 0.4 --top-p 0.8 --top-k 20 --min-p 0 --seed 42 \
    --repeat-penalty 1.0 --presence-penalty 0 \
    -a qwen3.5-4b --metrics -rea off
