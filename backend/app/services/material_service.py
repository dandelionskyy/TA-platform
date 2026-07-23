from app.ai.deepseek_client import (
    extract_pdf_by_page,
    extract_text_from_docx,
    extract_text_from_pptx,
)


def extract_material_text(data: bytes, extension: str) -> tuple[str, str]:
    """Extract searchable text while keeping the original file for preview/download."""
    try:
        if extension == ".pdf":
            pages = extract_pdf_by_page(data)
            text = "\n\n".join(f"[Page {index + 1}]\n{content}" for index, content in enumerate(pages))
        elif extension == ".pptx":
            text = extract_text_from_pptx(data)
        elif extension == ".docx":
            text = extract_text_from_docx(data)
        elif extension in {".txt", ".md"}:
            text = data.decode("utf-8", errors="replace")
        elif extension in {".png", ".jpg", ".jpeg", ".webp"}:
            return "", "image"
        else:
            return "", "unsupported"
        return text[:500000], "processed" if text.strip() else "no_text"
    except Exception:
        return "", "failed"
