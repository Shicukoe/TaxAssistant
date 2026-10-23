-- Khoản thu bị chấm dứt (docs/architecture.md, Model AI): "Chấm dứt việc thu, nộp lệ phí môn bài từ ngày 01 tháng 01
-- năm 2026" (khoản 7 Điều 10 Nghị quyết 198/2025/QH15) → quan hệ cham_dut tới các văn bản về khoản thu đó, do
-- app/ingest/link_replaced_documents.py ghi. View nhận thêm cham_dut và trả thêm loại quan hệ + nguyên văn câu tuyên bố
-- (nhãn "Không còn áp dụng … : «…»"). Cột mới thêm vào cuối — CREATE OR REPLACE VIEW chỉ cho thêm cột ở cuối.
CREATE OR REPLACE VIEW document_replacements AS
WITH direct AS (
    SELECT DISTINCT ON (r.to_doc)
           r.to_doc AS document_id, r.effective_from, r.from_doc AS replaced_by, r.source_label, r.has_exceptions,
           r.to_doc AS replaced_document, r.relation_type, r.quote
    FROM document_relations r
    WHERE r.relation_type IN ('thay_the', 'bai_bo', 'cham_dut') AND r.to_doc IS NOT NULL AND r.effective_from IS NOT NULL
    ORDER BY r.to_doc, r.effective_from
),
bases AS (
    SELECT from_doc AS consolidated, to_doc AS base
    FROM document_relations
    WHERE relation_type = 'hop_nhat' AND to_doc IS NOT NULL
),
base_replaced AS (
    SELECT DISTINCT ON (b.consolidated, b.base) b.consolidated, b.base, r.effective_from, r.from_doc, r.source_label,
           r.has_exceptions, r.relation_type, r.quote
    FROM bases b
    JOIN document_relations r ON r.relation_type IN ('thay_the', 'bai_bo', 'cham_dut') AND r.to_doc = b.base
                             AND r.effective_from IS NOT NULL
    WHERE NOT EXISTS (SELECT 1 FROM bases o WHERE o.consolidated = b.consolidated AND o.base = r.from_doc)
    ORDER BY b.consolidated, b.base, r.effective_from
),
consolidated AS (
    SELECT DISTINCT ON (br.consolidated)
           br.consolidated AS document_id, br.effective_from, br.from_doc AS replaced_by, br.source_label,
           br.has_exceptions, br.base AS replaced_document, br.relation_type, br.quote
    FROM base_replaced br
    WHERE (SELECT count(*) FROM base_replaced x WHERE x.consolidated = br.consolidated)
        = (SELECT count(*) FROM bases y WHERE y.consolidated = br.consolidated)
    ORDER BY br.consolidated, br.effective_from DESC
)
SELECT * FROM direct
UNION ALL
SELECT * FROM consolidated;
