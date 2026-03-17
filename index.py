# main.py - Updated with Cloudinary integration
import json
import os
import logging
import httpx
import re
import datetime
import math
import uuid
from typing import List, Dict, Any, Optional
import base64
from fastapi import Query, FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from bson import ObjectId
from cloudinary_utils import upload_brochure_to_cloudinary
import cloudinary
from models import CampaignRequest, CampaignResponse, CustomerSelection, CustomerBase
from dependencies import ai, email_sender
import services
from utils import convert_objectid_to_str
from db import (
    get_all_customers,
    get_all_dcs_customers,
    get_all_gcc_leads,
    campaigns_coll,
    sendgrid_events_coll,
    campaign_jobs_coll,
)

# Configure logging
logger = logging.getLogger("campaign-api")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
WORKER_SECRET = os.getenv("WORKER_SECRET") 

# Email validation regex
EMAIL_REGEX = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"


# Initialize FastAPI app
app = FastAPI(
    title="Campaign Management API",
    version="1.0.0",
    docs_url="/docs",          # Enable Swagger UI at /docs
    redoc_url="/redoc",        # ReDoc at /redoc
    openapi_url="/openapi.json"
)

# Add CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------------------------
# Cloudinary upload helper
# ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# API Endpoints
# ----------------------------------------------------------------------
@app.get("/")
async def root():
    """Redirect to interactive API documentation"""
    return RedirectResponse(url="/docs")

@app.get("/api/company-types")
async def get_company_types():
    """Get available company types for dropdown"""
    return [
        {"value": "customers", "label": "Cappah (Regular Customers)"},
        {"value": "dcs_customers", "label": "DCS Products"},
        {"value": "gcc_leads", "label": "GCC Leads"}
    ]

@app.get("/api/customers", response_model=List[Dict[str, Any]])
async def get_customers(
    country: str | None = Query(None)
):
    """
    Get all regular customers (optionally filtered by country)
    """
    try:
        customers = await get_all_customers()

        if country:
            customers = [
                customer for customer in customers
                if isinstance(customer.get("country"), str)
                and customer.get("country").strip().lower() == country.strip().lower()
            ]

        customers = [convert_objectid_to_str(customer) for customer in customers]
        return customers

    except Exception as e:
        logger.error(f"Error fetching customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/customers/dcs", response_model=List[Dict[str, Any]])
async def get_dcs_customers():
    """
    Get all DCS customers
    """
    try:
        customers = await get_all_dcs_customers()
        customers = [convert_objectid_to_str(customer) for customer in customers]        
        return customers
    except Exception as e:
        logger.error(f"Error fetching DCS customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/customers/gcc-leads", response_model=List[Dict[str, Any]])
async def get_gcc_leads():
    """
    Get all GCC leads
    """
    try:
        leads = await get_all_gcc_leads()
        leads = [convert_objectid_to_str(customer) for customer in leads]
        return leads
    except Exception as e:
        logger.error(f"Error fetching GCC leads: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/customers/select")
async def select_customers(selection: CustomerSelection):
    """
    Select customers based on type and optional email list
    """
    try:
        if selection.customer_type == "customers":
            db_docs = await get_all_customers()
        elif selection.customer_type == "dcs_customers":
            db_docs = await get_all_dcs_customers()
        elif selection.customer_type == "gcc_leads":
            db_docs = await get_all_gcc_leads()
        else:
            raise HTTPException(status_code=400, detail="Invalid customer type")
        
        # Map database documents to CustomerBase objects
        db_docs = [convert_objectid_to_str(customer) for customer in db_docs]  
        customers = []
        for doc in db_docs:
            customer = services.map_database_doc_to_customer(doc, selection.customer_type)
            if customer:
                customers.append(customer)
        
        # Filter if specific emails are selected
        if selection.selected_emails:
            selected_emails_set = set(selection.selected_emails)
            filtered_customers = [
                cust for cust in customers 
                if cust.email in selected_emails_set
            ]
            return filtered_customers
        else:
            return customers
            
    except Exception as e:
        logger.error(f"Error selecting customers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/campaigns/send", response_model=CampaignResponse)
async def send_campaign(
    request: CampaignRequest,
):
    """
    Enqueue a campaign to be processed by a background worker.
    If brochure_image (base64) is provided, it will be uploaded to Cloudinary.
    """
    try:
        # Validate company_type
        valid_company_types = ["customers", "dcs_customers", "gcc_leads"]
        if request.company_type not in valid_company_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid company_type. Must be one of: {valid_company_types}",
            )

        # Validate customers list
        if not request.customers:
            raise HTTPException(status_code=400, detail="No customers selected")

        campaign_id = str(uuid.uuid4())

        # Prepare customers as plain dicts for storage in Mongo
        customers_payload = [
            {
                "email": c.email,
                "name": c.name,
                "company_name": c.company_name,
                "country": c.country,
            }
            for c in request.customers
        ]

        # Handle brochure if provided (base64)
        pdf_url = None
        preview_image_url = None
        if request.brochure_image and request.brochure_mime_type:
            try:
                # Decode base64
                brochure_bytes = base64.b64decode(request.brochure_image)
                pdf_url, preview_image_url = await upload_brochure_to_cloudinary(
                    brochure_bytes,
                    folder="campaign_brochures"
                )
                if not pdf_url:
                    logger.warning("Cloudinary upload failed for base64 brochure")
            except Exception as e:
                logger.error(f"Failed to process base64 brochure: {e}")

        job_doc = {
            "campaign_id": campaign_id,
            "status": "pending",
            "campaign_name": request.campaign_name,
            "campaign_prompt": request.campaign_prompt,
            "subject": request.subject,
            "company_type": request.company_type,
            "customers": customers_payload,
            "total_customers": len(customers_payload),
            "sent": 0,
            "failed": 0,
            "failed_emails": [],
            # Cloudinary URLs
            "pdf_url": pdf_url,
            "preview_image_url": preview_image_url,
            # Keep old fields for backward compatibility (optional)
            "brochure_base64": request.brochure_image if not pdf_url else None,
            "brochure_mime": request.brochure_mime_type if not pdf_url else None,
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow(),
            "started_at": None,
            "finished_at": None,
            "next_index": 0,
        }

        await campaign_jobs_coll.insert_one(job_doc)

        response = CampaignResponse(
            campaign_id=campaign_id,
            status="queued",
            total_customers=len(request.customers),
            sent_count=0,
            failed_count=0,
            start_time=datetime.datetime.utcnow(),
        )

        return response

    except Exception as e:
        logger.error(f"Error enqueueing campaign: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/campaigns/send-with-file")
async def send_campaign_with_file(
    campaign_name: str = Form(...),
    campaign_prompt: str = Form(...),
    subject: str = Form(...),
    company_type: str = Form(...),
    customers: str = Form(...),  # JSON string of customers
    brochure_file: Optional[UploadFile] = File(None),
):
    """
    Sends a campaign to customers with an optional brochure file (PDF or image).
    The file is uploaded to Cloudinary; URLs are stored in the job document.
    """
    from utils import clean_country_value

    try:
        # parse JSON
        customer_data = json.loads(customers)
        if isinstance(customer_data, dict):
            customer_list = [customer_data]
        elif isinstance(customer_data, list):
            customer_list = customer_data
        else:
            raise HTTPException(status_code=400, detail="Customers must be a list or dict")

        validated_customers: List[CustomerBase] = []

        for i, cust in enumerate(customer_list):
            try:
                # Fix name
                name = cust.get("name") or cust.get("company_name") or "Customer"
                name = str(name).strip()

                # Fix country
                country = clean_country_value(cust.get("country"))

                # Clean and split emails
                raw_email = cust.get("email", "")
                if not raw_email or not isinstance(raw_email, str):
                    logger.warning(f"[Index {i}] No email, skipping customer")
                    continue

                # Split multiple emails separated by comma, semicolon, space
                email_list = re.split(r"[,\s;]+", raw_email)
                email_list = [e.strip().lower() for e in email_list if e.strip()]

                for email in email_list:
                    try:
                        # Validate email format
                        if not re.match(EMAIL_REGEX, email):
                            logger.warning(f"[Index {i}] Invalid email '{email}', skipping")
                            continue

                        # Create CustomerBase object
                        customer = CustomerBase(
                            email=email,
                            name=name,
                            company_name=cust.get("company_name"),
                            country=country
                        )
                        validated_customers.append(customer)

                    except Exception as e:
                        logger.warning(f"[Index {i}] Pydantic error for email '{email}': {e}")
                        continue

            except Exception as e:
                logger.warning(f"[Index {i}] Skipping invalid customer: {e}")
                continue

        # Process brochure file: upload to Cloudinary if provided
        pdf_url = None
        preview_image_url = None
        if brochure_file:
            brochure_bytes = await brochure_file.read()
            pdf_url, preview_image_url = await upload_brochure_to_cloudinary(
                brochure_bytes,
                brochure_file.filename,
                folder="campaign_brochures"
            )
            logger.info(f"Cloudinary upload result: pdf_url={pdf_url}, preview_url={preview_image_url}")
            if not pdf_url:
                logger.warning("Cloudinary upload failed for brochure file")


        # Create campaign ID and enqueue job
        campaign_id = str(uuid.uuid4())

        customers_payload = [
            {
                "email": c.email,
                "name": c.name,
                "company_name": c.company_name,
                "country": c.country,
            }
            for c in validated_customers
        ]

        job_doc = {
            "campaign_id": campaign_id,
            "status": "pending",
            "campaign_name": campaign_name,
            "campaign_prompt": campaign_prompt,
            "subject": subject,
            "company_type": company_type,
            "customers": customers_payload,
            "total_customers": len(customers_payload),
            "sent": 0,
            "failed": 0,
            "failed_emails": [],
            "pdf_url": pdf_url,                    # <-- add this
            "preview_image_url": preview_image_url, # <-- add this
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow(),
            "started_at": None,
            "finished_at": None,
            "next_index": 0,
        }

        await campaign_jobs_coll.insert_one(job_doc)

        return {
            "campaign_id": campaign_id,
            "status": "queued",
            "message": "Campaign job queued for processing",
            "total_customers": len(validated_customers),
            "company_type": company_type,
        }

    except Exception as e:
        logger.error(f"Error in send_campaign_with_file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/campaigns/status/{campaign_id}")
async def get_campaign_status(campaign_id: str):
    """
    Get status of a running/completed campaign
    """
    job = await campaign_jobs_coll.find_one({"campaign_id": campaign_id})
    if not job:
        raise HTTPException(status_code=404, detail="Campaign not found")

    return {
        "campaign_id": job.get("campaign_id"),
        "status": job.get("status"),
        "total": job.get("total_customers", 0),
        "sent": job.get("sent", 0),
        "failed": job.get("failed", 0),
        "failed_emails": job.get("failed_emails", []),
        "pdf_url": job.get("pdf_url"),
        "preview_image_url": job.get("preview_image_url"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "finished_at": job.get("finished_at"),
        "company_type": job.get("company_type"),
    }

@app.post("/api/campaigns/worker-tick")
async def campaign_worker_tick(
    request: Request,
    batch_size: int = 25,
    secret: Optional[str] = None
):
    # Verify secret (can be passed as query param or header)
    if not secret or secret != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Invalid secret")
    """
    Process a small batch of emails for the next pending/running campaign job.
    Intended for use with Vercel Cron or manual triggering.
    """
    # Pick the oldest pending or running job
    job = await campaign_jobs_coll.find_one(
        {"status": {"$in": ["pending", "running"]}},
        sort=[("created_at", 1)],
    )
    if not job:
        return {"status": "idle", "message": "No pending jobs"}

    job_id = str(job["_id"])
    result = await services.process_campaign_job_batch(
        job_id=job_id,
        batch_size=batch_size,
        ai=ai,
        email_sender=email_sender,
    )

    return {
        "status": "ok",
        "job_id": job_id,
        "campaign_id": job.get("campaign_id"),
        **result,
    }

@app.get("/api/campaigns/history")
async def get_campaign_history(limit: int = 50, skip: int = 0):
    """
    Get campaign history from database
    """
    try:
        campaigns = await campaigns_coll.find().sort("sent_at", -1).skip(skip).limit(limit).to_list(length=limit)
        
        # Convert ObjectId to string
        formatted_campaigns = []
        for campaign in campaigns:
            campaign["_id"] = str(campaign["_id"])
            formatted_campaigns.append(campaign)
        
        return formatted_campaigns
    except Exception as e:
        logger.error(f"Error fetching campaign history: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/sendgrid/webhook")
async def sendgrid_webhook(request: Request):
    """
    Receives SendGrid events: delivered, bounce, click, spamreport
    Stores events in MongoDB collection `sendgrid_events_coll`
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
            "timestamp": datetime.datetime.utcfromtimestamp(e.get("timestamp", 0)),
            "raw": e
        })

    if docs:
        await sendgrid_events_coll.insert_many(docs)
        logger.info("Stored %d SendGrid events", len(docs))

    return {"status": "ok", "stored_events": len(docs)}

@app.get("/api/campaigns/dashboard")
async def get_campaign_dashboard():
    """
    Get overall campaign stats for the dashboard
    """
    try:
        # Fetch all campaigns
        campaigns = await campaigns_coll.find().to_list(length=None)

        total_campaigns = len(campaigns)
        total_customers = sum(c.get("total_customers", 0) for c in campaigns)
        total_sent = sum(c.get("sent_count", 0) for c in campaigns)
        total_failed = sum(c.get("failed_count", 0) for c in campaigns)

        # Optionally: group by company_type
        by_company_type = {}
        for c in campaigns:
            ctype = c.get("company_type", "unknown")
            if ctype not in by_company_type:
                by_company_type[ctype] = {"count": 0, "sent": 0, "failed": 0}
            by_company_type[ctype]["count"] += 1
            by_company_type[ctype]["sent"] += c.get("sent_count", 0)
            by_company_type[ctype]["failed"] += c.get("failed_count", 0)

        return {
            "total_campaigns": total_campaigns,
            "total_customers": total_customers,
            "total_sent": total_sent,
            "total_failed": total_failed,
            "by_company_type": by_company_type
        }

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/campaigns/stats/{campaign_id}")
async def get_campaign_stats(campaign_id: str):
    """
    Get stats for a specific campaign including SendGrid metrics.
    """
    try:
        # Validate campaign ID
        try:
            oid = ObjectId(campaign_id)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid campaign ID format")

        # Fetch campaign from MongoDB
        campaign = await campaigns_coll.find_one({"_id": oid})
        if not campaign:
            raise HTTPException(status_code=404, detail="Campaign not found")

        # Base stats from DB
        stats = {
            "campaign_name": campaign.get("campaign_name"),
            "company_type": campaign.get("company_type"),
            "total_customers": campaign.get("total_customers", 0),
            "sent_count": campaign.get("sent_count", 0),
            "failed_count": campaign.get("failed_count", 0),
            "start_time": campaign.get("start_time"),
            "end_time": campaign.get("end_time")
        }

        # Fetch SendGrid Stats for this campaign using its category
        async with httpx.AsyncClient() as client:
            # SendGrid Stats API (filter by category = campaign_id)
            sg_stats_res = await client.get(
                f"https://api.sendgrid.com/v3/categories/stats?category={campaign_id}",
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            if sg_stats_res.status_code != 200:
                logger.error(f"SendGrid Stats API error: {sg_stats_res.text}")
                sg_stats = {}
            else:
                sg_data = sg_stats_res.json()
                # Sum metrics over all days returned
                total_requests = sum(day.get("stats", [{}])[0].get("metrics", {}).get("requests", 0) for day in sg_data)
                total_delivered = sum(day.get("stats", [{}])[0].get("metrics", {}).get("delivered", 0) for day in sg_data)
                total_clicked = sum(day.get("stats", [{}])[0].get("metrics", {}).get("clicks", 0) for day in sg_data)
                sg_stats = {
                    "requests": total_requests,
                    "delivered": total_delivered,
                    "clicked": total_clicked
                }

            # Optional: Fetch bounces from SendGrid
            sg_bounces_res = await client.get(
                "https://api.sendgrid.com/v3/suppression/bounces",
                headers={
                    "Authorization": f"Bearer {SENDGRID_API_KEY}",
                    "Content-Type": "application/json"
                }
            )
            if sg_bounces_res.status_code != 200:
                logger.error(f"SendGrid Bounces API error: {sg_bounces_res.text}")
                total_bounces = 0
            else:
                bounces_data = sg_bounces_res.json()
                # Count bounces for this campaign (if you tag campaign in email category)
                total_bounces = sum(1 for b in bounces_data if b.get("category") == campaign_id)

        # Merge SendGrid stats into response
        stats.update({
            "requests": sg_stats.get("requests", 0),
            "delivered": sg_stats.get("delivered", 0),
            "clicked": sg_stats.get("clicked", 0),
            "bounces": total_bounces
        })

        return stats

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching campaign stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/campaigns/listing")
async def list_campaigns(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    search: str | None = Query(None)
):
    """
    Returns paginated list of campaigns with optional search.
    """
    try:
        skip = (page - 1) * limit

        query = {}
        if search:
            query = {
                "$or": [
                    {"campaign_name": {"$regex": search, "$options": "i"}},
                    {"customer_name": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                ]
            }

        total_campaigns = await campaigns_coll.count_documents(query)

        campaigns = await (
            campaigns_coll
            .find(query)
            .sort("sent_at", -1)
            .skip(skip)
            .limit(limit)
            .to_list(length=limit)
        )

        campaign_list = []
        for c in campaigns:
            campaign_data = {
                "campaign_id": str(c.get("_id")),
                "email": c.get("email"),
                "customer_name": c.get("customer_name"),
                "campaign_name": c.get("campaign_name"),
                "subject": c.get("subject"),
                "sent_at": c.get("sent_at"),
                "pdf_url": c.get("pdf_url"),
                "preview_image_url": c.get("preview_image_url"),
            }

            # Sanitize numeric fields
            for key, value in campaign_data.items():
                if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                    campaign_data[key] = None

            campaign_list.append(campaign_data)

        return {
            "total_campaigns": total_campaigns,
            "total_pages": math.ceil(total_campaigns / limit),
            "current_page": page,
            "per_page": limit,
            "campaigns": campaign_list,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)