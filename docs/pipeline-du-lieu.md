# Pipeline dữ liệu (Dagster)

Pipeline tự động lấy văn bản luật về, kiểm chất lượng rồi nạp vào database. File này nói Dagster là gì, pipeline gồm những công đoạn nào, cách chạy, và khi có lỗi thì xem ở đâu.

## Dagster là gì

- **Một thư viện Python mã nguồn mở**, giấy phép Apache-2.0. Python **không có sẵn** Dagster: phải cài từ PyPI vào `.venv` bằng `pip install -e ".[pipeline]"`. Lệnh này cài hai gói: `dagster` (lõi) và `dagster-webserver` (giao diện web). Bản đang cài là 1.13.26, được ghim `>=1.13,<1.14` trong `pyproject.toml`.
- Mã nguồn ở github.com/dagster-io/dagster, tài liệu ở docs.dagster.io. Thông tin này đọc từ metadata của gói đã cài, ngày 16/10/2026.
- **Không phải Airflow và không lấy từ Airflow.** Đây là hai công cụ riêng, không dùng chung code, cùng làm một việc là điều phối pipeline. Dự án không cài Airflow.

### Vì sao chọn Dagster mà không chọn Airflow

| | Dagster | Airflow |
|---|---|---|
| Đơn vị chính | **Asset**: một bộ dữ liệu ("danh sách văn bản", "văn bản trong database") | **Task**: một việc cần làm |
| Kiểm chất lượng dữ liệu | Có sẵn (asset check) | Phải tự viết thành task riêng |
| Chạy trên máy cá nhân | Một lệnh `dagster dev`, lưu lịch sử bằng SQLite trong một thư mục | Cần scheduler, webserver và database metadata chạy liên tục. Không chạy thẳng trên Windows (cần WSL hoặc Docker) |
| Hợp với dự án này | Một người, một máy, vài công đoạn | Hợp với đội lớn, hàng trăm job |

Chọn ngày 15/10/2026, cùng lúc với quyết định giữ PostgreSQL.

## Các khái niệm dùng trong dự án

| Khái niệm Dagster | Nghĩa | Trong dự án |
|---|---|---|
| **Asset** | Một bộ dữ liệu, cùng hàm tạo ra nó | 5 asset, mỗi asset gọi đúng một hàm công đoạn trong `app/ingest/` |
| **Asset check** | Bài kiểm chạy sau khi tạo asset. Loại *blocking* không qua thì asset phụ thuộc không chạy | 6 bài, xem bảng dưới |
| **Job** | Một nhóm asset chạy cùng nhau | `cap_nhat_du_lieu`: cả 5 asset, chạy lần lượt trong một tiến trình để giữ nhịp 2 giây/lần với máy chủ |
| **Schedule** | Lịch hẹn chạy một job | `cap_nhat_hang_tuan`: thứ Hai 9:00 giờ Việt Nam |
| **Daemon** | Tiến trình nền canh lịch hẹn | Chỉ sống khi `dagster dev` đang mở |
| **Run** | Một lần chạy job, có log riêng | Xem trong giao diện, mục Runs |
| `DAGSTER_HOME` | Thư mục Dagster lưu lịch sử | `dagster_home/`, do script tự đặt |

Mọi định nghĩa nằm trong `app/pipeline/definitions.py`. File này chỉ nối các công đoạn với nhau; logic tải, tách và nạp nằm hết trong `app/ingest/`. Vì vậy mỗi công đoạn vẫn chạy được riêng mà không cần Dagster, ví dụ `python -m app.ingest.download_moj_documents`.

## Các công đoạn

```
source_health  (kiểm sống từng trang — mỗi trang một bài kiểm nguon_<tên>)
   │
   ├──► other_source_documents   (RSS congbao + docid mới của vanban.chinhphu.vn → văn bản thuế
   │                              → đối chiếu Bộ Tư pháp → tải bản gốc văn bản Bộ Tư pháp chưa có)
   ▼
moj_document_list ──► moj_documents ──┬──► database_documents ──► consolidated_links
(danh sách, sitemap)  (JSON Bộ Tư pháp) │                         (nối văn bản hợp nhất,
                                        │                          kiểm JSON đúng văn bản)
                                        ├──► congbao_documents
moj_attachments ────────────────────────┘    (tìm bù trên congbao)
(file đính kèm)
```

| Asset | Hàm gọi | Bài kiểm | Loại |
|---|---|---|---|
| `source_health` | `check_sources` | `nguon_<tên>` cho **từng trang** (vbpl_sitemap, moj_gateway, congbao, vanban_chinhphu, gdt): trả lời đúng **nội dung mong đợi**, không chỉ mã 200 | cảnh báo |
| `other_source_documents` | `discover_from_other_sources` | `ty_le_loi` ≤ 5%; `rss_congbao_co_the_sot`: cả 50 mục RSS đều mới hơn lần chạy trước → có thể đã sót văn bản | cảnh báo |
| `moj_document_list` | `update_document_list` | `sitemap_day_du`: sitemap phải có ≥ 90% số văn bản đã biết. Thấp hơn nghĩa là sitemap đang hỏng, không cập nhật | chặn |
| | | `doc_duoc_moi_sitemap`: mọi file sitemap đều đọc được | cảnh báo |
| `moj_documents` | `download_documents` | `ty_le_loi` ≤ 5% | chặn |
| `moj_attachments` | `download_attachments` | `ty_le_loi` ≤ 5% | cảnh báo |
| `congbao_documents` | `download_missing_from_congbao` | `ty_le_loi` ≤ 5% | cảnh báo |
| `database_documents` | `save_documents_to_database` | `ty_le_loi` ≤ 1% | chặn |
| `consolidated_links` | `link_consolidated_documents` | `ty_le_loi` ≤ 5%; `json_dung_van_ban`: liệt kê văn bản có số hiệu ở đầu chữ khác số hiệu của chính nó | cảnh báo |

Các ngưỡng trên là tạm, sẽ chỉnh sau vài lần chạy thật.

**Nhiều nguồn, tự chuyển khi hỏng** (chốt 22/10/2026):

| Việc | Thứ tự nguồn |
|---|---|
| Phát hiện văn bản mới | sitemap vbpl.vn → RSS "văn bản mới ban hành" của congbao → docid mới của vanban.chinhphu.vn |
| Lấy chữ / bản gốc | JSON Bộ Tư pháp → file đính kèm Bộ Tư pháp → congbao (Word trước, PDF sau) → vanban.chinhphu.vn |
| Công văn | gdt.gov.vn (đang chặn script) → vanban.chinhphu.vn (công văn Bộ Tài chính) — làm ở bước Công văn |

- Nhánh `other_source_documents` **không phụ thuộc** nhánh Bộ Tư pháp: cổng Bộ Tư pháp sập thì văn bản mới vẫn được tải về từ congbao và chinhphu.vn.
- Bản gốc của nguồn khác chỉ được **lưu** (`data/raw/congbao/new/`, `data/raw/vanban_chinhphu/`); nạp database khi đã có bước đọc file đính kèm.
- Văn bản thuế có trên nguồn khác mà Bộ Tư pháp chưa có → liệt kê trong báo cáo (`chua_co_tren_bo_tu_phap`). Danh sách dài ra theo thời gian là dấu hiệu cổng Bộ Tư pháp chậm hoặc hỏng.
- **Giới hạn:** nhiều nguồn giúp pipeline không dừng khi một trang hỏng, nhưng trang **đổi định dạng / API** thì vẫn phải sửa code đọc trang đó. `source_health` kiểm cả nội dung nên phát hiện được sớm.

**Khi `source_health` báo một nguồn chết:** công đoạn dùng nguồn đó dừng ngay với lỗi `[tên nguồn] source_health báo nguồn chết` và **không thử lại** (thử lại 10/20 phút vô ích vì `source_health` không chạy lại giữa chừng); lần chạy sau tự kiểm lại. Nhánh `other_source_documents` bỏ qua đúng nguồn chết, nguồn còn lại vẫn chạy (đã mô phỏng 22/10/2026).

**Biết trang nào hỏng:**
1. Giao diện Dagster → asset `source_health` → tab Checks: bài kiểm `nguon_<tên>` đỏ = trang đó hỏng; metadata có địa chỉ, mã HTTP, lý do, thời gian phản hồi.
2. Mọi dòng log lỗi mạng mở đầu bằng `[tên nguồn]`, ví dụ `[moj_gateway] HTTP 500 …`.
3. Bản ghi mới nhất cũng ở `data/raw/source_health.json`.

**Ba lớp chống lỗi, từ nhỏ tới lớn:**

1. **Một văn bản lỗi:** ghi mã văn bản và lý do vào báo cáo của công đoạn, rồi làm văn bản tiếp theo. Lỗi mạng, HTTP 429 và 5xx được thử lại sau 5 giây, rồi sau 15 giây.
2. **Nguồn sập:** lỗi liên tiếp 10 văn bản thì công đoạn dừng và báo `SourceUnavailableError`.
3. **Cả công đoạn hỏng:** Dagster chạy lại công đoạn tải sau 10 phút, rồi sau 20 phút. Nếu vẫn hỏng, công đoạn bị đánh dấu đỏ, các công đoạn phụ thuộc không chạy, còn công đoạn độc lập vẫn chạy.

## Cách chạy

Dùng bash: Git Bash trên Windows, hoặc terminal Linux khi lên VPS. Chạy từ thư mục gốc của dự án:

```bash
pip install -e ".[pipeline]"          # một lần, trong .venv

bash scripts/run_pipeline.sh          # chạy toàn bộ một lần rồi thoát
bash scripts/run_pipeline.sh ui       # mở giao diện http://127.0.0.1:3000 và bật lịch hằng tuần
```

- **Lịch hằng tuần chỉ chạy khi `ui` đang mở.** Đóng cửa sổ hoặc tắt máy thì không có gì chạy.
- Tới giờ mà máy đang tắt thì lần mở `ui` sau sẽ chạy bù **một** lần, không chạy bù nhiều tuần. Với lịch không chia partition như lịch này, Dagster chỉ xét lần hẹn gần nhất bị lỡ. Điều này đọc trong mã nguồn Dagster 1.13; **chưa thử bằng cách tắt máy thật**.
- Một lần chạy đầy đủ mất khoảng 70 phút (đo 15/10/2026), chủ yếu vì phải tải lại khoảng 1.600 văn bản còn hiệu lực với nhịp 2 giây. Phải để cửa sổ mở tới khi xong.
- Tắt giao diện: bấm Ctrl+C. Trong Git Bash, Ctrl+C có tắt sạch mọi tiến trình con không thì **chưa kiểm**. Nếu cổng 3000 vẫn bị chiếm, mở Task Manager và tắt các tiến trình `dagster.exe` và `python.exe` của dự án.
- Khi mở `ui` sẽ có hai dòng cảnh báo, đều vô hại:
  - "`dev_command` is superseded, use `dg dev`": `dg` là bộ lệnh mới của Dagster, nằm ở gói khác và chưa cài.
  - "Compute log capture disabled" (trên Windows): Dagster không bắt được `print` trên Windows. Log của dự án đi qua `logging` nên vẫn hiện đủ.

## Dagster lưu gì, ở đâu

- `dagster_home/dagster.yaml` (được commit): bắt log của logger `app.*` vào từng công đoạn, và tắt gửi số liệu sử dụng (telemetry).
- Phần còn lại của `dagster_home/` **không commit**:
  - `runs.db`, `history/`, `storage/`, `schedules/`: lịch sử chạy, log và trạng thái lịch hẹn.
  - Dagster dùng **SQLite riêng** cho các thứ này và không đụng tới PostgreSQL của app.
  - Thư mục khoảng 1,3 MB sau vài lần chạy.
- Dữ liệu văn bản vẫn nằm ở `data/raw/`, giống khi chạy từng công đoạn bằng tay.

## Khi có lỗi: xem ở đâu

1. Mở `bash scripts/run_pipeline.sh ui` rồi vào **Runs** và chọn lần chạy. Công đoạn hỏng có màu đỏ; bấm vào để xem log riêng của công đoạn đó.
2. Công đoạn chạy được nhưng có văn bản lỗi: vào **Assets**, chọn asset, xem phần metadata.
   - `danh_sach_loi` cho mã văn bản và lý do lỗi (tối đa 50 dòng).
   - Các số đếm cho kết quả: `tai_moi`, `khong_doi`, `thay_doi`…
3. Bài kiểm không qua: xem ở tab **Checks** của asset, có cả tỷ lệ lỗi và ngưỡng.
4. Chạy lại một công đoạn: trong giao diện, chọn asset rồi bấm **Materialize**. Hoặc chạy hàm công đoạn bằng tay: `python -m app.ingest.<file>`.
5. Ví dụ thật, lần chạy 15/10/2026:
   - 8 văn bản mới mà cổng Bộ Tư pháp trả HTTP 500 cả 3 lần thử. Các văn bản này nằm trong `danh_sach_loi`, công đoạn vẫn chạy hết, và tuần sau sẽ tự thử lại.
   - `database_documents` đỏ vì chưa đặt mật khẩu Postgres. Các công đoạn khác vẫn xong.
