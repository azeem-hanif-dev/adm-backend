# services.py
import asyncio
import base64
import datetime
import logging
from typing import List, Optional

import aiohttp

from models import CustomerBase
from utils import inject_cid_image, clean_country_value
from db import append_conversation_message, campaigns_coll

logger = logging.getLogger("campaign-api")

async def send_campaign_to_customers(
    campaign_id: str,
    customers: List[CustomerBase],
    campaign_name: str,
    campaign_prompt: str,
    subject: str,
    company_type: str,
    ai,
    email_sender,
    campaign_statuses: dict,
    brochure_base64: Optional[str] = None,
    brochure_mime: str = "image/jpeg"
):
    """
    Send campaign to a list of customers (background task)
    """
    sent_count = 0
    failed_count = 0
    failed_emails = []
    
    # Generate CID for image
    brochure_cid = f"brochure_{campaign_id}"
    
    campaign_statuses[campaign_id] = {
        "status": "running",
        "total": len(customers),
        "sent": 0,
        "failed": 0,
        "failed_emails": [],
        "start_time": datetime.datetime.utcnow(),
        "end_time": None,
        "company_type": company_type
    }
    
    async with aiohttp.ClientSession() as session:
        for customer in customers:
            try:
                logger.info(f"Generating campaign for {customer.name} ({customer.email})")
                
                # Call AI to generate campaign message
                out = ai.generate_campaign_message(
                    customer_id=customer.email,
                    customer_info={
                        "person_name": customer.name,
                        "company_name": customer.company_name or "",
                        "email": customer.email,
                        "country": customer.country or "",
                        "company_type": company_type
                    },
                    campaign_name=campaign_name,
                    campaign_prompt=campaign_prompt,
                    company_type=company_type
                )
                
                if not isinstance(out, dict) or "html" not in out:
                    logger.error(f"Unexpected response from AI for {customer.email}")
                    failed_count += 1
                    failed_emails.append(customer.email)
                    continue
                
                html = out["html"] or ""
                
                # Inject image if brochure is provided
                if brochure_base64:
                    final_html = inject_cid_image(html, cid=brochure_cid)
                else:
                    final_html = html
                
                # Send email with company_type
                success = await email_sender.send_email(
                    session=session,
                    recipient=customer.email,
                    subject=subject,
                    html_body=final_html,
                    company_type=company_type,
                    brochure_base64=brochure_base64,
                    brochure_filename=brochure_cid,
                    brochure_mime=brochure_mime,
                )
                
                if success:
                    # Save conversation message
                    try:
                        await append_conversation_message(
                            email=customer.email, 
                            role="megan", 
                            content=final_html
                        )
                    except Exception as e:
                        logger.error(f"Failed to append conversation for {customer.email}: {e}")
                    
                    # Insert campaign record
                    try:
                        await campaigns_coll.insert_one({
                            "campaign_id": campaign_id,
                            "email": customer.email,
                            "customer_name": customer.name,
                            "campaign_name": campaign_name,
                            "subject": subject,
                            "company_type": company_type,
                            "sent_at": datetime.datetime.utcnow(),
                            "brochure_filename": brochure_cid if brochure_base64 else None,
                        })
                    except Exception as e:
                        logger.error(f"Failed to log campaign for {customer.email}: {e}")
                    
                    sent_count += 1
                    campaign_statuses[campaign_id]["sent"] = sent_count
                    logger.info(f"✅ Campaign sent to {customer.email}")
                else:
                    failed_count += 1
                    failed_emails.append(customer.email)
                    campaign_statuses[campaign_id]["failed"] = failed_count
                    campaign_statuses[campaign_id]["failed_emails"] = failed_emails
                    logger.error(f"❌ Failed to send to {customer.email}")
                
            except Exception as e:
                logger.exception(f"Error processing customer {customer.email}: {e}")
                failed_count += 1
                failed_emails.append(customer.email)
                campaign_statuses[campaign_id]["failed"] = failed_count
                campaign_statuses[campaign_id]["failed_emails"] = failed_emails
            
            # Rate limiting delay
            await asyncio.sleep(1.5)
    
    # Update campaign status
    campaign_statuses[campaign_id].update({
        "status": "completed",
        "end_time": datetime.datetime.utcnow(),
        "sent_count": sent_count,
        "failed_count": failed_count
    })
    logger.info(f"Campaign {campaign_id} completed: {sent_count} sent, {failed_count} failed")

def map_database_doc_to_customer(doc: dict, customer_type: str) -> CustomerBase:
    """
    Map database document to CustomerBase model based on customer type.
    """
    from models import CustomerBase
    
    email = doc.get("email", "").strip()
    if not email:
        return None
    
    if customer_type == "gcc_leads":
        # GCC leads have first_name, last_name
        first_name = doc.get("first_name", "")
        last_name = doc.get("last_name", "")
        name = f"{first_name} {last_name}".strip() or doc.get("person_name", "Customer")
        company_name = doc.get("company") or doc.get("company_name")
        country = doc.get("country")
    else:
        # Regular customers and DCS customers
        name = doc.get("name") or doc.get("person_name") or "Customer"
        company_name = doc.get("company_name") or doc.get("company")
        country = doc.get("country")
    
    # Clean the country value
    country = clean_country_value(country)
    
    return CustomerBase(
        email=email,
        name=name,
        company_name=company_name,
        country=country
    )