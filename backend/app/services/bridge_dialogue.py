"""Eight-stage, server-owned teaching state machine."""

from dataclasses import dataclass


AVATAR_FOR_STAGE = {
    "greeting": "encouraging",
    "diagnosis": "questioning",
    "probing": "questioning",
    "hinting": "explaining",
    "struggle": "thinking",
    "check": "questioning",
    "explain": "explaining",
    "celebrate": "celebrating",
}


@dataclass(frozen=True)
class Transition:
    stage: str
    scaffold_count: int
    mastery: bool
    event_type: str


def advance(stage: str, scaffold_count: int, *, explain_back_ok: bool, locked: bool) -> Transition:
    """Advance only on a grounded turn; >=3 scaffolds precede explanation."""
    if stage == "greeting":
        return Transition("diagnosis", 0, False, "started")
    if stage == "diagnosis":
        return Transition("probing", max(scaffold_count, 1), False, "scaffold")
    if stage == "probing":
        return Transition("hinting", max(scaffold_count, 2), False, "scaffold")
    if stage == "hinting":
        return Transition("struggle", max(scaffold_count, 3), False, "struggled")
    if stage == "struggle":
        return Transition("check", scaffold_count, False, "explain_back_requested")
    if stage == "check":
        if explain_back_ok and scaffold_count >= 3 and not locked:
            return Transition("explain", scaffold_count, True, "mastered")
        return Transition("struggle", max(scaffold_count, 3), False, "misconception")
    if stage == "explain":
        if locked:
            return Transition("hinting", max(scaffold_count, 3), False, "assessment_refusal")
        return Transition("celebrate", scaffold_count, True, "mastered")
    if stage == "celebrate":
        if locked:
            return Transition("hinting", 1, False, "assessment_refusal")
        return Transition("diagnosis", 0, False, "started")
    return Transition("diagnosis", 0, False, "started")


def stage_prompt(stage: str, language: str, *, locked: bool = False) -> str:
    zh = language == "zh"
    if locked:
        return (
            "本模块目前处于考核保护期。我可以引导你思考，但不能给出完整答案。请先说说你的第一步。"
            if zh else
            "This module is in an assessment window. I can guide your thinking, but cannot give a full answer. What is your first step?"
        )
    return {
        "greeting": ("你好！你正在学习哪个概念？" if zh else "Hello! Which concept are you working on?"),
        "diagnosis": ("你想解决什么问题？你已经试过什么方法？" if zh else "What are you trying to find, and what have you tried so far?"),
        "probing": ("教材中的哪个概念可以帮助你确定第一步？" if zh else "Which idea in the module material might help you choose a first step?"),
        "hinting": ("先找出问题中的关键概念。你能说说它的定义吗？" if zh else "Identify the key concept first. How would you define it?"),
        "struggle": ("慢慢来。把这个概念用于一个较简单的情况，会发生什么？" if zh else "Take your time. What happens if you apply that idea to a simpler case?"),
        "check": ("请用自己的话解释你的方法，以及为什么它有效。" if zh else "Explain your approach back to me in your own words, including why it works."),
        "explain": ("现在我们核对教材中的解释。" if zh else "Now let us check the explanation in the module material."),
        "celebrate": ("你已清楚说明了自己的思路。准备试试下一个概念吗？" if zh else "You explained your reasoning clearly. Ready to try the next concept?"),
    }.get(stage, "你可以再说一点吗？" if zh else "Could you tell me a little more?")
