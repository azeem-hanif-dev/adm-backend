# adm_api.py
import asyncio
import base64
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import aiohttp
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from pydantic import BaseModel

from megan_ai import MeganAI
from email_sender import EmailSender
from db import (
    get_lead_by_email,
    get_recent_messages,
    append_conversation_message,
    search_products_text,
    campaigns_coll,
    sendgrid_events_coll
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ADM")

app = FastAPI(title="ADM Campaign API")

megan = MeganAI()
sender = EmailSender()

THROTTLE_SECONDS = 1.5

# -------------------------------
# Helpers
# -------------------------------
def inject_image_after_first_p(html: str, img_tag: str) -> str:
    match = re.search(r"</p\s*>", html, flags=re.IGNORECASE)
    if match:
        idx = match.end()
        return html[:idx] + img_tag + html[idx:]
    return img_tag + html

def build_base64_img_tag(img_bytes: bytes, mime: str) -> str:
    encoded = base64.b64encode(img_bytes).decode()
    return (
        "<div style='margin:20px 0;text-align:center;'>"
        f"<img src='data:{mime};base64,{encoded}' "
        "style='width:100%;max-width:600px;border-radius:12px;"
        "display:block;margin:auto;' />"
        "</div>"
    )

# -------------------------------
# Schemas
# -------------------------------
class CampaignRequest(BaseModel):
    campaign_name: str
    campaign_prompt: str
    lead_emails: List[str]
    subject: Optional[str] = None

class CampaignResponse(BaseModel):
    sent: int
    failed: int

# -------------------------------
# Campaign Send Endpoint
# -------------------------------
@app.post("/campaign/send", response_model=CampaignResponse)
async def send_campaign(
    campaign_name: str = Form(...),
    campaign_prompt: str = Form(...),
    lead_emails: str = Form(...),  # comma-separated
    subject: Optional[str] = Form(None),
    brochure: UploadFile = File(...)
):
    """
    Sends a campaign to existing leads, saves conversation history
    """
    emails = [e.strip().lower() for e in lead_emails.split(",") if e.strip()]
    if not emails:
        raise HTTPException(status_code=400, detail="No lead emails provided")

    img_bytes = await brochure.read()
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Invalid image upload")

    ext = Path(brochure.filename).suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    img_tag = build_base64_img_tag(img_bytes, mime)

    sent, failed = 0, 0

    async with aiohttp.ClientSession() as session:
        for email in emails:
            try:
                lead = await get_lead_by_email(email)
                if not lead:
                    logger.warning("Lead not found: %s", email)
                    failed += 1
                    continue

                recent_msgs = await get_recent_messages(email, limit=5)
                campaign_history = await campaigns_coll.find(
                    {"email": email}
                ).sort("sent_at", -1).to_list(length=5)

                product_summaries = []
                if lead.get("company_name"):
                    product_summaries = await search_products_text(
                        lead["company_name"], limit=4
                    )

                html_body = await asyncio.to_thread(
                    megan.generate_campaign_message,
                    lead_info=lead,
                    campaign_name=campaign_name,
                    campaign_prompt=campaign_prompt,
                    recent_messages=recent_msgs,
                    campaign_history=campaign_history,
                    featured_products=product_summaries,
                )

                if not html_body or len(html_body) < 80:
                    raise ValueError("Empty AI output")

                html_body = inject_image_after_first_p(html_body, img_tag)
                final_subject = subject or f"{campaign_name} – Greenway Products"

                await sender.send_email(
                    session=session,
                    recipient=email,
                    subject=final_subject,
                    html_body=html_body,
                    brochure_base64=base64.b64encode(img_bytes).decode(),
                    brochure_filename=Path(brochure.filename).name,
                    brochure_mime=mime
                )

                await campaigns_coll.insert_one({
                    "email": email,
                    "campaign_name": campaign_name,
                    "campaign_prompt": campaign_prompt,
                    "subject": final_subject,
                    "sent_at": datetime.utcnow()
                })

                await append_conversation_message(
                    email=email,
                    role="megan",
                    content=html_body
                )

                sent += 1
                logger.info("Campaign sent to %s", email)

            except Exception as exc:
                logger.exception("Failed for %s: %s", email, exc)
                failed += 1

            await asyncio.sleep(THROTTLE_SECONDS)

    return CampaignResponse(sent=sent, failed=failed)

# -------------------------------
# SendGrid Webhook Endpoint
# -------------------------------
@app.post("/sendgrid/webhook")
async def sendgrid_webhook(request):
    """
    Receives SendGrid events: delivered, bounce, click, spamreport
    """
    try:
        events = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not isinstance(events, list):
        raise HTTPException(status_code=400, detail="Expected list of events")

    docs = []
    for e in events:
        docs.append({
            "email": e.get("email"),
            "event": e.get("event"),
            "sg_message_id": e.get("sg_message_id"),
            "campaign_name": e.get("campaign_name") or e.get("custom_args", {}).get("campaign_name"),
            "timestamp": datetime.utcfromtimestamp(e.get("timestamp", 0)),
            "raw": e
        })

    if docs:
        await sendgrid_events_coll.insert_many(docs)
        logger.info("Stored %d SendGrid events", len(docs))

    return {"status": "ok"}



# -------------------------------
# Get all campaign names
# -------------------------------
@app.get("/campaign/names")
async def get_campaign_names():
    """
    Returns a list of all distinct campaign names.
    """
    try:
        names = await campaigns_coll.distinct("campaign_name")
        return {"campaign_names": names, "total": len(names)}
    except Exception as exc:
        logger.exception("Failed to fetch campaign names: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch campaign names")



# -------------------------------
# Campaign Stats APIs
# -------------------------------
@app.get("/campaign/stats/{campaign_name}")
async def campaign_stats(campaign_name: str):
    total_sent = await campaigns_coll.count_documents({"campaign_name": campaign_name})

    def count(event):
        return sendgrid_events_coll.count_documents({
            "campaign_name": campaign_name,
            "event": event
        })

    delivered = await count("delivered")
    bounced = await count("bounce")
    clicked = await count("click")
    spam = await count("spamreport")

    return {
        "campaign": campaign_name,
        "total_requests": total_sent,
        "delivered": delivered,
        "bounced": bounced,
        "clicked": clicked,
        "spam_reported": spam
    }

@app.get("/dashboard/campaigns/summary")
async def dashboard_summary():
    total_sent = await campaigns_coll.count_documents({})
    delivered = await sendgrid_events_coll.count_documents({"event": "delivered"})
    bounced = await sendgrid_events_coll.count_documents({"event": "bounce"})
    clicked = await sendgrid_events_coll.count_documents({"event": "click"})
    spam = await sendgrid_events_coll.count_documents({"event": "spamreport"})

    return {
        "total_campaign_requests": total_sent,
        "delivered": delivered,
        "bounced": bounced,
        "clicked": clicked,
        "spam_reported": spam
    }

# -------------------------------
# Health Check
# -------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}
