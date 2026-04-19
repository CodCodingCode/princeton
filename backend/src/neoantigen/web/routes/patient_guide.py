"""Patient-facing healing guide.

``POST /api/cases/{case_id}/patient-guide`` returns a ``PatientGuide`` -
lifestyle + self-advocacy guidance generated from the case. Cached on the
``CaseRecord`` so repeat opens of the Healing tab are instant.

Falls back to a static template when the medical/Kimi key is unset, matching
the rest of the app's degrade-don't-fail pattern.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ...agent._llm import call_for_json, has_api_key
from ...chat.agent import _slim_case
from ...chat.patient_guide_prompt import PATIENT_GUIDE_SYSTEM_PROMPT
from ..case_cache import update_cached_guide
from ..storage import store


router = APIRouter(prefix="/api/cases", tags=["patient-guide"])


# ─────────────────────────────────────────────────────────────
# Schema shipped to the frontend
# ─────────────────────────────────────────────────────────────


class HealingBlock(BaseModel):
    heading: str
    body: str
    bullets: list[str] = Field(default_factory=list)


class PatientGuide(BaseModel):
    headline: str
    healing: list[HealingBlock] = Field(default_factory=list)
    warning_signs: list[str] = Field(default_factory=list)
    things_to_avoid: list[str] = Field(default_factory=list)
    questions_for_doctor: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────
# Route
# ─────────────────────────────────────────────────────────────


@router.post("/{case_id}/patient-guide")
async def get_patient_guide(
    case_id: str,
    refresh: bool = Query(default=False),
) -> dict[str, Any]:
    rec = store().get(case_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    if rec.patient_guide is not None and not refresh:
        return rec.patient_guide.model_dump()

    if not has_api_key():
        guide = _fallback_guide(rec.case)
        rec.patient_guide = guide
        _persist_guide_to_cache(rec.input_hash, guide)
        return guide.model_dump()

    try:
        guide = await _generate_guide(rec.case)
    except Exception:
        # Degrade to the template rather than 500 - the frontend should
        # never get stuck with an empty Healing tab.
        guide = _fallback_guide(rec.case)

    rec.patient_guide = guide
    _persist_guide_to_cache(rec.input_hash, guide)
    return guide.model_dump()


def _persist_guide_to_cache(input_hash: str | None, guide: PatientGuide) -> None:
    """Best-effort: mirror the freshly-generated guide into the disk cache so
    subsequent uploads of the same bundle (or a backend restart) skip Kimi.
    Silently no-ops if the case wasn't loaded/cached under a content hash."""
    if not input_hash:
        return
    try:
        update_cached_guide(input_hash, guide)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# LLM generation
# ─────────────────────────────────────────────────────────────


async def _generate_guide(case) -> PatientGuide:
    user_prompt = (
        "Here is the analyzed case. Write the healing guide for THIS patient, "
        "grounded in the specific cancer type, stage, mutations, and "
        "recommended plan. Keep the tone warm and direct. Return the JSON.\n\n"
        f"{_slim_case(case)}"
    )
    return await call_for_json(
        schema=PatientGuide,
        system_prompt=PATIENT_GUIDE_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=4000,
    )


# ─────────────────────────────────────────────────────────────
# Static fallback keyed on cancer type + stage bucket
# ─────────────────────────────────────────────────────────────


def _stage_bucket(case) -> str:
    """Collapse AJCC stage into early / locoregional / advanced / unknown."""
    s = (case.intake.ajcc_stage or "").upper().strip()
    if not s:
        # Infer from Breslow for melanoma if stage is missing.
        b = case.pathology.breslow_thickness_mm
        if b is not None:
            if b < 1.0:
                return "early"
            if b < 4.0:
                return "locoregional"
            return "advanced"
        return "unknown"
    if s.startswith("0") or s.startswith("I") and not s.startswith("II") and not s.startswith("IV"):
        return "early"
    if s.startswith("II"):
        # IIA/IIB/IIC → early; IIIA+ → locoregional.
        if s.startswith("III"):
            return "locoregional"
        return "early"
    if s.startswith("IV"):
        return "advanced"
    return "unknown"


def _is_melanoma(case) -> bool:
    t = (case.primary_cancer_type or case.pathology.primary_cancer_type or "").lower()
    return "melanoma" in t


def _fallback_guide(case) -> PatientGuide:
    melanoma = _is_melanoma(case)
    bucket = _stage_bucket(case)

    headline = {
        "early": (
            "Getting this diagnosis is a lot, and also: catching it early is "
            "the biggest lever you have. Here is what you can do for "
            "yourself while your care team plans the medical side."
        ),
        "locoregional": (
            "This is a serious diagnosis and also a treatable one. Your body "
            "will be doing hard work over the next several months. Here is "
            "how to support it."
        ),
        "advanced": (
            "You are carrying a lot right now. The goal shifts toward living "
            "well alongside treatment. Here is what you can do to feel "
            "stronger, more yourself, and more in control."
        ),
        "unknown": (
            "Your care team is still pinning down the specifics. In the "
            "meantime, here is what you can do for yourself starting today."
        ),
    }[bucket]

    healing: list[HealingBlock] = [
        HealingBlock(
            heading="Fueling your body",
            body=(
                "You don't need a perfect cancer diet. You need enough "
                "protein, enough calories, and foods that feel good to eat. "
                "Your appetite may be unpredictable during treatment, so "
                "the rule is simple: when you can eat, eat something with "
                "protein and something with colour."
            ),
            bullets=[
                "Aim for protein at every meal and snack (eggs, yogurt, beans, fish, lean meat).",
                "Keep easy, appealing foods on hand for the days nothing sounds good.",
                "Stay hydrated. Sip through the day rather than chugging at meals.",
                "Go easy on restrictive diets. Now is not the time to cut food groups without your team's input.",
            ],
        ),
        HealingBlock(
            heading="Moving with intention",
            body=(
                "Regular gentle movement reduces fatigue, improves mood, "
                "and helps treatment tolerance. The goal is consistent, "
                "not intense. A walk counts. Ten minutes counts."
            ),
            bullets=[
                "Aim for 20 to 30 minutes of walking most days, broken up if needed.",
                "Add light strength work twice a week once you feel up to it.",
                "Rest hard on the days your body asks for rest. Push gently on the good days.",
                "Skip high-impact or contact activity around surgeries and infusions.",
            ],
        ),
        HealingBlock(
            heading="Sleep as medicine",
            body=(
                "Sleep is when your body does its repair work. Cancer "
                "treatment disrupts it in every direction: steroids, "
                "anxiety, hot flashes, middle-of-the-night thoughts. "
                "Protect your sleep like you'd protect a medication."
            ),
            bullets=[
                "Keep a steady wake-up time even on hard nights.",
                "Limit caffeine after noon and alcohol entirely.",
                "Screens out of the bedroom if you can manage it.",
                "Tell your care team if you're not sleeping. It's treatable.",
            ],
        ),
        HealingBlock(
            heading="Your mind and mood",
            body=(
                "Fear, grief, anger, numbness, dark humour - every one of "
                "these is a normal response to a cancer diagnosis. Getting "
                "help for your mental health is not weakness, it's "
                "treatment. It measurably improves how you tolerate the "
                "medical side."
            ),
            bullets=[
                "Ask your oncology team for a referral to an oncology social worker or psycho-oncologist.",
                "Try a simple daily practice: five minutes of breathing, journaling, or prayer.",
                "Name what you feel out loud to one person you trust, every day.",
                "If you've had depression or anxiety before, tell your team now, not later.",
            ],
        ),
        HealingBlock(
            heading="Your people",
            body=(
                "You will need help and you will also need space. Both "
                "are okay. The people who love you want a job to do - "
                "give them specific ones, and let the rest be."
            ),
            bullets=[
                "Pick one person as your point of contact for medical updates.",
                "Use a shared tool (CaringBridge, a group text) to avoid repeating news.",
                "Accept specific offers ('meals on Tuesdays', 'rides to infusion') over vague ones.",
                "Consider a peer support group - Cancer Support Community, Imerman Angels, or a disease-specific group.",
            ],
        ),
    ]

    if melanoma:
        healing.append(
            HealingBlock(
                heading="Protecting your skin",
                body=(
                    "You have a higher risk of a second melanoma than "
                    "someone who hasn't had one. Sun protection and "
                    "regular skin checks aren't optional anymore - they're "
                    "part of your treatment plan forever."
                ),
                bullets=[
                    "Daily broad-spectrum SPF 30+ on exposed skin, year-round.",
                    "Wide-brim hat, UPF-rated shirts, and sunglasses outdoors.",
                    "Avoid tanning beds completely. Forever. Not negotiable.",
                    "Monthly self-exam of your whole skin, plus your dermatologist every 3 to 6 months.",
                ],
            )
        )

    warning_signs_common = [
        "Fever above 100.4°F (38°C) during or after treatment.",
        "New severe headache, vision change, or confusion.",
        "Shortness of breath or chest pain.",
        "Uncontrolled nausea, vomiting, or inability to keep fluids down for 24 hours.",
        "New severe pain that over-the-counter medication doesn't touch.",
        "Signs of infection at any port, IV, or surgical site (redness spreading, warmth, pus).",
    ]

    things_to_avoid = [
        "Smoking and vaping - the single biggest reversible risk factor during treatment.",
        "High-dose antioxidant supplements during chemo or radiation unless your team okays them.",
        "New medications or supplements started without running them past your oncology pharmacist.",
    ]
    if melanoma:
        things_to_avoid.append("Tanning beds and unprotected midday sun exposure.")
    things_to_avoid.append(
        "Googling late at night. The statistics you find don't know you."
    )

    questions = [
        "What's the goal of treatment for me: cure, long-term control, or symptom management?",
        "What are the realistic side effects I should plan my next 3 months around?",
        "What's the surveillance plan once active treatment ends?",
        "Am I a candidate for any clinical trials, and how would I find out?",
        "What's your single strongest recommendation if this were your family member?",
        "Who on your team do I call after hours, and when is a symptom urgent enough?",
    ]
    if melanoma:
        questions.insert(
            3,
            "Do I have a BRAF mutation, and does that change my treatment options?",
        )

    return PatientGuide(
        headline=headline,
        healing=healing,
        warning_signs=warning_signs_common,
        things_to_avoid=things_to_avoid,
        questions_for_doctor=questions,
    )


__all__ = ["router", "PatientGuide", "HealingBlock"]
