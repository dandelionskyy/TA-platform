import asyncio
from io import BytesIO

from pypdf import PdfWriter

from app.core.security import hash_password, verify_password
from app.routers.ws import robot_key_valid
from app.ai.conversation_memory import ConversationMemory
from app.ai.deepseek_client import (
    extract_page_numbers,
    extract_pages_from_marked_text,
    select_relevant_pages,
    parse_guided_response,
    fallback_guided_question,
)
from app.services.material_service import extract_material_text
from app.services import sms_service


def test_passwords_are_not_stored_as_plaintext():
    encoded = hash_password("strong-password")
    assert encoded != "strong-password"
    assert verify_password("strong-password", encoded)
    assert not verify_password("wrong-password", encoded)


def test_on_page_registration_code_is_short_lived_and_single_use(monkeypatch):
    async def no_redis():
        return None

    phone = "13900009999"
    monkeypatch.setattr(sms_service, "_get_redis", no_redis)
    sms_service._sms_store.pop(phone, None)
    code = asyncio.run(sms_service.issue_registration_code(phone))
    assert code is not None and len(code) == 6 and code.isdigit()
    assert asyncio.run(sms_service.verify_sms(phone, code))
    assert not asyncio.run(sms_service.verify_sms(phone, code))


def test_robot_credentials_are_required():
    assert robot_key_valid("TA-Robot-01", "robot-secret-key-change-me")
    assert not robot_key_valid("TA-Robot-01", "wrong")
    assert not robot_key_valid("unknown", "robot-secret-key-change-me")


def test_context_is_bounded():
    memory = ConversationMemory()
    trimmed = memory._trim([
        {"role": "user", "content": "a" * 20000},
        {"role": "assistant", "content": "b" * 20000},
    ])
    assert sum(len(item["content"]) for item in trimmed) <= 24000


def test_page_queries_support_chinese_and_english_ranges():
    assert extract_page_numbers("\u7b2c\u4e94\u9875\u662f\u4ec0\u4e48") == [5]
    assert extract_page_numbers("\u7b2c\u5341\u5230\u5341\u4e8c\u9875\u7684\u8981\u70b9") == [10, 11, 12]
    assert extract_page_numbers("summarize pages 3 to 5") == [3, 4, 5]


def test_explicit_page_query_selects_only_that_page():
    pages = [f"content-{index}" for index in range(1, 7)]
    selected = select_relevant_pages("\u7b2c\u4e94\u9875\u662f\u4ec0\u4e48", pages)
    assert "[Page 5]" in selected
    assert "content-5" in selected
    assert "content-1" not in selected


def test_out_of_range_and_scanned_pages_are_reported():
    out_of_range = select_relevant_pages("page 5", ["one", "two", "three"])
    assert "The PDF has 3 pages" in out_of_range
    scanned = select_relevant_pages("page 2", ["one", ""])
    assert "No extractable text" in scanned


def test_persisted_pdf_text_keeps_page_boundaries():
    marked = "[Page 1]\nfirst\n\n[Page 2]\nsecond"
    assert extract_pages_from_marked_text(marked, 2) == ["first", "second"]


def test_image_only_pdf_is_marked_as_no_text():
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    text, processing_status = extract_material_text(output.getvalue(), ".pdf")
    assert "[Page 1]" in text
    assert processing_status == "no_text"


def test_guided_response_is_parsed_without_leaking_markers():
    raw = (
        "Main answer.\n\n<<<GUIDED_QUESTION>>>\n"
        '{"question":"What should we check next?","options":["Definition","Example","Practice"]}\n'
        "<<<END_GUIDED_QUESTION>>>"
    )
    answer, guide = parse_guided_response(raw)
    assert answer == "Main answer."
    assert guide == {
        "question": "What should we check next?",
        "options": ["Definition", "Example", "Practice"],
    }


def test_structured_guided_response_separates_answer_and_next_question():
    raw = (
        '{"answer_markdown":"**Prediction** increases uncertainty.\\n\\n**Update** reduces it.",'
        '"guided_question":{"question":"Which step uses a measurement?",'
        '"options":["Prediction","Update","Initialization"]}}'
    )
    answer, guide = parse_guided_response(raw)
    assert answer == "**Prediction** increases uncertainty.\n\n**Update** reduces it."
    assert guide == {
        "question": "Which step uses a measurement?",
        "options": ["Prediction", "Update", "Initialization"],
    }


def test_invalid_guided_response_is_removed_from_visible_answer():
    answer, guide = parse_guided_response("Answer\n<<<GUIDED_QUESTION>>>\nnot-json")
    assert answer == "Answer"
    assert guide is None


def test_guided_mode_has_a_language_appropriate_fallback():
    chinese = fallback_guided_question("\u4ec0\u4e48\u662f\u52a8\u91cf\u5b88\u6052？")
    english = fallback_guided_question("What is momentum conservation?")
    assert len(chinese["options"]) == 3
    assert len(english["options"]) == 3
    assert chinese["question"] != english["question"]
    assert fallback_guided_question("Question\n\nMy choice: Example") is None
