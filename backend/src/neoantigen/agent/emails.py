"""Email draft generation and sending.

Uses a PydanticAI agent (backed by K2 Think V2) to generate a professional draft
per recipient type with a typed `EmailContent` output. Sending goes through the
Gmail API if configured; otherwise the draft is returned for manual send.
"""

from __future__ import annotations

import base64
import json
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ..models import EmailDraft
from ._llm import build_model, has_api_key


class EmailContent(BaseModel):
    """Structured email output from the drafting agent."""

    subject: str = Field(description="Concise subject line, under 80 characters.")
    body: str = Field(description="Full email body. Plain text, no markdown.")


RECIPIENT_INSTRUCTIONS = {
    "sequencing_lab": (
        "You are requesting tumor WES + RNA-seq services for a canine cancer case. "
        "Be concise, professional, and include: patient species, cancer type, tissue type, "
        "urgency, and a request for pricing + turnaround. Ask for CLIA-grade or research-grade options."
    ),
    "synthesis_vendor": (
        "You are ordering a research-grade IVT mRNA construct for a veterinary compassionate-use vaccine. "
        "Include the construct length, desired modifications (N1-methylpseudouridine, Cap-1, polyA tail), "
        "quantity (typical: 500 µg for dosing), and a request for pricing + lead time. Mention that the "
        "sequence will be attached as FASTA."
    ),
    "vet_oncologist": (
        "You are seeking a consultation referral for a canine cancer patient with a complex case. "
        "Include: patient details, diagnosis, prior treatments, interest in immunotherapy / experimental "
        "protocols. Request availability for a 30-minute case review."
    ),
    "ethics_board": (
        "You are drafting a compassionate use / INAD pre-submission for a personalized mRNA cancer vaccine "
        "in a terminal canine patient. Include: justification (standard of care exhausted), safety rationale, "
        "computational evidence, and request for pre-submission meeting guidance."
    ),
    "owner": (
        "You are an AI treatment coordinator writing to a pet owner. Warm, clear, empathetic. "
        "Summarize what the analysis found and what the next steps look like. No jargon. "
        "Explicitly note this is a proposed plan, not a committed treatment."
    ),
}


SYSTEM_PROMPT = """You are an experienced veterinary oncology coordinator drafting professional correspondence.
Produce a complete email with a concise subject line and a well-structured body.
Keep the tone professional, warm where appropriate, and specific to the case context provided."""


async def draft_email(
    recipient_type: str,
    recipient_name: str,
    recipient_email: str = "",
    context: str = "",
    attachments: list[str] | None = None,
) -> EmailDraft:
    instruction = RECIPIENT_INSTRUCTIONS.get(recipient_type, "Write a professional email.")
    attachments = attachments or []

    if not has_api_key():
        return _fallback_draft(recipient_type, recipient_name, recipient_email, context, attachments)

    try:
        from pydantic_ai import Agent

        agent = Agent(
            build_model(),
            output_type=EmailContent,
            system_prompt=SYSTEM_PROMPT,
        )
        prompt = (
            f"Draft an email to {recipient_name}.\n\n"
            f"Recipient type: {recipient_type}\n"
            f"Instruction: {instruction}\n\n"
            f"Case context:\n{context}\n\n"
            f"Sign the email from 'NeoVax Treatment Coordinator'."
        )
        result = await agent.run(prompt)
        content = result.output
    except Exception:
        return _fallback_draft(recipient_type, recipient_name, recipient_email, context, attachments)

    return EmailDraft(
        recipient_type=recipient_type,  # type: ignore[arg-type]
        recipient_name=recipient_name,
        recipient_email=recipient_email or None,
        subject=content.subject,
        body=content.body,
        attachments=attachments,
    )


FALLBACK_TEMPLATES = {
    "sequencing_lab": (
        "Request for tumor sequencing services — canine oncology case",
        """Dear {recipient_name} team,

I am reaching out on behalf of a canine cancer patient who would benefit from your
tumor sequencing services. Summary below.

{context}

We are specifically interested in:
- Whole-exome sequencing (WES) of the tumor biopsy (FFPE or fresh-frozen)
- Matched normal sequencing (buccal swab or blood)
- RNA-seq for expression-level validation of candidate neoantigens
- Somatic variant calling with SnpEff/VEP annotation

Could you please share:
1. Pricing for research-grade and (if available) CLIA-certified tiers
2. Typical turnaround time from sample receipt to annotated VCF
3. Sample shipping requirements (cold chain, formalin, etc.)

Time is a factor — we'd appreciate any expedited options you can offer.

Thank you,
NeoVax Treatment Coordinator
""",
    ),
    "synthesis_vendor": (
        "mRNA synthesis request — canine personalized vaccine",
        """Dear {recipient_name} team,

We would like to place a custom mRNA synthesis order for a veterinary compassionate-use
cancer vaccine application. Details:

{context}

Construct specifications (FASTA attached):
- Research-grade IVT mRNA
- Modified bases: N1-methylpseudouridine (N1Me-Ψ)
- 5' cap: Cap-1 (ideally co-transcriptional / CleanCap)
- Poly-A tail: 120 nt
- Quantity: 500 µg (sufficient for prime + boost dosing in a 30 kg patient)

Could you please share:
1. Total pricing including QC (RIN, endotoxin, sterility, particle size)
2. Lead time from order confirmation to delivery
3. Any recommendations on buffer/lyophilization for shipment

Thank you,
NeoVax Treatment Coordinator
""",
    ),
    "vet_oncologist": (
        "Consultation referral — canine oncology case",
        """Dear Dr. {recipient_name},

I am writing to request a consultation for a canine cancer patient whose owner is
exploring experimental immunotherapy options after exhausting standard of care.

{context}

The owner has agreed to consider a compassionate-use personalized neoantigen vaccine.
We have generated candidate epitope designs and would like your expert opinion on:
1. Feasibility given the patient's current condition
2. Adjunct therapy recommendations (checkpoint inhibitors, tyrosine kinase inhibitors)
3. Monitoring strategy (imaging schedule, bloodwork, ELISpot if available)
4. Appropriate informed-consent framework

Would you have 30 minutes for a case review in the next 1-2 weeks? We can provide
the full computational case file in advance.

Thank you for considering this referral.
Best regards,
NeoVax Treatment Coordinator
""",
    ),
    "ethics_board": (
        "Pre-submission inquiry — compassionate use mRNA vaccine",
        """Dear Ethics Committee,

I am writing to initiate a pre-submission consultation for a compassionate-use
application involving a personalized mRNA cancer vaccine in a terminal canine patient.

{context}

Key justifications:
1. Standard-of-care options have been exhausted (surgery + chemotherapy completed)
2. Tumor biology (KIT exon 11 + 17 co-mutations) predicts poor response to
   remaining approved agents (toceranib)
3. Computational evidence (structural docking, DLA binding prediction) supports
   the rationale for this specific construct
4. Risk/benefit analysis favors the proposed intervention given terminal prognosis

I would welcome guidance on:
- Required pre-submission documentation
- Informed consent template suitable for a veterinary research context
- Any FDA CVM INAD steps we should initiate in parallel

Could we schedule a pre-submission meeting at the committee's convenience?

Respectfully,
NeoVax Treatment Coordinator
""",
    ),
    "owner": (
        "Update on Luna's treatment plan",
        """Hi {recipient_name},

I wanted to share the latest update on Luna's analysis.

{context}

Next steps on our end:
1. Confirm the plan with a board-certified veterinary oncologist
2. Order the mRNA vaccine construct from a research-grade manufacturer
3. Coordinate with your oncology team for formulation and first injection

I'll be in touch as each step completes. Please don't hesitate to reach out
with any questions — we want you and Luna to feel fully informed at every stage.

With care,
NeoVax Treatment Coordinator
""",
    ),
}


def _fallback_draft(
    recipient_type: str, recipient_name: str, recipient_email: str, context: str, attachments: list[str]
) -> EmailDraft:
    """Template-based draft when LLM is unavailable. Produces a realistic, sendable email."""
    subject_tmpl, body_tmpl = FALLBACK_TEMPLATES.get(
        recipient_type,
        ("Inquiry", "Dear {recipient_name},\n\n{context}\n\nBest regards,\nNeoVax Treatment Coordinator"),
    )
    # Strip any leading "Dr." from name for salutations that add their own
    clean_name = recipient_name.replace("Dr. ", "").replace("Dr ", "")
    body = body_tmpl.format(recipient_name=clean_name, context=context.strip() or "Case details on file.")
    return EmailDraft(
        recipient_type=recipient_type,  # type: ignore[arg-type]
        recipient_name=recipient_name,
        recipient_email=recipient_email or None,
        subject=subject_tmpl,
        body=body,
        attachments=attachments,
    )


# ─────────────────────────────────────────────────────────────
# Sending via Gmail API
# ─────────────────────────────────────────────────────────────


def send_via_gmail(draft: EmailDraft) -> str | None:
    """Send the email via Gmail API. Returns message ID on success, None on failure.

    Requires a service account or OAuth2 refresh token in env:
      GOOGLE_CREDENTIALS_PATH=/path/to/credentials.json
      GMAIL_SENDER_EMAIL=you@gmail.com
    """
    if not draft.recipient_email:
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None

    creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
    sender = os.environ.get("GMAIL_SENDER_EMAIL", "")
    if not (creds_path and sender and Path(creds_path).exists()):
        return None

    try:
        creds_data = json.loads(Path(creds_path).read_text())
        creds = Credentials.from_authorized_user_info(creds_data)
        service = build("gmail", "v1", credentials=creds)

        msg = MIMEMultipart()
        msg["to"] = draft.recipient_email
        msg["from"] = sender
        msg["subject"] = draft.subject
        msg.attach(MIMEText(draft.body, "plain"))

        for attach_path in draft.attachments:
            path = Path(attach_path)
            if not path.exists():
                continue
            from email.mime.base import MIMEBase
            from email import encoders

            part = MIMEBase("application", "octet-stream")
            part.set_payload(path.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename={path.name}")
            msg.attach(part)

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return result.get("id")
    except Exception:
        return None
