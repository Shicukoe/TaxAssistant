#!/usr/bin/env bash
# Chuyển model NLI của guardrail g sang ONNX float32 — làm MỘT lần (hoặc khi đổi model). Chạy được trên Git Bash.
#
#   bash scripts/convert_nli_to_onnx.sh
#
# Chạy bằng optimum trong môi trường riêng (cần torch + transformers để đọc model gốc) — app chỉ cần onnxruntime +
# tokenizers (docs/architecture.md, Kiểm câu trả lời có căn cứ ủng hộ). Không nén int8: int8 làm lệch điểm đủ để
# đổi kết quả đạt / không đạt; float32 cho điểm trùng bản PyTorch (docs/danh-gia.md, guardrail g).
# Cài optimum vào môi trường riêng: uv pip install --python <python của môi trường đó> "optimum[onnxruntime]"
set -euo pipefail

optimum_cli="${OPTIMUM_CLI:-D:/tools/convert-venv/Scripts/optimum-cli.exe}"
model="${NLI_MODEL:-MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7}"
output_dir="${NLI_ONNX_DIR:-D:/models/nli-onnx/mdeberta-fp32}"

"$optimum_cli" export onnx --model "$model" --task text-classification "$output_dir"
echo "Xong: $output_dir — đặt NLI_ONNX_DIR trong .env nếu khác mặc định"
