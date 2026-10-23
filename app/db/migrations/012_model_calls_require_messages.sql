-- model_calls.request phải có ô messages là mảng. Ràng buộc của migration 011 cho qua request không có ô này:
-- request -> 'messages' ra NULL, jsonb_typeof(NULL) ra NULL, và CHECK coi NULL là đạt.
ALTER TABLE model_calls DROP CONSTRAINT model_calls_request_check;
ALTER TABLE model_calls ADD CONSTRAINT model_calls_request_check
    CHECK (request ? 'messages' AND jsonb_typeof(request -> 'messages') = 'array');
