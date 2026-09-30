-- Cấu trúc database ban đầu.
-- Mỗi bảng có chú thích giải thích vì sao nó tồn tại. Lý do chi tiết: docs/quyet-dinh.md

CREATE EXTENSION IF NOT EXISTS vector;      -- lưu vector ngay trong Postgres, không cần Qdrant
CREATE EXTENSION IF NOT EXISTS unaccent;    -- Postgres không có cấu hình tiếng Việt → tìm kiếm bỏ dấu
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- unaccent() không immutable → không dùng trực tiếp trong generated column.
-- Wrapper immutable là cách xử lý chuẩn cho việc này.
CREATE OR REPLACE FUNCTION f_unaccent(text)
RETURNS text AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT;

-- =====================================================================
-- documents — một văn bản
-- =====================================================================
CREATE TABLE documents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source          text NOT NULL,      -- 'moj_gateway' | 'congbao' | 'gdt'
    source_uuid     text,               -- id của chính nguồn (uuid vbpl, uuid WCM của gdt)
    source_url      text NOT NULL,

    so_hieu         text,               -- '18/2026/TT-BTC'
    loai            text,               -- docType.name: 'Thông tư', 'Văn bản hợp nhất', ...
    doc_group       text NOT NULL,      -- 'VBQPPL' | 'VBHN' | 'CV' | 'UNKNOWN'
    co_quan         text,
    linh_vuc        text[],

    ngay_ban_hanh   date,
    eff_from        date,
    eff_to          date,
    eff_status_code text,               -- 'HHL1P' = hết hiệu lực một phần, ...

    is_consolidated boolean NOT NULL DEFAULT false,
    -- cổng JSON có sẵn cờ này: phân biệt văn bản luật với công văn
    is_administrative boolean NOT NULL DEFAULT false,

    -- Quy tắc: chữ OCR chỉ để TÌM, không bao giờ hiển thị làm trích dẫn.
    -- Cột này là thứ chặn điều đó ở tầng dữ liệu.
    text_origin     text NOT NULL DEFAULT 'none'
                    CHECK (text_origin IN ('native', 'ocr', 'none')),

    raw_path        text,               -- bản gốc trên đĩa (luôn lưu trước khi xử lý)
    fetched_at      timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT documents_source_uuid_uniq UNIQUE (source, source_uuid)
);

CREATE INDEX documents_so_hieu_idx   ON documents (so_hieu);
CREATE INDEX documents_eff_idx       ON documents (eff_from, eff_to);
CREATE INDEX documents_doc_group_idx ON documents (doc_group);

-- =====================================================================
-- document_relations — quan hệ giữa các văn bản
-- Cổng JSON không trả quan hệ văn bản (documentRelatedList luôn rỗng),
-- nên quan hệ phải tự dựng từ footnote VBHN và từ parse text.
-- =====================================================================
CREATE TABLE document_relations (
    id            bigserial PRIMARY KEY,
    from_doc      uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    to_doc        uuid REFERENCES documents(id) ON DELETE SET NULL,
    to_doc_ref    text,                 -- khi văn bản đích chưa có trong corpus
    relation_type text NOT NULL,        -- thay_the|sua_doi|bai_bo|hop_nhat|dan_chieu|can_cu|...
    evidence      text NOT NULL,        -- 'footnote' | 'text_parse'
    confidence    real,
    CONSTRAINT relation_has_target CHECK (to_doc IS NOT NULL OR to_doc_ref IS NOT NULL)
);

CREATE INDEX document_relations_from_idx ON document_relations (from_doc);
CREATE INDEX document_relations_to_idx   ON document_relations (to_doc);

-- =====================================================================
-- provisions — Điều / Khoản / Điểm
-- Markup của cổng JSON là PHẲNG: quan hệ cha–con suy từ thứ tự xuất hiện, không từ lồng thẻ.
-- 'tiểu mục' cũng tồn tại (Luật 64/2025 Điều 7 khoản 2) nhưng chưa cần.
-- =====================================================================
CREATE TABLE provisions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id    uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    -- uuid từ class prov-* của markup; NULL khi provision đến từ regex fallback
    provision_uuid text,
    level          text NOT NULL CHECK (level IN ('dieu', 'khoan', 'diem')),
    so             text NOT NULL,       -- '13' | '4' | 'a' | '5.3'  (điểm không chỉ là a/b/c)
    -- Luật 64/2025 Điều 7 khoản 2: CHỈ Điều bắt buộc có tên. Khoản/điểm luôn NULL.
    ten            text,
    parent_id      uuid REFERENCES provisions(id) ON DELETE CASCADE,
    ordinal        integer NOT NULL,    -- thứ tự trong tài liệu, dùng để dựng lại cây
    text           text NOT NULL,
    -- nguồn: markup phủ không đủ (4/9 Điều trên TT 18/2026) → regex fallback bắt buộc
    parsed_by      text NOT NULL CHECK (parsed_by IN ('markup', 'regex')),

    CONSTRAINT provisions_ten_only_dieu CHECK (level = 'dieu' OR ten IS NULL)
);

CREATE INDEX provisions_doc_idx    ON provisions (document_id, ordinal);
CREATE INDEX provisions_parent_idx ON provisions (parent_id);
CREATE INDEX provisions_level_idx  ON provisions (document_id, level);

-- =====================================================================
-- chunks — mỗi đoạn tìm kiếm là một ĐIỀU TRỌN VẸN (câu dẫn + mọi khoản + mọi điểm)
-- =====================================================================
CREATE TABLE chunks (
    id                 bigserial PRIMARY KEY,
    document_id        uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    dieu_provision_id  uuid NOT NULL UNIQUE REFERENCES provisions(id) ON DELETE CASCADE,
    text               text NOT NULL,
    token_count        integer,
    fts                tsvector GENERATED ALWAYS AS
                       (to_tsvector('simple', f_unaccent(text))) STORED
);

CREATE INDEX chunks_fts_idx ON chunks USING gin (fts);
CREATE INDEX chunks_doc_idx ON chunks (document_id);

-- =====================================================================
-- chunk_positions — vị trí từng khoản/điểm bên trong một Điều
-- Đây là bảng cho phép ĐỐI CHIẾU trích dẫn. Không có nó thì không bắt được
-- trích dẫn bịa, và yêu cầu "trích dẫn nguyên văn" không thực thi được.
-- =====================================================================
CREATE TABLE chunk_positions (
    id           bigserial PRIMARY KEY,
    chunk_id     bigint NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    provision_id uuid NOT NULL REFERENCES provisions(id) ON DELETE CASCADE,
    level        text NOT NULL CHECK (level IN ('dieu', 'khoan', 'diem')),
    so           text NOT NULL,
    char_start   integer NOT NULL,
    char_end     integer NOT NULL,
    CONSTRAINT chunk_positions_span CHECK (char_end > char_start),
    CONSTRAINT chunk_positions_uniq UNIQUE (chunk_id, provision_id)
);

CREATE INDEX chunk_positions_chunk_idx ON chunk_positions (chunk_id);

-- =====================================================================
-- amendments — lịch sử sửa đổi, đọc từ chú thích văn bản hợp nhất
-- target_kind='cum_tu' là thật, không phải trường hợp lạ: một quy định
-- (khoản 1 Điều 1 NĐ 141/2026) thay cụm từ "500 triệu đồng" → "01 tỷ đồng"
-- ở 18+ vị trí. Quan hệ sửa đổi → đích là NHIỀU-NHIỀU.
-- =====================================================================
CREATE TABLE amendments (
    id                  bigserial PRIMARY KEY,
    target_document_id  uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    target_provision_id uuid REFERENCES provisions(id) ON DELETE CASCADE,
    target_kind         text NOT NULL
                        CHECK (target_kind IN ('dieu','khoan','diem','ten_dieu','cum_tu')),
    phrase_from         text,           -- chỉ cho target_kind='cum_tu'
    phrase_to           text,
    amending_doc_id     uuid REFERENCES documents(id) ON DELETE SET NULL,
    amending_ref_text   text NOT NULL,  -- 'khoản 1 Điều 1 Nghị định số 141/2026/NĐ-CP'
    eff_from            date,           -- 'có hiệu lực kể từ ngày ...'
    footnote_index      integer,
    footnote_text       text NOT NULL,
    CONSTRAINT amendments_phrase CHECK (
        target_kind <> 'cum_tu' OR (phrase_from IS NOT NULL AND phrase_to IS NOT NULL))
);

CREATE INDEX amendments_target_doc_idx  ON amendments (target_document_id);
CREATE INDEX amendments_target_prov_idx ON amendments (target_provision_id);
CREATE INDEX amendments_eff_idx         ON amendments (eff_from);

-- =====================================================================
-- embeddings — vector của từng đoạn, để tìm theo nghĩa
-- model_name/version là CỘT, không phải cấu hình: đổi model embedding là
-- thêm một bộ vector mới, không phải migrate. Vector embed lại được nên
-- việc chọn model không phải quyết định khoá.
--
-- ponytail: cột `vector` để không chiều vì model chưa chọn.
-- Chưa đặt được index HNSW/IVFFlat khi chưa cố định chiều — migration 002
-- ở bước "Tìm kiếm" sẽ thêm cột có chiều cụ thể + index sau khi đo xong model.
-- =====================================================================
CREATE TABLE embeddings (
    id            bigserial PRIMARY KEY,
    chunk_id      bigint NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
    model_name    text NOT NULL,
    model_version text NOT NULL,
    dim           integer NOT NULL,
    vec           vector NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT embeddings_uniq UNIQUE (chunk_id, model_name, model_version)
);

-- =====================================================================
-- questions / answers — để đánh giá (eval set) và để mẹ xem lại lịch sử
-- =====================================================================
CREATE TABLE questions (
    id          bigserial PRIMARY KEY,
    asked_at    timestamptz NOT NULL DEFAULT now(),
    text        text NOT NULL,
    -- Haiku phân loại: tra_cuu|giai_thich|tinh_toan|vi_pham|so_sanh_thoi_gian|van_ban_moi
    kind        text,
    sac_thue    text,
    -- mốc thời gian câu hỏi hướng tới, mặc định hôm nay
    as_of_date  date NOT NULL DEFAULT CURRENT_DATE
);

CREATE TABLE answers (
    id          bigserial PRIMARY KEY,
    question_id bigint NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    answered_at timestamptz NOT NULL DEFAULT now(),
    text        text NOT NULL,
    model       text NOT NULL,
    -- có căn cứ hay không là một trạng thái riêng, không chỉ là câu chữ trong text
    has_cause   boolean NOT NULL,
    -- trích dẫn ĐÃ đối chiếu với chunk_positions
    citations   jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- câu tham chiếu: khi điều luật trỏ sang văn bản khác mà thiếu phần đó thì không hiểu được
    cross_refs  jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX answers_question_idx ON answers (question_id);

-- =====================================================================
-- usage_log — nguồn sự thật DUY NHẤT về chi phí.
-- Không đọc từ OAuth/subscription: cửa sổ 5 tiếng và "% còn lại" là khái niệm
-- của subscription Claude Code, không phải của API.
-- =====================================================================
CREATE TABLE usage_log (
    id            bigserial PRIMARY KEY,
    ts            timestamptz NOT NULL DEFAULT now(),
    question_id   bigint REFERENCES questions(id) ON DELETE SET NULL,
    model         text NOT NULL,
    input_tokens  integer NOT NULL DEFAULT 0,
    output_tokens integer NOT NULL DEFAULT 0,
    cache_read    integer NOT NULL DEFAULT 0,
    cache_write   integer NOT NULL DEFAULT 0,
    cost_usd      numeric(12, 6) NOT NULL
);

CREATE INDEX usage_log_ts_idx ON usage_log (ts);
