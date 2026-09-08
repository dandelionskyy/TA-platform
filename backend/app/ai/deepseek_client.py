# Ported and enhanced from the original AI Chatbot (g:\Desktop\Uni\2025启航计划\AI Chatbot\deepseek_client.py)
import base64
import io
import json
import os
import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from openai import OpenAI
from PyPDF2 import PdfReader
from pptx import Presentation
from docx import Document
from app.core.config import get_settings

settings = get_settings()

client = OpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_API_BASE,
)

# ==================== File Parsers ====================

def extract_text_from_pdf(pdf_data: bytes) -> str:
    text = ""
    with io.BytesIO(pdf_data) as f:
        reader = PdfReader(f)
        for page in reader.pages:
            text += page.extract_text() or ""
    return text


def extract_text_from_pptx(pptx_data: bytes) -> str:
    text = ""
    with io.BytesIO(pptx_data) as f:
        prs = Presentation(f)
        for slide in prs.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    text += shape.text + "\n"
    return text


def extract_text_from_docx(docx_data: bytes) -> str:
    text = ""
    with io.BytesIO(docx_data) as f:
        doc = Document(f)
        for para in doc.paragraphs:
            text += para.text + "\n"
    return text


# ==================== PDF Page Cache ====================

pdf_page_cache: Dict[str, List[str]] = {}
pdf_metadata_cache: Dict[str, Dict] = {}


def extract_pdf_by_page(pdf_data: bytes) -> List[str]:
    pages = []
    with io.BytesIO(pdf_data) as f:
        reader = PdfReader(f)
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            pages.append(page_text)
    return pages


def get_cached_pdf_pages(course_name: str, chapter_index: int) -> Optional[List[str]]:
    cache_key = f"{course_name}-ch{chapter_index}"
    return pdf_page_cache.get(cache_key)


def cache_pdf_pages(course_name: str, chapter_index: int, pages: List[str]):
    cache_key = f"{course_name}-ch{chapter_index}"
    pdf_page_cache[cache_key] = pages
    pdf_metadata_cache[cache_key] = {
        "total_pages": len(pages),
        "cached_at": datetime.now().isoformat(),
    }


_PAGE_NUMBER_TOKEN = r"[0-9\u96f6\u3007\u4e00\u4e8c\u4e24\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343]+"
_CHINESE_DIGITS = {
    "\u96f6": 0, "\u3007": 0, "\u4e00": 1, "\u4e8c": 2, "\u4e24": 2,
    "\u4e09": 3, "\u56db": 4, "\u4e94": 5, "\u516d": 6, "\u4e03": 7,
    "\u516b": 8, "\u4e5d": 9,
}
_CHINESE_UNITS = {"\u5341": 10, "\u767e": 100, "\u5343": 1000}


def _parse_page_number(value: str) -> Optional[int]:
    value = value.strip()
    if value.isdigit():
        return int(value)
    if not value or any(char not in _CHINESE_DIGITS and char not in _CHINESE_UNITS for char in value):
        return None
    if not any(char in _CHINESE_UNITS for char in value):
        return int("".join(str(_CHINESE_DIGITS[char]) for char in value))

    total = 0
    current = 0
    for char in value:
        if char in _CHINESE_DIGITS:
            current = _CHINESE_DIGITS[char]
        else:
            total += (current or 1) * _CHINESE_UNITS[char]
            current = 0
    return total + current


def extract_page_numbers(question: str) -> List[int]:
    page_numbers: set[int] = set()
    range_patterns = [
        rf"(?:\u7b2c\s*)?({_PAGE_NUMBER_TOKEN})\s*(?:-|~|\u81f3|\u5230)\s*(?:\u7b2c\s*)?({_PAGE_NUMBER_TOKEN})\s*\u9875",
        r"pages?\s*(\d+)\s*(?:-|~|to)\s*(\d+)",
    ]
    single_patterns = [
        rf"(?:\u7b2c\s*)?({_PAGE_NUMBER_TOKEN})\s*\u9875",
        r"page\s*(\d+)",
    ]

    for pattern in range_patterns:
        for match in re.finditer(pattern, question, re.IGNORECASE):
            start = _parse_page_number(match.group(1))
            end = _parse_page_number(match.group(2))
            if start is not None and end is not None and 0 < start <= end and end - start <= 50:
                page_numbers.update(range(start, end + 1))
    for pattern in single_patterns:
        for match in re.finditer(pattern, question, re.IGNORECASE):
            page_number = _parse_page_number(match.group(1))
            if page_number and page_number > 0:
                page_numbers.add(page_number)
    return sorted(page_numbers)


def _format_pdf_page(page_number: int, content: str) -> str:
    content = content.strip()
    if not content:
        content = "[No extractable text was found on this page. It may be scanned or image-only.]"
    return f"[Page {page_number}]\n{content}"


def extract_pages_from_marked_text(text: str, page_count: Optional[int] = None) -> List[str]:
    marker = re.compile(r"(?m)^\[Page\s+(\d+)\]\s*$")
    matches = list(marker.finditer(text or ""))
    if not matches:
        return [text] if text else ([""] * page_count if page_count else [])
    total_pages = page_count or max(int(match.group(1)) for match in matches)
    pages = [""] * total_pages
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        if 1 <= page_number <= total_pages:
            pages[page_number - 1] = text[match.end():end].strip()
    return pages


def select_relevant_pages(question: str, all_pages: List[str], include_page_numbers: bool = True) -> str:
    page_numbers = extract_page_numbers(question)
    if page_numbers:
        selected_pages = []
        for page_num in page_numbers:
            if 1 <= page_num <= len(all_pages):
                selected_pages.append(
                    _format_pdf_page(page_num, all_pages[page_num - 1])
                    if include_page_numbers else all_pages[page_num - 1]
                )
        if selected_pages:
            return "\n\n".join(selected_pages)
        requested = ", ".join(str(page_number) for page_number in page_numbers)
        return f"[Document metadata]\nThe PDF has {len(all_pages)} pages. Requested page(s): {requested}."

    important_keywords = [
        '概念', '定义', '公式', '定理', '原理', '性质', '特点', '特征',
        '例子', '示例', '例题', '应用', '用途', '方法', '步骤', '流程',
        '总结', '小结', '要点', '重点', '难点', '关键', '结论',
        'concept', 'definition', 'formula', 'theorem', 'principle', 'property',
        'characteristic', 'feature', 'example', 'sample', 'application', 'use',
        'method', 'step', 'procedure', 'process', 'summary', 'key point',
        'conclusion', 'important', 'critical',
    ]

    relevant_pages = []
    for i, page_content in enumerate(all_pages):
        page_lower = page_content.lower()
        for keyword in important_keywords:
            if keyword.lower() in question.lower() and keyword.lower() in page_lower:
                if include_page_numbers:
                    relevant_pages.append(_format_pdf_page(i + 1, page_content))
                else:
                    relevant_pages.append(page_content)
                break
        if len(relevant_pages) >= 3:
            break

    if relevant_pages:
        return "\n\n".join(relevant_pages)

    default_pages = all_pages[:3]
    if include_page_numbers:
        return "\n\n".join(_format_pdf_page(i + 1, content) for i, content in enumerate(default_pages))
    return "\n\n".join(default_pages)


# ==================== System Prompts ====================

SYSTEM_PROMPTS = {
    "chatbot": "You are a general-purpose chatbot, friendly and helpful. Please use Markdown for formatting. Default to responding in English unless specifically asked to use another language.",
    "physics": "You are an expert physicist and educator. Answer clearly, use Markdown, LaTeX for formulas.",
    "math": "You are a patient math tutor. Help users step-by-step using Markdown and LaTeX.",
    "circuit": "You are an experienced circuit engineer. Answer with professional terminology using Markdown and LaTeX.",
}

VOICE_SYSTEM_PROMPT = (
    "You are a conversational voice assistant. Reply in natural, colloquial language suitable for speech. "
    "Do NOT use Markdown, headings, lists, code blocks, inline code markers, or raw URLs. "
    "Avoid special symbols like '#', '*', '`'. Keep answers concise and well-structured as plain sentences. "
    "If the user asked in Chinese, reply in Chinese; if in English, reply in English."
)

RESPONSE_STYLE_PROMPT = (
    "Format the answer as readable Markdown with short paragraphs separated by blank lines. "
    "Use descriptive headings only when they improve scanning, and use lists for parallel points or steps. "
    "Bold only key concepts, conclusions, and short labels; never bold an entire paragraph. "
    "Write math only as valid LaTeX using $...$ or $$...$$. "
    "Never output HTML tags, HTML entities, or escaped HTML. "
    "Do not append follow-up questions, option menus, or next-step suggestions to the answer."
)

GUIDED_MODE_PROMPT = (
    "Return only one valid JSON object with this exact shape: "
    '{"answer_markdown":"the complete Markdown answer","guided_question":{"question":"one concrete question",'
    '"options":["answer 1","answer 2","answer 3"]}}. '
    "The guided question must use the user's language and test or advance the exact concept in answer_markdown. "
    "Provide 2 to 4 concise, plausible choices. Never ask which learning direction the student wants, "
    "never provide a generic explain/example/practice menu, and never repeat a question or choices from any earlier conversation message. "
    "If the student is a beginner or says they do not understand, ask an easy concrete comprehension question. "
    "If the student requests an exercise, ask the actual exercise now. Do not wrap the JSON in a code fence."
)


def parse_guided_response(content: str) -> tuple[str, Optional[Dict[str, object]]]:
    cleaned_content = content.strip()
    if cleaned_content.startswith("```"):
        cleaned_content = re.sub(r"^```(?:json)?\s*", "", cleaned_content, flags=re.IGNORECASE)
        cleaned_content = re.sub(r"\s*```$", "", cleaned_content)
    try:
        payload = json.loads(cleaned_content)
    except (json.JSONDecodeError, TypeError):
        payload = None
    if isinstance(payload, dict) and isinstance(payload.get("answer_markdown"), str):
        answer = payload["answer_markdown"].strip()
        guide_payload = payload.get("guided_question")
        if isinstance(guide_payload, dict):
            guide = _normalize_guided_question(guide_payload)
            return answer, guide
        return answer, None

    # Backward compatibility for responses generated by the earlier marker prompt.
    start_marker = "<<<GUIDED_QUESTION>>>"
    end_marker = "<<<END_GUIDED_QUESTION>>>"
    pattern = re.compile(
        rf"{re.escape(start_marker)}\s*(.*?)\s*{re.escape(end_marker)}",
        re.DOTALL,
    )
    match = pattern.search(content)
    if not match:
        clean = content.split(start_marker, 1)[0].strip() if start_marker in content else content.strip()
        return clean, None

    clean = (content[:match.start()] + content[match.end():]).strip()
    try:
        payload = json.loads(match.group(1))
    except (json.JSONDecodeError, TypeError):
        return clean, None

    return clean, _normalize_guided_question(payload)


def _normalize_guided_question(payload: object) -> Optional[Dict[str, object]]:
    question = payload.get("question") if isinstance(payload, dict) else None
    raw_options = payload.get("options") if isinstance(payload, dict) else None
    if not isinstance(question, str) or not isinstance(raw_options, list):
        return None

    question = question.strip()[:300]
    options = []
    for option in raw_options:
        if isinstance(option, str) and option.strip():
            value = option.strip()[:160]
            if value not in options:
                options.append(value)
                if len(options) == 4:
                    break
    if not question or len(options) < 2:
        return None
    return {"question": question, "options": options}


def fallback_guided_question(user_question: str) -> Optional[Dict[str, object]]:
    if "\u6211\u7684\u9009\u62e9\uff1a" in user_question or "My choice:" in user_question:
        return None
    if re.search(r"[\u4e00-\u9fff]", user_question):
        return {
            "question": "接下来你想怎样继续学习这个内容？",
            "options": ["进一步解释核心概念", "展示一个具体例子", "给我一道练习题"],
        }
    return {
        "question": "How would you like to continue learning this topic?",
        "options": ["Explain the core idea further", "Show a concrete example", "Give me a practice question"],
    }


# ==================== AI Response ====================

async def get_deepseek_response(
    user_question: str,
    mode: str = "chatbot",
    file_data: Optional[bytes] = None,
    filename: Optional[str] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    reference_context: Optional[str] = None,
    reference_name: Optional[str] = None,
    persisted_file_context: Optional[str] = None,
    persisted_filename: Optional[str] = None,
    persisted_page_count: Optional[int] = None,
    guided_mode: bool = False,
) -> Dict:
    """
    Returns dict with keys: response (str), context_source (str), filename_display (str)
    """
    if not settings.DEEPSEEK_API_KEY:
        return {"response": "Error: DeepSeek API key is not configured.", "context_source": "none", "filename_display": "", "guided_question": None}

    try:
        messages = []
        model_name = settings.DEEPSEEK_MODEL_NAME
        file_context = ""
        context_source = "none"
        filename_display = ""
        course_name = ""
        chapter_index = -1

        # --------- File Upload ---------
        if file_data and filename:
            is_image = filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp'))
            if is_image:
                model_name = "deepseek-vl-chat"
                base64_image = base64.b64encode(file_data).decode('utf-8')
                messages = [{"role": "user", "content": [
                    {"type": "text", "text": user_question or "Please describe this image"},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]}]
            else:
                if filename.lower().endswith('.pdf'):
                    pages = extract_pdf_by_page(file_data)
                    file_context = select_relevant_pages(user_question, pages, include_page_numbers=True)
                elif filename.lower().endswith('.pptx'):
                    file_context = extract_text_from_pptx(file_data)
                elif filename.lower().endswith('.docx'):
                    file_context = extract_text_from_docx(file_data)
                else:
                    return {"response": f"Unsupported file type: '{filename}'", "context_source": "none", "filename_display": ""}
                context_source = "manual_file"
                filename_display = filename

        # --------- Conversation File ---------
        elif persisted_filename and persisted_file_context is not None:
            if persisted_filename.lower().endswith('.pdf'):
                pages = extract_pages_from_marked_text(persisted_file_context, persisted_page_count)
                file_context = select_relevant_pages(user_question, pages, include_page_numbers=True)
            else:
                file_context = persisted_file_context.strip()
                if not file_context:
                    file_context = (
                        "[Document status]\nNo extractable text was found in this file. "
                        "It may be scanned, image-only, or unsupported for text extraction."
                    )
            context_source = "manual_file"
            filename_display = persisted_filename

        # --------- Managed Course Material ---------
        elif reference_context:
            file_context = reference_context
            context_source = "course_material"
            filename_display = reference_name or "Course chapter materials"

        # --------- Legacy Chapter Mode ---------
        elif '-ch' in mode:
            try:
                course_name_slug, chapter_index_str = mode.split('-ch')
                course_name = course_name_slug.replace('-', ' ')
                chapter_index = int(chapter_index_str)

                script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                base_path = os.path.join(script_dir, "knowledge_base", course_name)
                txt_path = os.path.join(base_path, f"chapter_{chapter_index + 1}.txt")
                pdf_path = os.path.join(base_path, f"chapter_{chapter_index + 1}.pdf")

                if os.path.exists(txt_path):
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        file_context = f.read()
                    context_source = "txt"
                    filename_display = f"Chapter {chapter_index + 1} Knowledge Base"
                elif os.path.exists(pdf_path):
                    cached_pages = get_cached_pdf_pages(course_name, chapter_index)
                    if cached_pages is None:
                        with open(pdf_path, 'rb') as f:
                            pdf_bytes = f.read()
                            pages = extract_pdf_by_page(pdf_bytes)
                            cache_pdf_pages(course_name, chapter_index, pages)
                    else:
                        pages = cached_pages
                    file_context = select_relevant_pages(user_question, pages, include_page_numbers=True)
                    context_source = "pdf"
                    filename_display = f"Chapter {chapter_index + 1} PDF"
                else:
                    file_context = ""
                    context_source = "none"
            except (ValueError, IndexError):
                file_context = ""
                context_source = "none"

        # --------- Build System Prompt ---------
        if file_context:
            file_context = file_context[:settings.MAX_CONTEXT_CHARS]
            page_query_hint = ""
            if extract_page_numbers(user_question):
                page_query_hint = "\nThe user mentioned a page number. Use matching [Page X] context when available."
            system_prompt = (
                "You are a careful university teaching assistant. Answer primarily from the supplied course material. "
                "If the material does not contain the answer, clearly say that first, then provide a concise general explanation. "
                "Do not invent quotations, page numbers, formulas, or conclusions that are absent from the material. "
                f"{page_query_hint}\nRespond in the same language as the user."
            )
            combined_input = (
                f"**Course context ({filename_display}):**\n---\n{file_context}\n---\n\n"
                f"**User question:**\n{user_question}"
            )
        else:
            system_prompt = SYSTEM_PROMPTS.get(mode, SYSTEM_PROMPTS["chatbot"])
            combined_input = user_question

        if mode == 'voice_chat' or mode.startswith('voice'):
            if system_prompt:
                system_prompt = system_prompt + "\n\n" + VOICE_SYSTEM_PROMPT
            else:
                system_prompt = VOICE_SYSTEM_PROMPT

        if not (mode == 'voice_chat' or mode.startswith('voice')):
            system_prompt = system_prompt + "\n\n" + RESPONSE_STYLE_PROMPT

        if guided_mode and not (mode == 'voice_chat' or mode.startswith('voice')):
            system_prompt = system_prompt + "\n\n" + GUIDED_MODE_PROMPT

        # --------- Build Messages ---------
        if not messages:
            messages = [{"role": "system", "content": system_prompt}]
            if conversation_history and len(conversation_history) > 0:
                for msg in conversation_history:
                    if msg.get("role") in ["user", "assistant"]:
                        messages.append({"role": msg["role"], "content": msg["content"]})
            messages.append({"role": "user", "content": combined_input})
        elif messages:
            messages.insert(0, {"role": "system", "content": system_prompt})

        # --------- Call API ---------
        request_options = {"model": model_name, "messages": messages, "stream": False}
        if guided_mode and not (mode == 'voice_chat' or mode.startswith('voice')):
            request_options["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**request_options)
        raw_response = response.choices[0].message.content.strip()
        ai_response, guided_question = parse_guided_response(raw_response) if guided_mode else (raw_response, None)
        if guided_mode and guided_question is None:
            guided_question = fallback_guided_question(user_question)

        return {
            "response": ai_response,
            "context_source": context_source,
            "filename_display": filename_display,
            "guided_question": guided_question,
        }

    except Exception as e:
        print(f"DeepSeek request failed: {type(e).__name__}: {e}")
        return {
            "response": "The assistant is temporarily unavailable. Please try again in a moment.",
            "context_source": "none",
            "filename_display": "",
            "guided_question": None,
        }
