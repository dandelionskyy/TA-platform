"""Dedicated pypdf worker. Run only through pdf_extraction.extract_pdf_pages.

Resource ceilings limit costly document parsing; they are not a filesystem
security sandbox. stderr contains no uploaded text and is discarded by caller.
"""

import io
import json
import sys

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_TEXT_CHARS = 8_000_000
MAX_PAGES = 10_000


def _set_resource_limits() -> None:
    try:
        import resource
    except ImportError:  # Windows retains the parent-enforced wall timeout.
        return
    # Apply inside the newly started interpreter: preexec_fn is unsafe when
    # the server is multithreaded. Linux workers enforce both memory and CPU.
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (45, 46))


def main() -> int:
    _set_resource_limits()
    from pypdf import PdfReader

    data = sys.stdin.buffer.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        return 1
    try:
        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > MAX_PAGES:
            return 1
        pages: list[str] = []
        chars = 0
        for page in reader.pages:
            text = page.extract_text() or ""
            chars += len(text)
            if chars > MAX_TEXT_CHARS:
                return 1
            pages.append(text)
        sys.stdout.buffer.write(json.dumps(pages, ensure_ascii=False).encode("utf-8"))
        return 0
    except Exception:
        # Do not propagate PDF content or parser details through the API.
        return 1


if __name__ == "__main__":
    sys.exit(main())
