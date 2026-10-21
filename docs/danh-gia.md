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
- **Còn thiếu:** bài đo cho phần cắt theo đề mục (văn bản không có Điều) — làm cùng lúc viết phần đó.

---

## 3. Tìm kiếm — embedding + từ khóa

**Guardrail:** luôn kết hợp tìm theo nghĩa với tìm theo từ khóa — không để embedding là đường duy nhất.

**Bài đo**

| Chỉ số | Cách tính | Nguồn |
|---|---|---|
| **recall@5** | Tỷ lệ câu hỏi có Điều đúng nằm trong 5 kết quả đầu | Chỉ số tìm kiếm chuẩn |
| **MRR@10** | Trung bình của 1 ÷ (thứ hạng của Điều đúng đầu tiên), tính trong 10 kết quả đầu | Chỉ số tìm kiếm chuẩn |
| **nDCG@10** | Tính cả thứ hạng lẫn mức độ liên quan có cấp bậc | BEIR chọn làm chỉ số chính vì "cân bằng tốt cho cả đánh giá liên quan nhị phân lẫn có cấp bậc", còn precision/recall không tính thứ hạng [BEIR] |

**Dữ liệu đo:** câu hỏi thật của mẹ, mỗi câu gắn nhãn các Điều đúng (Điều chính = mức 2, Điều liên quan = mức 1 cho nDCG). Đo riêng: chỉ từ khóa, chỉ embedding, kết hợp — để thấy mỗi phần đóng góp gì.

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

**Khi chạy:** mỗi câu hỏi ghi tên + phiên bản model, nhãn, xác suất. Xác suất dưới ngưỡng → không ưu tiên loại thuế nào và gắn cờ để xem lại (ngưỡng đặt sau mốc gốc).

Thư viện cần thêm (`transformers`, `torch`, có thể `onnxruntime`) chỉ thêm khi tới bước này, nằm trong nhóm phụ thuộc riêng, và phải được người dùng đồng ý.

**Làm ở bước:** Trả lời (bước 6).

---

## 5. Xếp lại kết quả — model chạy trên máy (ĐỀ XUẤT: cross-encoder, chọn ở bước Tìm kiếm)

**Guardrail:** xếp lại chỉ đổi thứ tự trong danh sách đã tìm, không thêm văn bản ngoài danh sách.

**Bài đo:** recall@5 và nDCG@10 **trước và sau** khi xếp lại. Xếp lại mà làm rơi Điều đúng khỏi top 5 thì không dùng.

**Làm ở bước:** Trả lời (bước 6).

---

## 6. Viết câu trả lời — model tự host trên laptop

Đây là công đoạn rủi ro nhất. Nghiên cứu trên các công cụ tra cứu luật thương mại (Lexis+ AI, Westlaw) đo được tỷ lệ ảo giác 17–33% dù chúng đều dùng RAG [Magesh].

### Guardrail khi chạy (tất định, mỗi câu trả lời)

| | Kiểm | Không đạt thì |
|---|---|---|
| a | Mỗi đoạn trích khớp **từng chữ** với một đoạn đã lưu (`chunk_positions`) | Bỏ đoạn trích (đã thiết kế) |
| b | Văn bản/Điều được dẫn phải nằm trong các đoạn đã tìm được cho câu hỏi này | Bỏ trích dẫn đó |
| c | **Mọi con số** trong câu trả lời (tiền, tỷ lệ, ngày, thời hạn) phải xuất hiện trong đoạn được dẫn | Gắn cờ "con số chưa có căn cứ", không hiện như căn cứ |
| d | Không có đoạn nào tìm được → trả lời "không có căn cứ trích dẫn" | Không gọi model viết câu trả lời có trích dẫn |
| e | Nhãn hết hiệu lực, công văn, OCR gắn theo dữ liệu, không theo lời model | — |
| f | `llama-server` không trả lời trong thời gian chờ, hoặc hết bộ nhớ GPU | Báo lỗi rõ cho mẹ, không trả câu trả lời dở |

### Phân loại lỗi khi câu trả lời sai

Mỗi câu hỏi lưu kết quả trung gian của từng bước (mốc thời gian, nhãn + xác suất, danh sách đoạn tìm được, câu trả lời, kết quả guardrail). Câu trả lời sai thì so từng bước với nhãn, theo thứ tự, và ghi lỗi vào **loại đầu tiên** sai:

| Loại lỗi | Nhận ra bằng | Sửa ở đâu |
|---|---|---|
| **Lấy sai thông tin** | Mốc thời gian / loại thuế / loại câu hỏi khác nhãn | Quy tắc mốc thời gian, classifier |
| **Tìm sai** | Điều đúng không có trong top-5 sau xếp lại | Tìm kiếm, xếp lại |
| **Suy luận sai** | Điều đúng có trong ngữ cảnh, kết luận sai | Prompt, cách đưa ngữ cảnh |
| **Bịa** | Câu trả lời có mệnh đề không có trong ngữ cảnh (faithfulness, hallucination của [RAGChecker]) | Prompt, guardrail |

Báo cáo của mỗi lần đo gồm số câu sai theo từng loại, để biết sửa chỗ nào trước.

### Bài đo ngoại tuyến

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
- **[SetFit]** Lewis Tunstall, Nils Reimers, Unso Eun Seo Jo, Luke Bates, Daniel Korat, Moshe Wasserblat, Oren Pereg. *Efficient Few-Shot Learning Without Prompts.* arXiv:2209.11055, 2022. https://arxiv.org/abs/2209.11055
- Tesseract: gói tiếng Việt `vie` trong `tesseract-ocr/tessdata_best` (Apache-2.0); bản cài Windows của UB Mannheim (Apache-2.0).
