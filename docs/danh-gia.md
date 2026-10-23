# Đánh giá và guardrail

Mọi công đoạn dùng model phải có hai thứ:

- **Guardrail** — kiểm tra chạy **mỗi lần** trong code, không dùng model, chặn lỗi trước khi tới người dùng.
- **Bài đo** — chạy **ngoại tuyến** trên một bộ dữ liệu có đáp án, cho ra con số, để biết model tốt tới đâu và một thay đổi có làm nó tệ đi không.

Chỉ số lấy từ nghiên cứu đã công bố (danh mục cuối file). Chỉ số nào là riêng của dự án thì ghi rõ. Nguồn kiểm ngày 13/10/2026.

---

## Nguyên tắc chung

1. **Không đưa công đoạn nào vào dùng khi chưa có bài đo và kết quả mốc gốc** (quy tắc bất biến trong `architecture.md`).
2. **Ngưỡng đạt chưa đặt.** Lần đo đầu là **mốc gốc**. Sau đó, mỗi thay đổi (prompt, model, cách tìm kiếm, cách tách văn bản) phải chạy lại bài đo và không được làm chỉ số chính xấu đi. Ngưỡng do người dùng chốt sau khi thấy mốc gốc.
3. **Guardrail tất định đi trước giám khảo AI.** Cái gì kiểm được bằng so khớp chữ, so số thì không giao cho model chấm.
4. **Giám khảo AI phải được hiệu chỉnh bằng người.** Mẹ chấm một mẫu; báo tỷ lệ khớp và Cohen's kappa giữa giám khảo và mẹ. ARES dùng vài trăm nhãn người để sửa sai số của giám khảo [ARES]; nghiên cứu về công cụ tra cứu luật dùng người có chuyên môn chấm theo bảng tiêu chí, kappa 0,77 giữa người chấm [Magesh].
5. **Model viết câu trả lời không được tự chấm mình** — LLM giám khảo có thiên lệch tự khen, thiên lệch vị trí, thiên lệch thích câu dài [Zheng].
6. **Giám khảo là Claude, chỉ trong bộ đo** (chốt 21/10/2026). Tốn tiền API, nên chỉ chạy bộ đo khi có thay đổi, không chạy cho từng câu hỏi thật. Điểm chấm của Claude **không bao giờ** làm dữ liệu huấn luyện (quy tắc bất biến số 13 trong `architecture.md`).
7. **Kết quả mỗi lần đo được lưu lại** (ngày, phiên bản, con số) để so với lần trước.
8. **Ba tập dữ liệu tách rời** (chốt 22/10/2026):
   - **Huấn luyện** — dữ liệu để fine-tune (nhãn từ quy tắc, câu hỏi do model mở sinh, câu mẹ sửa).
   - **Kiểm định (validation)** — câu hỏi thật có nhãn của mẹ, dùng để **chỉnh**: khớp temperature scaling cho classifier, chọn ngưỡng độ tin, chọn temperature sinh câu trả lời, so prompt.
   - **Bộ đo (test)** — câu hỏi thật có nhãn của mẹ, **không bao giờ dùng để chỉnh**, chỉ chạy để báo số. Chỉnh trên bộ đo thì con số đẹp giả.
   Một câu hỏi chỉ nằm ở một tập; câu hỏi gần giống nhau (cùng ý, đổi vài chữ) cũng phải cùng tập. Tỷ lệ chia: chưa chốt — tuỳ số câu mẹ gom được.

---

## 1. OCR — Tesseract tiếng Việt

Dùng cho: PDF đính kèm (140 file, 7.920 trang — 59 file không có lớp chữ) và công văn scan. Chọn Tesseract (chốt 13/10/2026) vì Unlimited-OCR bản gốc ~6,7 GB không vừa GPU 6 GB.

**Guardrail khi chạy**

- Chữ OCR lưu với `text_origin = 'ocr'` → **không bao giờ được trích**, chỉ để tìm (đã chặn ở schema).
- Tesseract trả độ tin cậy cho từng từ → trang có độ tin cậy trung bình thấp thì gắn cờ, không lặng lẽ đưa vào kho. Ngưỡng đặt sau khi có mốc gốc.

**Bài đo**

| Chỉ số | Cách tính | Vì sao | Nguồn |
|---|---|---|---|
| **CER** — tỷ lệ lỗi ký tự | (số ký tự thêm + bớt + thay để biến bản OCR thành bản đúng) ÷ số ký tự bản đúng. Khoảng cách Levenshtein | Chỉ số OCR thông dụng nhất | [Neudecker], [OCR-D] |
| **WER** — tỷ lệ lỗi từ | Như CER nhưng tính theo từ | Tìm kiếm theo từ khóa hỏng theo từ, không theo ký tự | [Neudecker] |
| **CER bỏ dấu** | CER sau khi bỏ dấu tiếng Việt ở cả hai bản | Tách lỗi **dấu** ("thuê" ↔ "thuế") khỏi lỗi **chữ** | Riêng của dự án |
| **Độ chính xác chữ số** | Lấy mọi dãy số (tiền, ngày, số hiệu, tỷ lệ) trong bản đúng; tỷ lệ dãy xuất hiện **y hệt** trong bản OCR | Rủi ro lớn nhất: "8.000.000" đọc thành "3.000.000" | Riêng của dự án |
| **Ảnh hưởng tới tìm kiếm** | recall@5 của bộ câu hỏi khi kho dùng chữ OCR so với khi dùng chữ gốc | Lỗi OCR lan sang chất lượng RAG; CER thấp chưa chắc tìm kiếm tốt | [OHRBench] |

**Chuẩn hóa trước khi đo** (ghi rõ vì các công cụ tính CER khác nhau cho kết quả khác nhau [Neudecker]): Unicode NFC, gộp khoảng trắng liên tiếp, bỏ số trang và đầu trang/chân trang lặp lại. Không hạ chữ thường — chữ hoa sai cũng là lỗi.

**Dữ liệu đo:** khoảng 20 văn bản mà cổng Bộ Tư pháp có **cả** chữ HTML (làm đáp án) **và** file PDF. Chọn trải đều theo thời kỳ (scan cũ, PDF mới) và loại văn bản. Phải tải thêm PDF của các văn bản này — hiện chỉ có PDF của văn bản JSON rỗng.

**Công cụ:** khoảng cách Levenshtein viết bằng Python thuần (vài dòng), không thêm thư viện.

**Làm ở bước:** đọc chữ file đính kèm (bước 2); dùng lại cho công văn scan (bước 5).

---

## 2. Tách Điều / khoản / điểm

Không dùng model (biểu thức chính quy), nhưng sai ở đây làm hỏng mọi bước sau nên vẫn đo.

- **Guardrail:** vị trí khoản/điểm phải trùng ranh giới dòng (`split_articles.py`, `self_check`).
- **Bài đo:** so với markup của cổng Bộ Tư pháp. Kết quả 02/10/2026: bắt được 99,8% Điều, 98,1% khoản, 98,0% điểm. Chi tiết ở `nguon-du-lieu.md`.
- **Cắt theo đề mục** (văn bản không có Điều): cổng không có markup cho văn bản cũ nên không có đáp án tự động. Đo ba thứ: (1) **độ phủ** — phần chữ từ đề mục đầu tiên tới khối chữ ký nằm trong một mục nào đó; (2) **đề mục bị bỏ** — dòng trông như đề mục ("III.", "B.") nhưng không được nhận vì sai thứ tự, liệt kê ra để xem bằng tay; (3) **tự tay xem 10 văn bản** chọn ngẫu nhiên, so mục cắt ra với bản gốc.
  - **Kết quả 22/10/2026** (700 văn bản: 571 cắt theo mục, 129 theo độ dài): độ phủ **96,4%**; **124 dòng giống đề mục bị bỏ ở 35/571 văn bản** — phần lớn đúng là phải bỏ (dòng trong bảng "II. Đô thị loại II", biểu mẫu "I. PHẦN TỰ KÊ KHAI"), còn lại là lỗi thật: số La Mã dùng ở hai cấp (07-TC/TCT: danh sách I…VIII loại tài nguyên nằm trong mục II), văn bản gốc đánh trùng số (29/TC-TCT: hai mục III). Hệ quả: chữ vẫn tìm và trích nguyên văn được, nhưng **nhãn mục có thể sai** ở các văn bản này. 10 mẫu: 9 sạch, 1 sót một đề mục (02/2007/TT-BTM, "III. ĐIỀU KHOẢN THI HÀNH").
- **Phép kiểm chất lượng từng văn bản** (lớp 2, `check_document_quality.py`, đo 22/10/2026 trên 2.611 văn bản có chữ): `ma_chu` trượt 5, `thu_tu_de_muc` 110, `do_phu` 63, `doan_qua_dai` 98 → **115 văn bản cách ly** (81 chữ thật, 34 PDF). Bắt được lỗi **chưa ai viết quy tắc cho**: HTML của cổng còn chữ TCVN3 (90/2004/QĐ-BTC "Dông cô tay cÇm"); chú thích cuối của văn bản hợp nhất bị tách thành Điều ("[20] Điều 44 của Luật…", "Điều 7, Điều 8 của Nghị định…", Điều trong đoạn trích của chú thích — 113/VBHN-VPQH, 27/2026/VBHN-NĐ-BTC). Báo nhầm đã sửa: dấu nhân "×" trong công thức trùng mã TCVN3 của "ì". Ngưỡng `do_phu` 90%, `doan_qua_dai` 20.000 ký tự là tạm.
- **Lớp 1 — đo Apache Tika 4.1.0** (Java Temurin 21, 22/10/2026) trên đúng 317 file Word/RTF + 141 PDF, so với Word + pypdf:
  - **Word/RTF:** chữ phần thân khớp ≥ 90% ở 304/317 file; 13 file lệch vì Tika đọc thêm header/footer trang ("Công báo số… ngày…"). Chữ Tika thô còn 290 dòng mã TCVN3 (phần lớn là header RTF — Tika không chuyển header), sau bộ sửa TCVN3 của dự án còn 7 dòng — bằng Word. XHTML của Tika đánh dấu `div class="header|footer"` cho Word 97 (lọc được), RTF thì không.
  - **PDF:** tỷ lệ chữ hợp lệ (chữ có trong từ vựng ≥ 3 lần của 2.264 văn bản chữ thật, tính theo số chữ) **Tika 95,0% so với pypdf 90,4%**; Tika tốt hơn ở 37 file, kém hơn ở 4, ngang ở 43; 57 file cả hai gần như rỗng (ảnh scan). pypdf hay tách sai âm tiết ("c ủa", "n ăm"), Tika (PDFBox) không.
  - Thời gian: 476 giây cho 458 file (2 tiến trình) — so với Word 92 giây + pypdf 123 giây; chỉ chạy một lần mỗi file.
  - **Đã chuyển sang Tika** (22/10/2026). So trước/sau trên văn bản lấy chữ từ file đính kèm: 50 văn bản PDF trước đây không tách được nay tìm được; văn bản chữ Word: 285/286 giữ nguyên số đoạn, 1 tốt hơn. Bộ đo cố định thêm 2 ca cho lỗi riêng của Tika (ký tự điều khiển Word thành "�"; vùng chú thích Word sau phần thân).
- **Lớp 4 — bộ phân loại dòng học từ markup** (scikit-learn 1.9.1: TF-IDF ký tự 1–4 + hồi quy logistic, 22/10/2026). Văn bản có markup đủ ở cấp Điều: 687; chia theo văn bản 80/20 (549 học, 138 đo, 20.193 dòng). F1 so với markup — **regex**: Điều 0,999 · khoản 0,990 · điểm 0,946 · chữ thường 0,993 (trung bình 0,982); **model**: 0,990 · 0,950 · 0,922 · 0,983 (0,961). **Regex tốt hơn ở mọi nhãn → giữ regex.** Model sai chủ yếu ở danh sách đánh số ngoài Điều ("1. Luật An ninh mạng số…" ở phần căn cứ) — nhìn từng dòng riêng lẻ thì không biết vị trí và thứ tự, regex thì biết. Thiên lệch cần biết: chọn văn bản "đủ markup" bằng cách so số Điều với regex nên cấp Điều nghiêng về regex; markup tự nó không nhất quán ở dạng "1.1." (lúc là khoản, lúc không). Thử lại khi có lý do: model có ngữ cảnh (dòng trước/sau, đang trong Điều hay không — kiểu CRF) và khi bộ đo cố định cho thấy lỗi cấu trúc mà regex không sửa được.
- **Bộ đo cố định** (lớp 3, `check_golden_cases.py`): 14 ca, mỗi ca một lỗi gặp thật; chạy trong Dagster (bài kiểm `bo_do_co_dinh`, chặn). Mỗi lần sửa quy tắc tách còn **so trước/sau trên toàn kho**: sửa quy tắc đề mục Điều lần đầu làm mất đề mục thật "Điều 4ể Hàng hóa GIC" (dấu chấm hỏng thành chữ) và "Điều 1, Phạm vi điều chỉnh" — phát hiện nhờ so, sửa trước khi nạp. Lần cuối: 13 Điều bị bỏ, đều là Điều giả.
  - Lỗi đã sửa trong lúc đo: "Phần A", "PHẦN B" (có chữ "Phần") ban đầu không được nhận → mục cuối của phần A nuốt cả văn bản (60/2007/TT-BTC: một mục 100.146 ký tự). Sau khi sửa, mục dài nhất 62.357 ký tự; 187/2.755 mục dài hơn 8.000 ký tự (tỷ lệ gần bằng Điều: 456/12.353).

---

## 3. Tìm kiếm — embedding + từ khóa

**Guardrail:** luôn kết hợp tìm theo nghĩa với tìm theo từ khóa — không để embedding là đường duy nhất.

**Bài đo**

| Chỉ số | Cách tính | Nguồn |
|---|---|---|
| **recall@5** | Tỷ lệ câu hỏi có Điều đúng nằm trong 5 kết quả đầu | Chỉ số tìm kiếm chuẩn |
| **MRR@10** | Trung bình của 1 ÷ (thứ hạng của Điều đúng đầu tiên), tính trong 10 kết quả đầu | Chỉ số tìm kiếm chuẩn |
| **nDCG@10** | Tính cả thứ hạng lẫn mức độ liên quan có cấp bậc | BEIR chọn làm chỉ số chính vì "cân bằng tốt cho cả đánh giá liên quan nhị phân lẫn có cấp bậc", còn precision/recall không tính thứ hạng [BEIR] |

**Dữ liệu đo:** câu hỏi thật của mẹ, mỗi câu gắn nhãn các Điều đúng (Điều chính = mức 2, Điều liên quan = mức 1 cho nDCG).

**Model embedding ứng viên** (kiểm HuggingFace 22/10/2026 — chất lượng trên câu hỏi thuế **chưa đo**):

| Model | Giấy phép | Ghi chú |
|---|---|---|
| BGE-M3 | MIT | Đa ngôn ngữ, 8.192 token — Điều dài vẫn vừa |
| Qwen3-Embedding-0.6B | Apache-2.0 | Đa ngôn ngữ |
| bkai-foundation-models/vietnamese-bi-encoder | Apache-2.0 (ghi trên model card) | Nền PhoBERT-base-v2, huấn luyện thêm 80% dữ liệu Legal Text Retrieval Zalo 2021; trên 20% còn lại: Acc@10 93,59, MRR@10 80,73 (model card tự báo). **Cần tách từ trước**; PhoBERT tối đa 256 token — Điều dài bị cắt. Nền PhoBERT-base-v2 mang giấy phép **AGPL-3.0** — giấy phép của bản phái sinh cần xem lại |
| truro7/vn-law-embedding | Apache-2.0 | Nền halong_embedding, huấn luyện trên bộ câu hỏi luật Việt Nam; ít người dùng |

**Chốt 23/10/2026:** BGE-M3 (người dùng chọn, không đo so với ứng viên khác). **Bộ đo tạm** `app/answer/search_eval_questions.json`: khoảng 20 câu do Claude soạn theo kiểu câu mẹ hay hỏi, Điều đúng tra trong database, người dùng duyệt — **chỉ để đo**, không bao giờ làm dữ liệu huấn luyện (quy tắc bất biến số 13). Thay bằng câu hỏi thật của mẹ khi có.

**LEGAL-BERT** (Chalkidis và cộng sự, Findings of EMNLP 2020) **không dùng được**: huấn luyện trên 12 GB văn bản luật **tiếng Anh** (EU, Anh, Mỹ). Bản đa ngôn ngữ MultiLegalPile (Niklaus và cộng sự, ACL 2024) gồm 24 ngôn ngữ châu Âu, **không có tiếng Việt**. Đo riêng: chỉ từ khóa, chỉ embedding, kết hợp — để thấy mỗi phần đóng góp gì.

**bkai vietnamese-bi-encoder — đã thử, dừng, không dùng** (23/10/2026): người dùng muốn so với BGE-M3 vì model được đánh giá cao ở luật Việt Nam. Chạy theo cấu hình gốc (tách từ bằng pyvi, mean pooling, tối đa 256 token) trên CPU — GPU đã đủ tải với hai server — sau 45 phút chưa tính xong 16.878 đoạn; người dùng chốt **dùng thẳng BGE-M3**, xoá model bkai. Lý do không quay lại: (1) BGE-M3 đã đạt recall@5 0,90 trên bộ tạm; (2) 256 token ≈ 1.000 ký tự, một nửa số đoạn dài hơn → phần sau của Điều không vào vector; (3) cần torch + pyvi trong app, BGE-M3 chạy được trên `llama-server` có sẵn.

**Làm ở bước:** Tìm kiếm (bước 4) — cũng là cách chọn model embedding.

---

## 4. Hiểu câu hỏi — mốc thời gian (quy tắc), loại thuế và loại câu hỏi (model trên máy, sau thay bằng classifier)

Chốt 18/10/2026: phần lấy thông tin phải đúng và càng tất định càng tốt, không dựa hoàn toàn vào suy đoán của model (quy tắc bất biến số 12 trong `architecture.md`).

### 4a. Mốc thời gian — quy tắc, không dùng model

**Guardrail:** mốc thời gian **luôn hiện** đầu câu trả lời. Không đọc được mốc thì dùng hôm nay và ghi rõ "theo quy định hiện hành". Câu có hai mốc ("so sánh 2025 và 2026") thì trả cả hai, không chọn một.

**Bài đo:** tỷ lệ lấy đúng mốc, so khớp chính xác ngày/năm với nhãn. Mỗi mẫu câu nhận ra được có một test riêng; câu nào trong bộ câu hỏi thật bị đọc sai thì thêm thành test trước khi sửa quy tắc.

### 4b. Loại thuế và loại câu hỏi — model trên máy tạm thời, sau là classifier

**Guardrail:** kết quả phải nằm trong danh sách cố định (danh sách loại thuế: chưa chốt); sai định dạng thì bỏ qua và tìm không ưu tiên loại nào. **Loại thuế chỉ dùng để ưu tiên, không lọc cứng.**

**Bài đo:**
- Loại thuế (một câu có thể thuộc nhiều loại): precision và recall theo từng loại, và tỷ lệ câu có **ít nhất một loại đúng**.
- Loại câu hỏi (tra cứu / vi phạm / so sánh trước–sau / ngoài phạm vi): độ chính xác và bảng nhầm lẫn. Nhầm "vi phạm" thành "tra cứu" là lỗi nặng nhất, vì câu trả lời mất khối nếu–thì; đếm riêng lỗi này.
- Ảnh hưởng tới tìm kiếm: recall@5 **có và không có** ưu tiên theo loại thuế. Ưu tiên mà làm recall@5 giảm thì bỏ.

**Thay bằng classifier** (chốt 18/10/2026). Tạm thời dùng model viết câu trả lời (Qwen) với đầu ra ép theo JSON schema. Mục đích của classifier là **có một bước tất định làm nền cho debug**: cùng câu hỏi + cùng phiên bản model → cùng nhãn, có xác suất để đặt ngưỡng, không cần mạng, tăng tốc được (ONNX Runtime, lượng tử hoá INT8).

Model ứng viên (kiểm trên HuggingFace 18/10/2026):

| Model | Kích thước | Giấy phép | Ghi chú |
|---|---|---|---|
| **mmBERT-small** [mmBERT] | 140M (42M không tính bảng từ) | MIT | **Thử trước.** Kiến trúc ModernBERT, nhanh; 1.800+ ngôn ngữ, có tiếng Việt; nhận chữ thô; 8.192 token. Hơn XLM-R theo model card — trên tiếng Việt chưa kiểm |
| **BamiBERT** [BamiBERT] | ~103M | BSD-3-Clause-Clear **+ Qualcomm responsible AI license** | **Thử trước, sau khi đọc giấy phép thứ hai.** Model tiếng Việt mới nhất (07/2026), nhận chữ thô, 2.048 token; model card tự báo tốt nhất 11/15 chỉ số trên 8 bộ đo tiếng Việt |
| PhoBERT-base (v1) [PhoBERT] | 135M | MIT | **Mốc so.** Bắt buộc tách từ trước bằng VnCoreNLP (cần Java); tối đa 256 token |
| PhoBERT-base-v2 | 135M | **AGPL-3.0** | Không dùng trừ khi chấp nhận AGPL |
| mDeBERTa-v3-base [DeBERTaV3] | 276M (86M thân + 190M bảng từ) | MIT | Mạnh ở phân loại/NLI, có tiếng Việt; chậm hơn |
| XLM-RoBERTa-base | 279M | MIT | Mốc so cổ điển |
| ViDeBERTa | — | không ghi | **Không dùng** — không có giấy phép |

**Mốc so rẻ nhất, phải đo trước:** embedding của model đã chọn ở bước Tìm kiếm (không fine-tune) + logistic regression. Có thể thử thêm SetFit [SetFit] — bài báo báo cáo 8 câu mẫu mỗi lớp đã cạnh tranh được với fine-tune trên cả bộ huấn luyện, nhưng đo trên tiếng Anh, thí nghiệm đa ngôn ngữ không có tiếng Việt → **chưa kiểm**. Model fine-tune nào không vượt mốc này thì không giữ.

**Dữ liệu nhãn** (chỗ khó nhất):
- Trường "lĩnh vực" của cổng Bộ Tư pháp **không dùng làm nhãn được**: đo 18/10/2026 trên 3.160 văn bản, 1.515 (48%) ghi "Chưa phân loại", phần còn lại quá chung ("Quản lý thuế, phí và lệ phí": 895).
- Gom nhãn từ: (1) quy tắc trên tiêu đề văn bản ("thuế giá trị gia tăng" → GTGT); (2) câu hỏi mẫu do **model có giấy phép mở** (Qwen, Apache-2.0) sinh từ từng Điều, mang nhãn của văn bản chứa Điều đó; (3) nhãn mẹ gắn hoặc xác nhận. **Không dùng nhãn hay câu hỏi do Claude sinh** (quy tắc bất biến số 13 — sửa 21/10/2026, trước đó có đề xuất dùng).
- **Bộ đo chỉ gồm câu hỏi thật của mẹ** — câu hỏi sinh ra thường "sạch" hơn câu thật, đo trên đó sẽ ra số đẹp giả.

**Quy trình:** lưu kết quả tạm thời + phản hồi của mẹ → đủ vài trăm câu có nhãn → đo mốc so → fine-tune mmBERT-small và BamiBERT, PhoBERT-base làm mốc → so với cách tạm thời trên cùng bộ đo → ngang hoặc hơn thì thay. Fine-tune trên GPU 6 GB với model cỡ base, câu ngắn, fp16: thường vừa, **chưa đo**.

**Khi chạy:** mỗi câu hỏi ghi tên + phiên bản model, nhãn, xác suất. Xác suất dưới ngưỡng → không ưu tiên loại thuế nào và gắn cờ để xem lại (ngưỡng đặt sau mốc gốc, trên tập kiểm định).

**Hiệu chỉnh xác suất (calibration):** classifier encoder không có bước lấy mẫu — nhãn là giá trị xác suất cao nhất, luôn tất định. Nhưng xác suất của mạng nơ-ron hiện đại thường **quá tự tin** [Guo]. Dùng **temperature scaling**: chia logit cho một hệ số T khớp trên **tập kiểm định** (không đổi nhãn dự đoán, chỉ làm xác suất phản ánh đúng độ tin). Đo bằng **ECE** (expected calibration error) [Guo] trên bộ đo.

**Cách tạm thời (Qwen, ép JSON):** temperature **0** (chốt 22/10/2026) — đầu ra ngắn, bị schema ép, không có rủi ro lặp vô tận; đo 22/10: 3 câu × 3 lần lặp lại giống hệt. Ổn định nhưng **sai có hệ thống** (câu nào cũng ra TNCN/TNDN, bỏ sót hộ kinh doanh, hoá đơn, vi phạm) → bổ sung **quy tắc từ khoá tất định** cho nhãn rõ ràng và loại nhãn trùng bằng code.

Thư viện cần thêm (`transformers`, `torch`, có thể `onnxruntime`) chỉ thêm khi tới bước này, nằm trong nhóm phụ thuộc riêng, và phải được người dùng đồng ý.

**Làm ở bước:** Trả lời (bước 6).

---

### Tách câu hỏi nhiều ý (`split_question.py`)

**Guardrail:** câu tách ra chỉ dùng để tìm, không hiện như dữ kiện; tách hỏng hoặc trả rỗng → tìm bằng cả câu như cũ; câu ngắn một ý không qua model (bộ đo tìm kiếm hiện tại không đổi).

**Bài đo:** chưa có bộ câu hỏi nhiều ý có nhãn. Tạm: với mỗi câu nhiều ý, liệt kê các mảng luật cần có (ví dụ chi phí được trừ, hóa đơn, thanh toán không dùng tiền mặt, khai bổ sung, xử phạt) → tỷ lệ mảng có ít nhất một Điều đúng trong các Điều đưa model, **trước và sau** khi tách. Thay bằng câu hỏi thật của mẹ khi có.

## 5. Xếp lại kết quả — model chạy trên máy (ĐỀ XUẤT: cross-encoder, chọn ở bước Tìm kiếm)

**Guardrail:** xếp lại chỉ đổi thứ tự trong danh sách đã tìm, không thêm văn bản ngoài danh sách.

**Bài đo:** recall@5 và nDCG@10 **trước và sau** khi xếp lại. Xếp lại mà làm rơi Điều đúng khỏi top 5 thì không dùng.

**Khi nào cần:** reranker chỉ đổi thứ tự, không tìm thêm. `measure_search` in thêm recall@20: số câu có Điều đúng trong top 20 nhưng ngoài top 5 là phần reranker có thể cứu. Gần bằng 0 → không thêm (thêm một model, thêm thời gian, không lợi).

**Văn bản bị thay (guardrail):** văn bản cũ bị văn bản mới tuyên bố hết hiệu lực xếp sau mọi văn bản khác và luôn mang nhãn ghi rõ văn bản, khoản tuyên bố — không bao giờ trích mà không có nhãn. **Bài đo:** bài tự kiểm các mẫu câu (`--check`); đọc tay toàn bộ quan hệ tìm được (vài chục) — số hiệu bị thay đúng không, ngày đúng không.

**Kéo Điều được dẫn chiếu (guardrail):** chỉ dẫn chiếu trong cùng văn bản; không đọc dẫn chiếu trong văn bản sửa đổi; Điều thêm đi qua đủ guardrail trích dẫn như Điều tìm được. **Bài đo:** bài tự kiểm các mẫu câu dẫn chiếu (`--check`); tỷ lệ dẫn chiếu tìm được Điều đích trên mẫu ngẫu nhiên.

**Làm ở bước:** Trả lời (bước 6).

---

## 6. Viết câu trả lời — model tự host trên laptop

Đây là công đoạn rủi ro nhất. Nghiên cứu trên các công cụ tra cứu luật thương mại (Lexis+ AI, Westlaw) đo được tỷ lệ ảo giác 17–33% dù chúng đều dùng RAG [Magesh].

### Guardrail khi chạy (tất định, mỗi câu trả lời)

| | Kiểm | Không đạt thì |
|---|---|---|
| a | Mỗi đoạn trích khớp **từng chữ** với một đoạn đã lưu (`chunk_positions`) | Bỏ đoạn trích (đã thiết kế) |
| b | Văn bản/Điều được dẫn phải nằm trong các đoạn đã tìm được cho câu hỏi này | Bỏ trích dẫn đó. Chữ trích khớp nguyên văn **đúng một** đoạn khác trong danh sách (model ghi nhầm số đoạn — gặp khi có 10 đoạn, 23/10/2026) → đổi về đoạn đó; vị trí Điều/khoản lấy theo chỗ khớp |
| c | **Mọi con số** trong câu trả lời (tiền, tỷ lệ, ngày, thời hạn) phải xuất hiện trong đoạn được dẫn. Trừ (chốt 23/10/2026): số đã có trong câu hỏi, năm của mốc thời gian, số nằm trong số hiệu văn bản được dẫn, số của chỗ dẫn ("khoản 1 Điều 9", "19/VBHN-BTC"), số thứ tự đầu dòng ("2026" của "năm 2026" hay của "25/2026/VBHN-BTC" không phải thông tin lấy từ luật). Năm khác vẫn phải có căn cứ — "áp dụng từ năm 2027" khi luật ghi 2026 là lỗi | Gắn cờ "con số chưa có căn cứ", không hiện như căn cứ |
| d | Không có đoạn nào tìm được → trả lời "không có căn cứ trích dẫn" | Không gọi model viết câu trả lời có trích dẫn |
| e | Nhãn hết hiệu lực, công văn, OCR gắn theo dữ liệu, không theo lời model | — |
| f | `llama-server` không trả lời trong thời gian chờ, hoặc hết bộ nhớ GPU | Báo lỗi rõ cho mẹ, không trả câu trả lời dở |
| g | **Mỗi câu trong kết luận phải được căn cứ ủng hộ** (chốt 22/10/2026) — kiểm theo cách AlignScore [AlignScore]: ngữ cảnh = chữ của các khoản chứa trích dẫn đã qua kiểm (a), cắt đoạn ~350 token; mỗi câu kết luận lấy xác suất `entailment` cao nhất trên các đoạn; điểm cả câu trả lời = trung bình. Bắt loại lỗi "suy luận sai" mà (a) không bắt được — ví dụ trích đúng nguyên văn định mức rượu của thuyền viên nhưng kết luận cho hành khách | Gắn cờ câu dưới ngưỡng ("câu chưa được căn cứ ủng hộ"), không xoá câu trả lời. Ngưỡng **tạm 0,5** — đặt lại trên tập kiểm định. **Giới hạn chạy (23/10/2026):** câu trả lời nhiều ý (~20 câu, khoản dài) làm bước này chạy hơn 10 phút trên CPU → mỗi câu chỉ chấm với 3 đoạn ngữ cảnh có nhiều từ chung nhất (lệch khỏi AlignScore — AlignScore chấm mọi đoạn), và dừng sau 60 giây; câu chưa kịp chấm được đếm riêng (`claim_unscored`), không tính vào điểm. Guardrail không bao giờ làm hỏng câu trả lời |

**Model cho guardrail g:** AlignScore chỉ có bản nền RoBERTa **tiếng Anh** (README: "we only provide the metric trained on RoBERTa") → dùng cùng cách làm với model NLI đa ngôn ngữ `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` [mDeBERTa-NLI] (MIT; nhãn theo thứ tự entailment / neutral / contradiction; độ chính xác XNLI tiếng Việt 0,793 theo model card; dữ liệu huấn luyện dịch máy, NLI tổng quát — trên văn bản luật tiếng Việt **chưa đo**). NLI là một trong 7 nhiệm vụ nền của AlignScore. Chạy trên **CPU** — không tranh VRAM với `llama-server`.

**Đo đầu tiên (22/10/2026) — chưa tin được, đang chạy chế độ đo:** câu SAI đối tượng ("hành khách được mua 1,5 lít rượu", ngữ cảnh là khoản 4 về thuyền viên) được **0,780** điểm ủng hộ; câu ĐÚNG trong luồng thật ("hồ sơ khai thuế theo quý … ngày cuối cùng của tháng đầu quý sau", khoản 3 Điều 10 NĐ 252/2026) được **0,806** — hai khoảng điểm chồng nhau, không ngưỡng nào tách được. Khi ngữ cảnh là đúng khoản (khoản 2, hành khách) thì tách rõ: câu đúng 0,969, câu sai ≤ 0,004. Model NLI tổng quát (dịch máy) bỏ qua việc **sai đối tượng** khi số lượng trùng. Vì vậy `NLI_WARNINGS_VISIBLE=false`: luôn chấm và lưu điểm, chưa hiện cảnh báo cho người dùng. Bật khi đã đo trên tập kiểm định có nhãn "câu này được căn cứ ủng hộ không" và có ngưỡng tách được. Hướng thử nếu vẫn chồng điểm: model NLI lớn hơn, hoặc fine-tune NLI trên cặp (khoản, câu) có nhãn của mẹ.
**Tốc độ trên CPU:** nạp model ~9 giây (nạp sẵn lúc khởi động); ~2,3 giây mỗi cặp (câu, đoạn). Hướng tăng tốc chưa đo: ONNX Runtime (repo model có sẵn bản ONNX), hoặc chạy GPU (cần bản torch CUDA, ~0,6 GB VRAM).

### Phân loại lỗi khi câu trả lời sai

Mỗi câu hỏi lưu kết quả trung gian của từng bước (mốc thời gian, nhãn + xác suất, danh sách đoạn tìm được, câu trả lời, kết quả guardrail). Câu trả lời sai thì so từng bước với nhãn, theo thứ tự, và ghi lỗi vào **loại đầu tiên** sai:

| Loại lỗi | Nhận ra bằng | Sửa ở đâu |
|---|---|---|
| **Lấy sai thông tin** | Mốc thời gian / loại thuế / loại câu hỏi khác nhãn | Quy tắc mốc thời gian, classifier |
| **Tìm sai** | Điều đúng không có trong top-5 sau xếp lại | Tìm kiếm, xếp lại |
| **Suy luận sai** | Điều đúng có trong ngữ cảnh, kết luận sai | Prompt, cách đưa ngữ cảnh |
| **Bịa** | Câu trả lời có mệnh đề không có trong ngữ cảnh (faithfulness, hallucination của [RAGChecker]) | Prompt, guardrail |

Báo cáo của mỗi lần đo gồm số câu sai theo từng loại, để biết sửa chỗ nào trước.

### Thông số lấy mẫu khi viết câu trả lời

Chốt 22/10/2026: **temperature 0.4, top_p 0.8, top_k 20, seed cố định, tắt phạt lặp, giới hạn `max_tokens`**.

- Hỏi đáp trên tài liệu, 35 model mở gồm Qwen3 4B/8B, T = 0 / 0.4 / 0.7 / 1.0 [Roig]: T=0 chính xác nhất ở 60% trường hợp nhưng chênh lệch trung vị chỉ ~2 điểm % (ngữ cảnh 32K); T cao hơn giảm bịa ở 53% trường hợp; T=0 tăng mạnh **lặp vô tận** (Llama 3.1 8B, 128K: 14,05% ở T=0 so với 2,05% ở T=1.0). Khuyến nghị: "a moderate temperature (T=0.4 or T=0.7) often provides the best balance".
- Trắc nghiệm, 9 model: T 0.0–1.0 không ảnh hưởng có ý nghĩa thống kê [Renze].
- Bộ đo luật dùng T=0 **để lặp lại được**, không phải vì tối ưu [LegalBench]; model vẫn bịa luật ở T=0 [Dahl]. Chưa tìm thấy nghiên cứu y khoa đo riêng ảnh hưởng của temperature lên trích dẫn.
- `top_p`/`top_k` theo model card Qwen3.5 (chế độ không suy luận). Model card gợi ý thêm `presence_penalty` 1.5 — **không dùng**: phạt lặp có thể đổi chữ trong đoạn trích (suy luận, chưa đo).
- Seed cố định giữ được khả năng lặp lại: đo 22/10, T=0.4 + seed 42 → 3 lần giống hệt; không cố định seed → 3 lần khác nhau (cùng bản dựng, cùng máy, 1 slot).
- **Còn phải đo** trên tập kiểm định: T = 0 / 0.4 / 0.7 × (độ đúng, tỷ lệ trượt guardrail, tỷ lệ bị cắt vì `max_tokens`, tỷ lệ trích khớp từng chữ).

### Bài đo ngoại tuyến

**Chỉ số phụ:** BERTScore [BERTScore] giữa câu trả lời và đáp án mẹ đã duyệt — đo độ giống theo nghĩa. Không thay kiểm con số tất định (embedding của "1,5 lít" và "2,0 lít" có thể rất gần — suy luận, chưa đo). Guardrail g cũng là một chỉ số: tỷ lệ câu kết luận được căn cứ ủng hộ trên bộ đo; cần đo độ khớp giữa guardrail g và nhãn của mẹ trước khi tin.


**Mức mệnh đề — câu trả lời có bám kho dữ liệu không**

| Chỉ số | Cách tính | Nguồn |
|---|---|---|
| **Faithfulness** (bám ngữ cảnh) | Tách câu trả lời thành các mệnh đề ngắn; số mệnh đề được ngữ cảnh đã tìm ủng hộ ÷ tổng số mệnh đề. Trên bộ WikiEval khớp với người 95% | [RAGAS] |
| **Response relevancy** (đúng trọng tâm) | Sinh lại câu hỏi từ câu trả lời, đo độ giống với câu hỏi gốc | [RAGAS] |
| **Context precision / context recall** | Đoạn tìm được có liên quan không / có chứa đủ ý của câu trả lời tham chiếu không. Bài báo RAGAS chỉ có "context relevance"; hai chỉ số này có trong thư viện `ragas` và trong RAGChecker | thư viện `ragas`, [RAGChecker] |
| **Hallucination** | Tỷ lệ mệnh đề **sai** và **không** có trong đoạn nào đã tìm | [RAGChecker] |
| **Noise sensitivity** | Tỷ lệ mệnh đề sai nhưng lấy từ một đoạn đã tìm — model bị đoạn nhiễu dẫn sai | [RAGChecker] |
| **Context utilization** | Trong các ý đúng có sẵn ở đoạn đã tìm, câu trả lời dùng được bao nhiêu | [RAGChecker] |

**Mức trích dẫn**

| Chỉ số | Cách tính | Nguồn |
|---|---|---|
| **Citation recall** | Mỗi câu khẳng định được 1 nếu có trích dẫn **và** các đoạn được dẫn gộp lại ủng hộ đầy đủ câu đó | [ALCE] |
| **Citation precision** | Mỗi trích dẫn được 1 nếu nó thật sự cần để ủng hộ câu — trích dẫn thừa, không liên quan bị trừ | [ALCE] |

**Mức pháp lý — do mẹ chấm** (bảng nhãn của [Magesh])

| Nhãn | Nghĩa |
|---|---|
| **Đúng và có căn cứ** (accurate) | Nội dung đúng, liên quan, và mỗi ý chính dẫn đúng văn bản ủng hộ nó |
| **Ảo giác** (hallucinated) | Nội dung sai, **hoặc** dẫn một văn bản không ủng hộ / không áp dụng được (misgrounded) |
| **Chưa đủ** (incomplete) | Từ chối trả lời, hoặc đúng nhưng không dẫn căn cứ (ungrounded) |

Chỉ số chính cho người dùng đọc: **tỷ lệ ảo giác** trên bộ câu hỏi kiểm tra.

**Dữ liệu đo:** bộ câu hỏi kiểm tra — bắt đầu 20 câu từ câu hỏi thật của mẹ, tăng dần. Mỗi câu có câu trả lời tham chiếu và các Điều đúng, **mẹ duyệt**. Có cả câu mà kho **không** có căn cứ — để đo bot có biết nói "không có căn cứ" không.

**Công cụ**

- **RAGAS** (`ragas`, Apache-2.0, bản 0.4.3): có sẵn faithfulness, response relevancy, context precision/recall, noise sensitivity. Dùng được với Claude làm giám khảo hay không: **chưa kiểm** — tài liệu chính chỉ có ví dụ với OpenAI. Đọc mã nguồn ragas trước khi viết code đo.
- **RAGChecker** (Apache-2.0): có đủ các chỉ số mức mệnh đề ở trên. Lần cập nhật mã nguồn gần nhất: 12/2024 — có thể ít được bảo trì.
- **ALCE** (MIT): chấm citation bằng mô hình NLI TRUE (T5-11B) — quá nặng cho máy này. Dùng **công thức** của ALCE, việc kiểm "đoạn có ủng hộ câu không" giao cho giám khảo AI.
- Prompt của các công cụ này viết cho tiếng Anh; dùng cho câu trả lời tiếng Việt cần thử trước — **chưa kiểm**.
- Cài như nhóm phụ thuộc riêng `[eval]` trong `pyproject.toml`, không lẫn vào app. Thêm khi tới bước Trả lời và người dùng đồng ý.

**Giám khảo:** **Claude** (chốt 21/10/2026), không phải model viết câu trả lời — tránh thiên lệch tự khen [Zheng]. Các câu trong bộ đo được gửi lên API của Anthropic khi chấm. Giám khảo nào cũng phải qua bước hiệu chỉnh với nhãn của mẹ (nguyên tắc 4).

**Làm ở bước:** Trả lời (bước 6). Đo lại mỗi khi đổi prompt, model, cách tìm kiếm.

---

## Tóm tắt theo bước

| Bước trong `ke-hoach.md` | Phải có trước khi "Xong" |
|---|---|
| 2. Lấy văn bản luật về | Báo cáo OCR: CER, WER, CER bỏ dấu, độ chính xác chữ số trên ~20 văn bản |
| 4. Tìm kiếm | Bảng recall@5, MRR@10, nDCG@10 cho từ khóa / embedding / kết hợp |
| 5. Công văn | Bài đo OCR chạy lại trên mẫu công văn scan |
| 6. Trả lời | Test cho từng mẫu câu mốc thời gian; độ chính xác loại thuế, loại câu hỏi và recall@5 có/không ưu tiên loại thuế; báo cáo RAGAS + citation + nhãn của mẹ trên bộ câu hỏi kiểm tra; độ khớp giữa giám khảo và mẹ; kết quả guardrail a–f |

---

## Nguồn

- **[RAGAS]** Shahul Es, Jithin James, Luis Espinosa-Anke, Steven Schockaert. *Ragas: Automated Evaluation of Retrieval Augmented Generation.* arXiv:2309.15217, 2023. https://arxiv.org/abs/2309.15217
- **[ALCE]** Tianyu Gao, Howard Yen, Jiatong Yu, Danqi Chen. *Enabling Large Language Models to Generate Text with Citations.* EMNLP 2023. arXiv:2305.14627. https://arxiv.org/abs/2305.14627
- **[RAGChecker]** Dongyu Ru và cộng sự. *RAGChecker: A Fine-grained Framework for Diagnosing Retrieval-Augmented Generation.* arXiv:2408.08067, 2024. https://arxiv.org/abs/2408.08067
- **[ARES]** Jon Saad-Falcon, Omar Khattab, Christopher Potts, Matei Zaharia. *ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems.* NAACL 2024. arXiv:2311.09476. https://arxiv.org/abs/2311.09476
- **[Magesh]** Varun Magesh, Faiz Surani, Matthew Dahl, Mirac Suzgun, Christopher D. Manning, Daniel E. Ho. *Hallucination-Free? Assessing the Reliability of Leading AI Legal Research Tools.* arXiv:2405.20362, 2024. https://arxiv.org/abs/2405.20362
- **[Zheng]** Lianmin Zheng và cộng sự. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena.* NeurIPS 2023 (Datasets and Benchmarks). arXiv:2306.05685. https://arxiv.org/abs/2306.05685
- **[OHRBench]** Junyuan Zhang và cộng sự. *OCR Hinders RAG: Evaluating the Cascading Impact of OCR on Retrieval-Augmented Generation.* ICCV 2025. arXiv:2412.02592. https://arxiv.org/abs/2412.02592
- **[Neudecker]** Clemens Neudecker và cộng sự. *A survey of OCR evaluation tools and metrics.* HIP '21. https://doi.org/10.1145/3476887.3476888
- **[OCR-D]** Đặc tả đánh giá chất lượng OCR-D. https://ocr-d.de/en/spec/ocrd_eval
- **[BEIR]** Nandan Thakur, Nils Reimers, Andreas Rücklé, Abhishek Srivastava, Iryna Gurevych. *BEIR: A Heterogenous Benchmark for Zero-shot Evaluation of Information Retrieval Models.* NeurIPS 2021 (Datasets and Benchmarks). arXiv:2104.08663. https://arxiv.org/abs/2104.08663
- **[mmBERT]** *mmBERT: a modern multilingual encoder.* arXiv:2509.06888, 2025. https://arxiv.org/abs/2509.06888 — model `jhu-clsp/mmBERT-small`, `jhu-clsp/mmBERT-base`
- **[BamiBERT]** Dat Quoc Nguyen, Thinh Pham, Chi Tran, Linh The Nguyen. arXiv:2607.02259, 2026. https://arxiv.org/abs/2607.02259 — model `Qualcomm-AI-Research/BamiBERT`
- **[PhoBERT]** Dat Quoc Nguyen, Anh Tuan Nguyen. *PhoBERT: Pre-trained language models for Vietnamese.* Findings of EMNLP 2020. — model `vinai/phobert-base`
- **[DeBERTaV3]** Pengcheng He, Jianfeng Gao, Weizhu Chen. *DeBERTaV3: Improving DeBERTa using ELECTRA-Style Pre-Training with Gradient-Disentangled Embedding Sharing.* arXiv:2111.09543. — model `microsoft/mdeberta-v3-base`
- **[AlignScore]** Yuheng Zha, Yichi Yang, Ruichen Li, Zhiting Hu. *AlignScore: Evaluating Factual Consistency with A Unified Alignment Function.* ACL 2023. arXiv:2305.16739. https://github.com/yuh-zha/AlignScore
- **[BERTScore]** Tianyi Zhang, Varsha Kishore, Felix Wu, Kilian Q. Weinberger, Yoav Artzi. *BERTScore: Evaluating Text Generation with BERT.* ICLR 2020. arXiv:1904.09675. https://github.com/Tiiiger/bert_score
- **[mDeBERTa-NLI]** Moritz Laurer. `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (model card, HuggingFace). https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7
- **[Roig]** JV Roig. *How Much Do LLMs Hallucinate in Document Q&A Scenarios? A 172-Billion-Token Study Across Temperatures, Context Lengths, and Hardware Platforms.* arXiv:2603.08274, 2026. https://arxiv.org/abs/2603.08274
- **[Renze]** Matthew Renze. *The Effect of Sampling Temperature on Problem Solving in Large Language Models.* Findings of EMNLP 2024. https://aclanthology.org/2024.findings-emnlp.432/
- **[LegalBench]** Neel Guha và cộng sự. *LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models.* arXiv:2308.11462 (cách đặt temperature: theo kết quả tìm kiếm, chưa đọc toàn văn).
- **[Dahl]** Matthew Dahl, Varun Magesh, Mirac Suzgun, Daniel E. Ho. *Large Legal Fictions: Profiling Legal Hallucinations in Large Language Models.* Journal of Legal Analysis 16(1), 2024. https://doi.org/10.1093/jla/laae003 (theo kết quả tìm kiếm, chưa đọc toàn văn).
- **[Guo]** Chuan Guo, Geoff Pleiss, Yu Sun, Kilian Q. Weinberger. *On Calibration of Modern Neural Networks.* ICML 2017. arXiv:1706.04599. https://arxiv.org/abs/1706.04599
- **[SetFit]** Lewis Tunstall, Nils Reimers, Unso Eun Seo Jo, Luke Bates, Daniel Korat, Moshe Wasserblat, Oren Pereg. *Efficient Few-Shot Learning Without Prompts.* arXiv:2209.11055, 2022. https://arxiv.org/abs/2209.11055
- Tesseract: gói tiếng Việt `vie` trong `tesseract-ocr/tessdata_best` (Apache-2.0); bản cài Windows của UB Mannheim (Apache-2.0).
