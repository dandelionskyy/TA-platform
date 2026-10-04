"""Conservative, deterministic BRIDGE output and assessment safeguards.

Retrieved teaching files and student messages are untrusted. A generated model
completion is never allowed to set the dialogue stage, module, source list or
assessment lock. In all scaffold stages we use server-authored wording, even
when an optional local model is configured.
"""

import re


_ASSESSMENT = re.compile(
    r"\b(?:exam|test|quiz|graded|assessment|assignment|homework|marking|deadline|"
    r"take[- ]home|submit|coursework|past paper|midterm|final paper|"
    r"for marks|for credit|timed paper|set task)\b|考试|测验|作业|考核|提交|评分|计分|试卷|期末|期中",
    re.IGNORECASE,
)
_AMBIGUOUS_ASSESSMENT = re.compile(
    r"\b(?:due tomorrow|hand in|hand this in|teacher asked|tutor asked|"
    r"model answer|mark scheme|my deadline|this paper|right now for class)\b|"
    r"要交|截止|标准答案|老师让我|这道题要交",
    re.IGNORECASE,
)
_INJECTION = re.compile(
    r"ignore (?:all |the |previous |above )?(?:instructions|rules|system)|"
    r"system prompt|developer message|jailbreak|绕过(?:规则|限制)|忽略(?:上述|之前)?(?:指令|规则)",
    re.IGNORECASE,
)
_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?![\w.])")


def assessment_intent(message: str) -> bool:
    return bool(_ASSESSMENT.search(message) or _AMBIGUOUS_ASSESSMENT.search(message))


def suspicious_instruction(text: str) -> bool:
    return bool(_INJECTION.search(text))


def safe_evidence_excerpt(text: str, *, limit: int = 650) -> str:
    """Short source quotation, rejecting obvious instructions planted in uploads."""
    paragraphs = re.split(r"\n+|(?<=[.!?。！？])\s+", text)
    clean = [p.strip() for p in paragraphs if p.strip() and not suspicious_instruction(p)]
    return " ".join(clean)[:limit].strip()


def practice_variant(message: str, language: str, reviewed_template: str | None = None) -> str:
    """Change numerical operands or use a staff-reviewed alternate question.

    Never echo arbitrary instructions from the student's input back as a new
    question. For conceptual questions without a reviewed item, use a safe
    generic alternate context; it is a guided prompt, not a marked problem.
    """
    if reviewed_template and len(reviewed_template) <= 500 and not suspicious_instruction(reviewed_template):
        return reviewed_template
    numbers = list(_NUMBER.finditer(message))
    if numbers and len(message) <= 240 and not suspicious_instruction(message):
        def change(match: re.Match[str]) -> str:
            raw = match.group(0)
            try:
                value = float(raw)
                transformed = value + (3 if value >= 0 else -3)
                return str(int(transformed)) if raw.lstrip("-").isdigit() else f"{transformed:g}"
            except ValueError:
                return raw

        updated = _NUMBER.sub(change, message)
        if updated != message:
            return ("练习一个改变数值的类似问题：" if language == "zh" else "Try a similar practice question with changed numbers: ") + updated
    return (
        "试用教材中的另一个例子练习同一概念。你会先检查什么？"
        if language == "zh" else
        "Try a different example of the same concept from this module. What would you check first?"
    )


def verify_response(
    candidate: str,
    *,
    stage: str,
    locked: bool,
    grounded: bool,
    source_count: int,
    language: str,
    fallback: str,
    evidence_excerpt: str = "",
    model_verdict: bool | None = None,
    approved_translation: str | None = None,
) -> str:
    """Second pass: replace unsafe output rather than letting it escape.

    A full explanation must be derived from a short verified teaching excerpt.
    A heuristic cannot prove an arbitrary model response is entailed by source
    material, so this MVP fails closed to the source excerpt at that stage.
    """
    if not grounded or source_count < 1:
        return fallback
    if locked:
        return fallback
    if stage != "explain":
        # Candidate text can only be used after a distinct local model
        # compliance pass approves it, plus these hard format/content gates.
        # An unavailable/malformed checker always rewrites to server copy.
        if model_verdict is not True or not candidate or candidate == fallback:
            return fallback
        proposal = candidate.strip()
        if len(proposal) > 280 or "\n" in proposal or not proposal.endswith(("?", "？")):
            return fallback
        if not re.match(r"^(?:what|which|how|why|when|where|can|could|would|do|does|"
                        r"try|think|你|请|如果|哪|什|为|怎|能|可)", proposal, re.IGNORECASE):
            return fallback
        if suspicious_instruction(proposal):
            return fallback
        if re.search(r"\d|=|\b(?:answer|solution|equals|therefore|formula|result is|is correct)\b|"
                     r"答案|解答|等于|结果是|所以是", proposal, re.IGNORECASE):
            return fallback
        if language == "en" and re.search(r"[\u3400-\u9fff]", proposal):
            return fallback
        if language == "zh" and len(re.findall(r"[A-Za-z]{3,}", proposal)) > 2:
            return fallback
        # A candidate stuffed with a retrieved worked answer tends to copy
        # source-specific vocabulary. Limit such overlap in question stages.
        source_terms = set(re.findall(r"[a-z]{5,}", evidence_excerpt.lower()))
        proposal_terms = set(re.findall(r"[a-z]{5,}", proposal.lower()))
        if len(source_terms & proposal_terms) > 3:
            return fallback
        return proposal
    excerpt = safe_evidence_excerpt(evidence_excerpt)
    if not excerpt:
        return fallback
    citation = (
        "教材中的相关段落：" if language == "zh" else "Relevant passage from the module: "
    )
    # Keep the model completion away from the final answer: neither lexical
    # overlap nor a second model is a reliable proof of source entailment.
    return citation + (approved_translation if approved_translation else excerpt)
