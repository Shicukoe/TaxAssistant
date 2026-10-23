"""Đo tìm kiếm trên bộ câu hỏi có Điều đúng (docs/danh-gia.md mục 3): recall@5, MRR@10 cho từ khoá / theo nghĩa / kết hợp.
recall@20 để quyết có cần reranker: câu có Điều đúng trong top 20 mà ngoài top 5 là phần reranker có thể cứu (mục 5).

Chạy (cần server embedding: bash scripts/run_embedding_server.sh):
    python -m app.answer.measure_search                   bộ đo mặc định app/answer/search_eval_questions.json
    python -m app.answer.measure_search <file.json> -v    in từng câu
"""

import asyncio
import json
import sys
from datetime import date
from pathlib import Path

from app.answer.search_articles import search

MODES = ["tu_khoa", "nghia", "ket_hop"]
DEFAULT_FILE = Path(__file__).with_name("search_eval_questions.json")


def first_hit_rank(results: list[dict], gold: set[str], depth: int) -> int | None:
    """Thứ hạng (từ 1) của Điều đúng đầu tiên trong `depth` kết quả đầu."""
    for rank, row in enumerate(results[:depth], start=1):
        if f"{row['so_hieu']}|{row['dieu_so']}" in gold:
            return rank
    return None


async def measure(path: Path, verbose: bool) -> dict[str, dict[str, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    as_of = date.fromisoformat(data["moc_mac_dinh"])
    totals = {mode: {"recall@5": 0.0, "mrr@10": 0.0, "recall@20": 0.0} for mode in MODES}
    for item in data["cau_hoi"]:
        gold = set(item["dung"])
        line = []
        for mode in MODES:
            results, error = await search(item["hoi"], item.get("moc", as_of), mode)
            if error:
                raise RuntimeError(error)
            rank = first_hit_rank(results, gold, 20)
            totals[mode]["recall@5"] += rank is not None and rank <= 5
            totals[mode]["mrr@10"] += 1 / rank if rank and rank <= 10 else 0
            totals[mode]["recall@20"] += rank is not None
            line.append(f"{mode}={rank or '-'}")
        if verbose:
            print(f"{'  '.join(f'{x:<10}' for x in line)}  {item['hoi']}")
    count = len(data["cau_hoi"])
    return {mode: {k: round(v / count, 3) for k, v in values.items()} for mode, values in totals.items()}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    path = Path(args[0]) if args else DEFAULT_FILE
    result = asyncio.run(measure(path, "-v" in sys.argv), loop_factory=asyncio.SelectorEventLoop if sys.platform == "win32" else None)
    print(f"\n{'cách tìm':<10} recall@5  MRR@10   recall@20  ({path.name})")
    for mode, values in result.items():
        print(f"{mode:<10} {values['recall@5']:<9} {values['mrr@10']:<8} {values['recall@20']}")


if __name__ == "__main__":
    main()
