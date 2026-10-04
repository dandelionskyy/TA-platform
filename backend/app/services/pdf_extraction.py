"""Bounded PDF text extraction shared by BRIDGE and legacy course materials.

The parser receives the uploaded bytes via stdin and runs in a separate Python
process, so a malformed PDF cannot pin an application thread indefinitely.
"""

import json
import subprocess
import sys
from pathlib import Path

MAX_PDF_BYTES = 50 * 1024 * 1024
PDF_TIMEOUT_SECONDS = 70
_WORKER = Path(__file__).with_name("pdf_text_worker.py")


def extract_pdf_pages(data: bytes) -> list[str]:
    """Return one string per PDF page; raise ValueError on bounded failures."""
    if len(data) > MAX_PDF_BYTES:
        raise ValueError("PDF exceeds the 50 MB extraction limit")
    try:
        result = subprocess.run(
            [sys.executable, "-I", str(_WORKER)],
            input=data,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=PDF_TIMEOUT_SECONDS,
            check=False,
            env={"PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as exc:
        # subprocess.run kills and reaps the timed-out process before raising.
        raise ValueError("PDF extraction timed out") from exc
    except OSError as exc:
        raise ValueError("PDF extraction process is unavailable") from exc
    if result.returncode != 0:
        raise ValueError("Could not extract PDF text")
    try:
        pages = json.loads(result.stdout)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Could not extract PDF text") from exc
    if not isinstance(pages, list) or any(not isinstance(page, str) for page in pages):
        raise ValueError("Could not extract PDF text")
    return pages
