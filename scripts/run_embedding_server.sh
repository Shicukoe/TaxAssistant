#!/usr/bin/env bash
# Chạy model embedding BGE-M3 bằng llama-server thứ hai (cổng 9932). Chạy được trên Git Bash (Windows) và Linux.
#
#   bash scripts/run_embedding_server.sh    để cửa sổ mở; Ctrl+C để tắt
#
# Cần cho: tính vector khi nạp dữ liệu (asset chunk_embeddings) và tìm theo nghĩa khi trả lời.
# Cờ lấy từ tools/server/README.md của llama.cpp b11796. GGUF tự chuyển từ trọng số gốc BAAI/bge-m3
# bằng convert_hf_to_gguf.py của cùng bản (docs/architecture.md, Embedding).
set -euo pipefail

llama_server="${LLAMA_SERVER_EXE:-D:/models/llama.cpp/b11796/bin/llama-server.exe}"
model_file="${EMBEDDING_MODEL_FILE:-D:/models/bge-m3/bge-m3-f16.gguf}"

# --embedding        chỉ phục vụ embedding (README: "use only with dedicated embedding models")
# --pooling cls      BGE-M3 lấy vector ở token CLS (model card BAAI/bge-m3)
# -c / -b / -ub 8192 model embedding xử lý cả đoạn trong MỘT batch → batch phải chứa được đoạn dài nhất (BGE-M3: 8.192 token)
# -ngl all           đưa mọi lớp lên GPU (~1,2 GB với bản f16)
# -np 1              một yêu cầu một lúc; app gửi theo lô
# --host 127.0.0.1   chỉ nghe trên máy này
# -a                 tên model trong API, khớp EMBEDDING_MODEL trong .env
exec "$llama_server" \
    -m "$model_file" \
    --embedding --pooling cls \
    -c 8192 -b 8192 -ub 8192 -ngl all -np 1 \
    --host 127.0.0.1 --port 9932 \
    -a bge-m3
