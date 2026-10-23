-- Kết luận của câu trả lời (draft.ket_luan) tách riêng khỏi answers.text (bản chữ đầy đủ cho terminal):
-- web mở lại cuộc hội thoại cũ dựng lại đúng khung (kết luận + căn cứ + nhãn) từ bản ghi chính thức, không từ
-- checkpoint (docs/architecture.md, Quy tắc dùng LangGraph). Câu trả lời cũ để trống → web hiện answers.text.
ALTER TABLE answers ADD COLUMN ket_luan text;
