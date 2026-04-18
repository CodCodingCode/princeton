"""Plain-English case narrative for the pet owner.

Uses K2 Think V2 via PydanticAI to produce a warm, jargon-free explanation.
Falls back to a static template when K2_API_KEY is not set.
"""

from __future__ import annotations

from ._llm import build_model, has_api_key, strip_think


SYSTEM_PROMPT = """You are a compassionate veterinary treatment coordinator.
Write a short, warm, clear plain-English explanation for the pet owner. 400-500 words.

Structure:
1. What we found in the tumor (mutations, in simple terms)
2. Why a personalized vaccine makes sense
3. What the next steps are
4. What outcomes are realistic — be honest, don't overpromise

Avoid medical jargon. Analogies are encouraged. End with a note that this is a proposed plan
that requires a licensed veterinary oncologist to implement."""


async def explain_case(
    patient_name: str,
    cancer_type: str,
    candidate_count: int,
    top_mutation: str,
    **extra,
) -> str:
    if not has_api_key():
        return _fallback(patient_name, cancer_type, candidate_count, top_mutation)

    try:
        from pydantic_ai import Agent

        agent = Agent(
            build_model(),
            output_type=str,
            system_prompt=SYSTEM_PROMPT,
        )
        prompt = (
            f"Patient: {patient_name}\n"
            f"Cancer type: {cancer_type}\n"
            f"Top mutation found: {top_mutation}\n"
            f"Strong vaccine candidates found: {candidate_count}\n\n"
            "Write the owner-facing explanation."
        )
        result = await agent.run(prompt)
        return strip_think(result.output)
    except Exception:
        return _fallback(patient_name, cancer_type, candidate_count, top_mutation)


def _fallback(patient_name: str, cancer_type: str, candidate_count: int, top_mutation: str) -> str:
    return (
        f"Hi — here's what we found for {patient_name}.\n\n"
        f"The tumor has several DNA typos (mutations). These typos change tiny parts of proteins "
        f"inside the cancer cells and make them look different from healthy cells. The most "
        f"important one we found is {top_mutation}.\n\n"
        f"We identified {candidate_count} strong candidate fragments from these mutations. A "
        f"personalized vaccine made from these fragments would teach {patient_name}'s immune "
        f"system to recognize and attack cells carrying them — while leaving healthy cells alone.\n\n"
        f"Next steps: confirm the plan with a veterinary oncologist, order the mRNA, formulate it "
        f"into a lipid nanoparticle, and schedule the first injection. The whole process takes "
        f"about 5-6 weeks.\n\n"
        f"Honest expectations: personalized cancer vaccines are promising but not guaranteed. "
        f"Current data (human trials) shows roughly 40-50% of patients see meaningful tumor "
        f"response. This is best used alongside surgery or standard chemo, not instead of it.\n\n"
        f"This is a proposed plan. Any treatment decision should be made with a licensed veterinary "
        f"oncologist who has examined {patient_name} in person."
    )
