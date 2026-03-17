# services.py
import asyncio
import datetime
import logging
import os
import uuid
from typing import List, Optional

import aiohttp
from bson import ObjectId

from models import CustomerBase
from utils import clean_country_value, inject_preview_image
from db import append_conversation_message, campaigns_coll, campaign_jobs_coll

logger = logging.getLogger("campaign-api")


async def process_campaign_job_batch(job_id: str, batch_size: int, ai, email_sender):
    """
    Process a limited batch of customers for a given campaign job.
    Uses locking to avoid concurrent processing of the same job.
    Returns a dict with job status and processing stats.
    """
    lock_id = str(uuid.uuid4())  # unique identifier for this worker tick

    # Attempt to acquire lock on the job
    # Conditions:
    # - Job is not locked (locked != True) OR
    # - Lock is stale (older than 10 minutes)
    lock_result = await campaign_jobs_coll.update_one(
        {
            "_id": ObjectId(job_id),
            "$or": [
                {"locked": {"$ne": True}},
                {"locked_at": {"$lt": datetime.datetime.utcnow() - datetime.timedelta(minutes=10)}}
            ]
        },
        {
            "$set": {
                "locked": True,
                "locked_by": lock_id,
                "locked_at": datetime.datetime.utcnow(),
                "updated_at": datetime.datetime.utcnow()
            }
        }
    )

    if lock_result.modified_count == 0:
        logger.info(f"[batch] Job {job_id} is locked by another worker, skipping")
        return {"job_status": "locked", "processed": 0}

    # Lock acquired, proceed with processing
    try:
        job = await campaign_jobs_coll.find_one({"_id": ObjectId(job_id)})
        if not job:
            logger.error(f"[batch] Job {job_id} not found after lock acquisition")
            return {"job_status": "not_found", "processed": 0}

        customers_data = job.get("customers", [])
        total = len(customers_data)
        if total == 0:
            await campaign_jobs_coll.update_one(
                {"_id": ObjectId(job_id)},
                {"$set": {"status": "completed", "finished_at": datetime.datetime.utcnow()}}
            )
            return {"job_status": "completed", "processed": 0, "total": 0}

        next_index = job.get("next_index", 0)
        if next_index >= total:
            if job.get("status") != "completed":
                await campaign_jobs_coll.update_one(
                    {"_id": ObjectId(job_id)},
                    {"$set": {"status": "completed", "finished_at": datetime.datetime.utcnow()}}
                )
            return {"job_status": "completed", "processed": 0, "total": total, "next_index": next_index}

        end_index = min(next_index + max(batch_size, 1), total)
        slice_data = customers_data[next_index:end_index]

        pdf_url = job.get("pdf_url")
        preview_image_url = job.get("preview_image_url")
        campaign_id = job.get("campaign_id")
        campaign_name = job.get("campaign_name")
        campaign_prompt = job.get("campaign_prompt")
        subject = job.get("subject")
        company_type = job.get("company_type")

        logger.info(
            f"[batch] Job {job_id} / campaign {campaign_id}: processing customers {next_index}..{end_index-1} of {total}"
        )

        # Ensure job is marked running and started_at set
        await campaign_jobs_coll.update_one(
            {"_id": ObjectId(job_id)},
            {
                "$set": {
                    "status": "running",
                    "started_at": job.get("started_at") or datetime.datetime.utcnow(),
                    "updated_at": datetime.datetime.utcnow(),
                }
            }
        )

        is_local = os.getenv("ENV", "").lower() == "local"
        connector = aiohttp.TCPConnector(ssl=not is_local)
        semaphore = asyncio.Semaphore(10)  # limit concurrent AI calls

        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = []
            for raw in slice_data:
                task = _process_single_customer_batch(
                    raw, job, pdf_url, preview_image_url,
                    ai, email_sender, session, semaphore
                )
                tasks.append(task)
            results = await asyncio.gather(*tasks, return_exceptions=True)

        success_count = sum(1 for r in results if r is True)
        fail_count = sum(1 for r in results if r is False or isinstance(r, Exception))

        new_next_index = end_index
        update_fields = {
            "next_index": new_next_index,
            "updated_at": datetime.datetime.utcnow()
            # Note: sent/failed counters are updated per customer inside _process_single_customer_batch
        }

        job_status = "running"
        if new_next_index >= total:
            job_status = "completed"
            update_fields["status"] = "completed"
            update_fields["finished_at"] = datetime.datetime.utcnow()

        await campaign_jobs_coll.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": update_fields}
        )

        result = {
            "job_status": job_status,
            "processed": len(slice_data),
            "success": success_count,
            "failed": fail_count,
            "total": total,
            "from_index": next_index,
            "to_index": new_next_index,
            "remaining": max(total - new_next_index, 0),
        }
        return result

    finally:
        # Always release the lock when done (success or failure)
        await campaign_jobs_coll.update_one(
            {"_id": ObjectId(job_id), "locked_by": lock_id},
            {"$set": {"locked": False, "locked_by": None, "updated_at": datetime.datetime.utcnow()}}
        )


async def _process_single_customer_batch(
    raw_customer: dict,
    job: dict,
    pdf_url: Optional[str],
    preview_image_url: Optional[str],
    ai,
    email_sender,
    session: aiohttp.ClientSession,
    semaphore: asyncio.Semaphore,
) -> bool:
    """Process one customer: generate HTML, inject preview, send email."""
    async with semaphore:
        # First validate customer data; if invalid, mark failure and return
        try:
            customer = CustomerBase(
                email=raw_customer.get("email"),
                name=raw_customer.get("name"),
                company_name=raw_customer.get("company_name"),
                country=clean_country_value(raw_customer.get("country")),
            )
        except Exception as e:
            logger.warning(f"[batch] Invalid customer data: {raw_customer} - {e}")
            # Increment failed counter and push failed email
            await campaign_jobs_coll.update_one(
                {"_id": ObjectId(job["_id"])},
                {
                    "$inc": {"failed": 1},
                    "$push": {"failed_emails": raw_customer.get("email")},
                    "$set": {"updated_at": datetime.datetime.utcnow()},
                }
            )
            return False

        try:
            logger.info(f"[batch] Generating campaign for {customer.name} ({customer.email})")
            # Call AI (async)
            out = await ai.generate_campaign_message(
                customer_id=customer.email,
                customer_info={
                    "person_name": customer.name,
                    "company_name": customer.company_name or "",
                    "email": customer.email,
                    "country": customer.country or "",
                    "company_type": job["company_type"],
                },
                campaign_name=job["campaign_name"],
                campaign_prompt=job["campaign_prompt"],
                company_type=job["company_type"],
            )

            if not isinstance(out, dict) or "html" not in out:
                logger.error(f"[batch] Unexpected AI response for {customer.email}")
                raise ValueError("AI returned no HTML")

            html = out["html"] or ""
            logger.info(f"[batch] Preview URLs for {customer.email}: pdf_url={pdf_url}, preview_url={preview_image_url}")
            if pdf_url and preview_image_url:
                final_html = inject_preview_image(html, pdf_url, preview_image_url)
                logger.info(f"[batch] After injection, HTML length: {len(final_html)}")
                # Optional: log first 500 chars to see if image tag appears
                logger.debug(f"HTML snippet: {final_html[:500]}")
            else:
                final_html = html
                logger.info(f"[batch] No preview URLs, using raw HTML")

            # Inject preview image if URLs exist
            if pdf_url and preview_image_url:
                final_html = inject_preview_image(html, pdf_url, preview_image_url)
            else:
                final_html = html

            # Send email (no brochure attachments now)
            success = await email_sender.send_email(
                session=session,
                recipient=customer.email,
                subject=job["subject"],
                html_body=final_html,
                company_type=job["company_type"],
            )

            if not success:
                logger.error(f"[batch] SendGrid failure for {customer.email}")
                await campaign_jobs_coll.update_one(
                    {"_id": ObjectId(job["_id"])},
                    {
                        "$inc": {"failed": 1},
                        "$push": {"failed_emails": customer.email},
                        "$set": {"updated_at": datetime.datetime.utcnow()},
                    }
                )
                return False

            # Success - log conversation and campaign
            try:
                await append_conversation_message(
                    email=customer.email,
                    role="megan",
                    content=final_html,
                )
            except Exception as e:
                logger.error(f"[batch] Failed to append conversation for {customer.email}: {e}")

            try:
                await campaigns_coll.insert_one(
                    {
                        "campaign_id": job["campaign_id"],
                        "email": customer.email,
                        "customer_name": customer.name,
                        "campaign_name": job["campaign_name"],
                        "subject": job["subject"],
                        "company_type": job["company_type"],
                        "sent_at": datetime.datetime.utcnow(),
                        "pdf_url": pdf_url,
                        "preview_image_url": preview_image_url,
                    }
                )
            except Exception as e:
                logger.error(f"[batch] Failed to log campaign for {customer.email}: {e}")

            # Increment sent counter
            await campaign_jobs_coll.update_one(
                {"_id": ObjectId(job["_id"])},
                {
                    "$inc": {"sent": 1},
                    "$set": {"updated_at": datetime.datetime.utcnow()},
                }
            )

            logger.info(f"[batch] ✅ Campaign sent to {customer.email}")
            return True

        except Exception as e:
            logger.exception(f"[batch] Error processing {customer.email}: {e}")
            await campaign_jobs_coll.update_one(
                {"_id": ObjectId(job["_id"])},
                {
                    "$inc": {"failed": 1},
                    "$push": {"failed_emails": customer.email},
                    "$set": {"updated_at": datetime.datetime.utcnow()},
                }
            )
            return False


def map_database_doc_to_customer(doc: dict, customer_type: str) -> Optional[CustomerBase]:
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