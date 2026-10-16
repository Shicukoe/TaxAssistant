# Thứ bậc và thứ tự ưu tiên của văn bản pháp luật

Tài liệu này ghi lại **luật nói gì** về thứ bậc văn bản, cách chọn văn bản khi các quy định mâu thuẫn, và vị trí của công văn. Mọi điểm đều dẫn tới điều luật cụ thể, đọc từ bản gốc trên cổng Bộ Tư pháp ngày 12/10/2026. Phần cuối là **đề xuất** cách áp dụng vào bot — chưa chốt.

---

## Tóm tắt

1. Văn bản quy phạm pháp luật có **15 cấp**, Hiến pháp cao nhất. Trong lĩnh vực thuế, thứ tự thường gặp: Luật / Nghị quyết Quốc hội → Pháp lệnh / Nghị quyết UBTVQH → Nghị định → Quyết định Thủ tướng → Thông tư.
2. Khi hai quy định khác nhau, chọn theo thứ tự: **văn bản có hiệu lực tại thời điểm xảy ra sự việc** → **văn bản có hiệu lực pháp lý cao hơn** → cùng cơ quan ban hành thì **văn bản ban hành sau**.
3. **Công văn không phải văn bản quy phạm pháp luật.** Nó là văn bản hành chính hướng dẫn áp dụng, không được thay đổi quy định hay đặt ra quy định mới. Công văn luôn đứng dưới mọi văn bản quy phạm pháp luật.
4. **Công văn cũ vẫn phải tìm thấy được.** Sự việc xảy ra năm nào thì áp dụng văn bản có hiệu lực năm đó, và cơ quan thuế được truy thu thuế tới 10 năm trước. Hỏi về một kỳ thuế cũ là phải dùng luật cũ và hướng dẫn cũ.
5. **Từ 01/07/2025 quy tắc đã đổi:** khi một văn bản bị thay thế, văn bản hướng dẫn thi hành nó **hết hiệu lực theo**, trừ khi được công bố là còn hiệu lực. Trước đó thì ngược lại.

---

## Nguồn đã đọc

Tất cả lấy từ cổng dữ liệu JSON của Bộ Tư pháp — cùng nguồn với dữ liệu của bot.

| Văn bản | Điều đã đọc | Hiệu lực |
|---|---|---|
| Hiến pháp năm 2013 | Điều 70 khoản 4, Điều 119 | |
| Luật Ban hành văn bản quy phạm pháp luật số 64/2025/QH15 | Điều 2, 4, 5, 8, 53, 55, 57, 58, 60, 61, 65, 66, 71 | từ 01/04/2025 |
| Luật số 87/2025/QH15 sửa đổi Luật 64/2025 | Điều 1, 2, 3 | từ 01/07/2025 |
| Nghị định 78/2025/NĐ-CP hướng dẫn Luật 64/2025 | Điều 7, 63 | |
| Nghị định 30/2020/NĐ-CP về công tác văn thư | Điều 3, 7 | |
| Pháp lệnh Hợp nhất văn bản quy phạm pháp luật (Văn bản hợp nhất số 118/VBHN-VPQH) | Điều 3, 4 | bản sửa đổi từ 01/07/2026 |
| Luật Quản lý thuế số 108/2025/QH15 | Điều 12, 44, 52, 53 | từ 01/07/2026 (một phần từ 01/01/2026) |

---

## 1. Văn bản quy phạm pháp luật là gì

> "Văn bản quy phạm pháp luật là văn bản có chứa quy phạm pháp luật, được ban hành đúng thẩm quyền, hình thức, trình tự, thủ tục theo quy định của Luật này." — Luật 64/2025, Điều 2

Tức là phải đủ hai điều kiện: **có quy phạm** và **đúng loại văn bản, đúng người ban hành**. Tên loại văn bản không quyết định — "Quyết định của Bộ trưởng" không có trong danh sách dưới đây nên không phải văn bản quy phạm pháp luật.

## 2. Thứ bậc: 15 cấp văn bản

Luật 64/2025 Điều 4, **đã được Luật 87/2025 sửa** (bỏ cấp huyện, thêm cấp xã và Chủ tịch UBND tỉnh), hiệu lực từ 01/07/2025:

| Cấp | Văn bản | Ai ban hành | Trong thuế |
|---|---|---|---|
| 1 | Hiến pháp | Quốc hội | Chỉ Quốc hội được "quy định, sửa đổi hoặc bãi bỏ các thứ thuế" (Hiến pháp Điều 70 khoản 4) |
| 2 | Bộ luật, luật; nghị quyết của Quốc hội | Quốc hội | Luật thuế GTGT, TNCN, TNDN, Quản lý thuế 108/2025/QH15… |
| 3 | Pháp lệnh, nghị quyết của UBTVQH; nghị quyết liên tịch của UBTVQH | Ủy ban Thường vụ Quốc hội | Ví dụ: biểu thuế bảo vệ môi trường |
| 4 | Lệnh, quyết định của Chủ tịch nước | Chủ tịch nước | Chủ yếu lệnh công bố luật — không có nội dung thuế |
| 5 | Nghị định, nghị quyết của Chính phủ; nghị quyết liên tịch của Chính phủ | Chính phủ | Nghị định hướng dẫn luật thuế, nghị định xử phạt |
| 6 | Quyết định của Thủ tướng Chính phủ | Thủ tướng | |
| 7 | Nghị quyết của Hội đồng Thẩm phán TAND tối cao | | |
| 8 | Thông tư của Chánh án TANDTC, Viện trưởng VKSNDTC, **Bộ trưởng**, Tổng Kiểm toán nhà nước | | **Thông tư Bộ Tài chính** — nhiều nhất trong kho dữ liệu |
| 9 | Thông tư liên tịch | | Ví dụ: thông tư liên tịch Bộ Tài chính – Bộ Tài nguyên và Môi trường |
| 10 | Nghị quyết HĐND cấp tỉnh | | Ngoài phạm vi (chỉ lấy trung ương) |
| 11 | Quyết định UBND cấp tỉnh | | Ngoài phạm vi |
| 12 | Quyết định Chủ tịch UBND cấp tỉnh | | Ngoài phạm vi |
| 13 | Văn bản của đơn vị hành chính – kinh tế đặc biệt | | Ngoài phạm vi |
| 14 | Nghị quyết HĐND cấp xã | | Ngoài phạm vi |
| 15 | Quyết định UBND cấp xã | | Ngoài phạm vi |

**Lưu ý khi đọc bảng:**
- Hiến pháp "có hiệu lực pháp lý cao nhất" được ghi rõ (Hiến pháp Điều 119). Còn Điều 4 Luật 64 chỉ **liệt kê** hệ thống, không ghi thành câu "theo thứ tự hiệu lực giảm dần". Đọc thứ tự liệt kê như thứ tự hiệu lực là cách hiểu thông dụng; chỗ dễ tranh luận là giữa các văn bản cùng hàng hoặc khác ngành (ví dụ cấp 7 và cấp 8).
- Văn bản của **cấp huyện** (đã bỏ từ 01/07/2025) vẫn còn hiệu lực trong địa giới cũ đến hết 28/02/2027, trừ khi cấp xã ban hành văn bản thay (Luật 87/2025 Điều 3). Không ảnh hưởng bot vì chỉ lấy trung ương.
- Văn bản phải "bảo đảm tính hợp hiến, tính hợp pháp, tính thống nhất … trong hệ thống pháp luật" (Luật 64 Điều 5 khoản 2) — văn bản cấp dưới không được trái văn bản cấp trên.

## 3. Hai quy định khác nhau thì theo cái nào

Luật 64/2025, Điều 58:

| Khoản | Quy tắc | Ý nghĩa cho bot |
|---|---|---|
| 1, 2 | Văn bản "được áp dụng đối với hành vi, sự kiện xảy ra tại thời điểm mà văn bản đó đang có hiệu lực" (trừ khi văn bản quy định hiệu lực trở về trước) | **Lọc theo mốc thời gian trước tiên.** Hỏi về kỳ thuế 2023 thì dùng văn bản có hiệu lực năm 2023 |
| 3 | Các văn bản quy định khác nhau về cùng một vấn đề → "áp dụng văn bản có hiệu lực pháp lý cao hơn" | Luật thắng nghị định, nghị định thắng thông tư |
| 4 | Cùng một cơ quan ban hành, quy định khác nhau → "áp dụng quy định của văn bản … ban hành sau" | Hai thông tư Bộ Tài chính mâu thuẫn → theo thông tư mới hơn |
| 5 | Điều ước quốc tế Việt Nam là thành viên thắng văn bản trong nước (trừ Hiến pháp) | Hiệp định tránh đánh thuế hai lần — ngoài phạm vi hiện tại |
| 6 | Cách áp dụng khác các khoản trên do Quốc hội quy định | |

**Hiệu lực trở về trước** (Điều 55): chỉ khi thật cần thiết, và **không bao giờ** được dùng để đặt trách nhiệm pháp lý mới hoặc nặng hơn cho hành vi đã xảy ra.

**Luật chuyên ngành ưu tiên hơn luật chung** — Điều 58 **không** có quy tắc này. Một số luật tự ghi điều khoản kiểu "trường hợp luật khác có quy định khác thì áp dụng theo luật đó"; phải đọc từng luật, không được suy ra.

## 4. Hiệu lực: khi nào bắt đầu, khi nào hết

- **Bắt đầu** (Điều 53): văn bản trung ương có hiệu lực không sớm hơn 45 ngày kể từ ngày thông qua hoặc ký (trừ thủ tục rút gọn). Văn bản quy định chi tiết phải có hiệu lực cùng lúc với văn bản nó hướng dẫn.
- **Ai được sửa** (Điều 8): văn bản chỉ được sửa đổi, bổ sung, thay thế bằng văn bản **của chính cơ quan đã ban hành** nó. Văn bản sửa phải nêu rõ tên văn bản, phần, chương, mục, tiểu mục, điều, khoản, điểm bị sửa. Sửa quá một nửa số điều thì phải ban hành văn bản thay thế.
- **Hết hiệu lực** (Điều 57 khoản 1): hết thời hạn ghi trong văn bản; bị sửa đổi, bổ sung, thay thế; hoặc bị bãi bỏ.
- **Văn bản hướng dẫn của văn bản bị thay thế** (Điều 57 khoản 2) — **quy tắc đã đảo ngược**:

| Thời điểm văn bản gốc bị thay thế | Văn bản hướng dẫn của nó |
|---|---|
| Từ 01/04/2025 đến 30/06/2025 (Luật 64 bản đầu) | **Tiếp tục có hiệu lực** nếu không trái văn bản mới, trừ khi được công bố hết hiệu lực |
| Từ 01/07/2025 (Luật 87/2025 sửa) | **Hết hiệu lực**, trừ khi được công bố tiếp tục có hiệu lực. Văn bản công bố đăng trên công báo điện tử và cơ sở dữ liệu quốc gia về pháp luật |
| Trước 01/04/2025 (Luật 80/2015) | Chưa kiểm — cần đọc Luật 80/2015 |

Ví dụ trong thuế: Luật Quản lý thuế 108/2025/QH15 có hiệu lực từ 01/07/2026 và thay Luật 38/2019/QH14 (Điều 52). Theo quy tắc mới, các nghị định, thông tư hướng dẫn Luật 38/2019 hết hiệu lực theo, trừ phần được công bố còn hiệu lực. Trạng thái hiệu lực từng văn bản trên cổng Bộ Tư pháp có phản ánh đúng việc này hay không: **chưa kiểm**.

## 5. Văn bản hợp nhất

- Hợp nhất "không được làm thay đổi nội dung và hiệu lực của văn bản được hợp nhất" (Pháp lệnh Hợp nhất, Điều 3 khoản 2). Văn bản hợp nhất **không phải một cấp văn bản mới** — nó mang thứ bậc của văn bản gốc.
- Từ 01/07/2026: "Văn bản hợp nhất được cơ quan, tổ chức, cá nhân sử dụng làm căn cứ chính thức trong viện dẫn và áp dụng pháp luật" (Điều 4 khoản 1, sửa bởi Pháp lệnh 01/2026/UBTVQH16). Quy định trước ngày đó: chưa kiểm.
- **Cách viện dẫn** (Điều 4 khoản 2): ghi tên, số, ký hiệu văn bản gốc kèm "(hợp nhất tại Văn bản hợp nhất số …)", và số Điều/khoản/điểm **theo văn bản hợp nhất**. Bot nên trích dẫn đúng kiểu này.
- Luật 64 Điều 65: văn bản sửa đổi, bổ sung **phải** được hợp nhất.

## 6. Công văn

- **Là văn bản hành chính**, không phải văn bản quy phạm pháp luật. Nghị định 30/2020 Điều 7 liệt kê "công văn" trong các loại văn bản hành chính; Điều 3 khoản 3: văn bản hành chính "hình thành trong quá trình chỉ đạo, điều hành, giải quyết công việc".
- **Vai trò: hướng dẫn áp dụng** (Luật 64 Điều 61). Cơ quan ban hành văn bản quy phạm pháp luật hướng dẫn áp dụng văn bản của mình **bằng văn bản hành chính**; việc hướng dẫn "không được làm thay đổi nội dung quy định được hướng dẫn, không được đặt ra quy định mới", và phải đăng trên cổng thông tin điện tử của cơ quan ban hành. Không ai được "hướng dẫn áp dụng" Hiến pháp, luật, nghị quyết Quốc hội, pháp lệnh — những văn bản đó chỉ được UBTVQH **giải thích** (Điều 60).
- **Công văn không có trạng thái hiệu lực riêng.** Giá trị của nó đi theo văn bản quy phạm pháp luật mà nó hướng dẫn.

**Thông tư mới có "sửa" công văn cũ không?** Về mặt pháp lý thì không: chỉ văn bản quy phạm pháp luật mới bị sửa, bởi chính cơ quan đã ban hành (Điều 8). Điều thực sự xảy ra là:
1. Thông tư mới thay đổi **quy định** mà công văn cũ hướng dẫn → với sự việc xảy ra **sau** ngày thông tư mới có hiệu lực, công văn cũ mất căn cứ.
2. Với sự việc xảy ra **trước** ngày đó, quy định cũ và công văn hướng dẫn nó **vẫn là thứ áp dụng** (Điều 58 khoản 2).
3. Thông tư mới đôi khi đưa thẳng cách hiểu trong công văn cũ thành quy định — hoặc làm ngược lại. Muốn biết là trường hợp nào thì phải **đặt công văn cũ cạnh thông tư mới** để so.

**Vì sao công văn cũ bắt buộc phải tìm thấy được:**
- Cơ quan thuế được truy thu thuế thiếu, thuế trốn, tiền chậm nộp "trong thời hạn 10 năm trở về trước kể từ ngày phát hiện hành vi vi phạm" (Luật Quản lý thuế 108/2025 Điều 44 khoản 8).
- Thời hiệu xử phạt: 02 năm với vi phạm thủ tục thuế; 05 năm với trốn thuế, khai sai dẫn đến thiếu thuế (Điều 44 khoản 7).
- Người nộp thuế được khai bổ sung hồ sơ có sai sót trong 05 năm (Điều 12 khoản 5).
- Chuyển tiếp: khoản thuế được miễn, giảm phát sinh trước 01/07/2026 tiếp tục xử lý theo Luật 38/2019; cuộc kiểm tra quyết định trước ngày đó cũng theo luật cũ (Điều 53).

→ Một khách của mẹ bị kiểm tra năm 2026 về kỳ thuế 2019 thì căn cứ là luật, nghị định, thông tư **và công văn hướng dẫn** có hiệu lực năm 2019.

## 7. Cấu trúc bên trong một văn bản

Nghị định 78/2025 Điều 63:

- Thứ tự chia nhỏ: **Phần → Chương → Mục → Tiểu mục → Điều → Khoản → Điểm**. Cấp nào cũng có thể không có, trừ Điều. Điều đánh số Ả Rập từ "Điều 1".
- Phần, chương, mục, tiểu mục, điều **phải có tên**; khoản và điểm không có tên. Mỗi điểm chỉ một ý.
- Văn bản **ban hành kèm theo** (ví dụ quyết định ban hành kèm quy chế) gồm hai phần: phần văn bản ban hành, và phần văn bản được ban hành kèm theo — phần sau có thể tự chia chương, điều riêng. Đây là lý do số Điều "quay lại từ đầu" mà bộ tách đang xử lý.
- Thứ tự trình bày: quy định chung trước quy định cụ thể; nội dung trước thủ tục; quyền và nghĩa vụ trước chế tài; quy định phổ biến trước ngoại lệ.

Đây là **cách trình bày**, không phải thứ bậc: các Điều trong cùng một văn bản có hiệu lực ngang nhau. Hai Điều trong cùng văn bản mâu thuẫn nhau thì xử lý thế nào — Luật 64 không nói; **chưa kiểm** nguồn khác.

---

## 8. Áp dụng vào bot — ĐỀ XUẤT, chưa chốt

1. **Thứ tự xếp căn cứ** khi trả lời:
   1. Lọc theo mốc thời gian: chỉ văn bản có hiệu lực tại mốc (hoặc gắn nhãn hết hiệu lực).
   2. Xếp theo cấp trong bảng ở mục 2: luật → nghị quyết Quốc hội → pháp lệnh → nghị định → quyết định Thủ tướng → thông tư → **công văn cuối cùng**.
   3. Cùng cơ quan ban hành, cùng vấn đề: văn bản ban hành sau đứng trước.
   4. Văn bản hợp nhất mang cấp của văn bản gốc.

   Cấp tính bằng một biểu thức SQL từ cột `loai` và `doc_group` đã có — không cần thêm cột.

2. **Công văn cũ luôn tìm thấy được**, không bao giờ bị lọc vì "cũ". Mỗi công văn hiện kèm nhãn "hướng dẫn — không phải văn bản quy phạm pháp luật".

3. **Nối công văn với văn bản nó hướng dẫn.** Đọc phần căn cứ và các câu "theo quy định tại … Thông tư số …" trong công văn, ghi vào bảng `document_relations` có sẵn (thêm loại quan hệ `huong_dan`). Khi trả lời: nếu văn bản được hướng dẫn đã hết hiệu lực tại mốc thời gian của câu hỏi, gắn nhãn "văn bản được hướng dẫn đã hết hiệu lực từ ngày …".

4. **Không tự suy hiệu lực văn bản hướng dẫn.** Dùng trạng thái của cổng Bộ Tư pháp. Nếu văn bản gốc bị thay thế từ 01/07/2025 mà văn bản hướng dẫn vẫn ghi "còn hiệu lực", gắn nhãn "cần kiểm hiệu lực" thay vì đoán.

5. **Câu hỏi về kỳ thuế cũ:** lấy năm của kỳ thuế làm mốc thời gian, không lấy năm bị kiểm tra.
