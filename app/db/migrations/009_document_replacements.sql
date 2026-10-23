-- Văn bản bị văn bản mới tuyên bố hết hiệu lực (docs/architecture.md, Model AI) — cổng Bộ Tư pháp không ghi ngày hết
-- hiệu lực cho Luật Quản lý thuế 38/2019, Luật Thuế TNCN 04/2007… dù luật mới đã ghi rõ (phát hiện 23/10/2026).
-- Quan hệ thay_the / bai_bo (văn bản mới → văn bản cũ) do app/ingest/link_replaced_documents.py ghi, tính lại mỗi lần chạy.
ALTER TABLE document_relations
    ADD COLUMN effective_from date,     -- văn bản cũ hết hiệu lực từ ngày này
    ADD COLUMN source_label text,       -- 'khoản 3 Điều 52' — chỗ ghi câu tuyên bố trong văn bản mới
    ADD COLUMN quote text,              -- nguyên văn câu tuyên bố
    ADD COLUMN has_exceptions boolean;  -- câu có "trừ …": một phần văn bản cũ còn áp dụng

-- Văn bản nào hết hiệu lực từ ngày nào, theo văn bản nào. Bản hợp nhất hết hiệu lực khi MỌI văn bản gốc của nó đã bị
-- thay bởi văn bản ngoài nhóm gốc: 15/VBHN-BTC nối với 83/2013, 125/2020 và 126/2020 — 83/2013 bị 126/2020 thay
-- nhưng 15/VBHN-BTC vẫn là bản đang dùng. Ngày của bản hợp nhất là ngày văn bản gốc cuối cùng bị thay.
CREATE VIEW document_replacements AS
WITH direct AS (
    SELECT DISTINCT ON (r.to_doc)
           r.to_doc AS document_id, r.effective_from, r.from_doc AS replaced_by, r.source_label, r.has_exceptions,
           r.to_doc AS replaced_document
    FROM document_relations r
    WHERE r.relation_type IN ('thay_the', 'bai_bo') AND r.to_doc IS NOT NULL AND r.effective_from IS NOT NULL
    ORDER BY r.to_doc, r.effective_from
),
bases AS (
    SELECT from_doc AS consolidated, to_doc AS base
    FROM document_relations
    WHERE relation_type = 'hop_nhat' AND to_doc IS NOT NULL
),
base_replaced AS (
    SELECT DISTINCT ON (b.consolidated, b.base) b.consolidated, b.base, r.effective_from, r.from_doc, r.source_label,
           r.has_exceptions
    FROM bases b
    JOIN document_relations r ON r.relation_type IN ('thay_the', 'bai_bo') AND r.to_doc = b.base AND r.effective_from IS NOT NULL
    WHERE NOT EXISTS (SELECT 1 FROM bases o WHERE o.consolidated = b.consolidated AND o.base = r.from_doc)
    ORDER BY b.consolidated, b.base, r.effective_from
),
consolidated AS (
    SELECT DISTINCT ON (br.consolidated)
           br.consolidated AS document_id, br.effective_from, br.from_doc AS replaced_by, br.source_label,
           br.has_exceptions, br.base AS replaced_document
    FROM base_replaced br
    WHERE (SELECT count(*) FROM base_replaced x WHERE x.consolidated = br.consolidated)
        = (SELECT count(*) FROM bases y WHERE y.consolidated = br.consolidated)
    ORDER BY br.consolidated, br.effective_from DESC
)
SELECT * FROM direct
UNION ALL
SELECT * FROM consolidated;
