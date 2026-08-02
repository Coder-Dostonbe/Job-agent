"""Model javobidan JSON ajratish — model API emas, uning formati kafolatsiz."""
import pytest

from scoring import ai_json


class TestParse:
    def test_plain_json(self):
        assert ai_json.parse('{"score": 80}') == {"score": 80}

    def test_code_fence(self):
        assert ai_json.parse('```json\n{"score": 80}\n```') == {"score": 80}

    def test_text_before(self):
        assert ai_json.parse('Mana javob:\n{"score": 80}') == {"score": 80}

    def test_text_after(self):
        assert ai_json.parse('{"score": 80}\nUmid qilamanki foydali.') == {"score": 80}

    def test_array(self):
        assert ai_json.parse('[{"id": 1}]') == [{"id": 1}]

    def test_braces_inside_a_string_do_not_confuse_the_scanner(self):
        assert ai_json.parse('{"reason": "narx {aniq emas}"}') == {"reason": "narx {aniq emas}"}

    def test_escaped_quotes(self):
        assert ai_json.parse(r'{"reason": "u \"katta\" dedi"}') == {"reason": 'u "katta" dedi'}

    def test_truncated_json_raises(self):
        """Kesilgan javobni tiklab bo'lmaydi — chaqiruvchi buni bilishi kerak."""
        with pytest.raises(ValueError):
            ai_json.parse('{"score": 80, "reason": "yax')

    def test_no_json_at_all_raises(self):
        with pytest.raises(ValueError):
            ai_json.parse("Kechirasiz, javob bera olmayman.")


class TestContentText:
    def test_normal_reply(self):
        payload = {"content": [{"type": "text", "text": "salom"}]}
        assert ai_json.content_text(payload) == "salom"

    def test_multiple_blocks_are_joined(self):
        payload = {"content": [{"text": "a"}, {"text": "b"}]}
        assert ai_json.content_text(payload) == "ab"

    def test_api_error_keeps_its_reason(self):
        """Ilgari bu `KeyError: 'content'` bo'lib chiqar, asl sabab yo'qolardi."""
        payload = {"type": "error", "error": {"message": "overloaded_error"}}
        with pytest.raises(ValueError, match="overloaded_error"):
            ai_json.content_text(payload)

    def test_empty_content(self):
        with pytest.raises(ValueError):
            ai_json.content_text({"content": []})

    def test_truncation_is_named(self):
        payload = {"content": [{"text": '{"score": 8'}], "stop_reason": "max_tokens"}
        with pytest.raises(ValueError, match="max_tokens"):
            ai_json.content_text(payload)

    def test_unexpected_shape(self):
        with pytest.raises(ValueError):
            ai_json.content_text("javob emas")
