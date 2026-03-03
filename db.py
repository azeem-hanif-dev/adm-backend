# db.py
import os
import datetime
import re
from typing import List, Union
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from bson.objectid import ObjectId

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("Missing MONGO_URI in .env")

client = AsyncIOMotorClient(MONGO_URI)
db = client.get_default_database('ADM')  # uses DB in the URI if provided

# Collections
leads_coll = db["Leads"]
conversations_coll = db["Conversations"]
campaigns_coll = db["Campaigns"]
products_coll = db["Products"]
customers_coll = db["Customers"]
dcs_customers_coll = db["DCS-Customers"]
gcc_leads_coll = db["gcc-leads"]  # New collection
sendgrid_events_coll = db["SendGridEvents"]


# Helpful async functions

async def upsert_lead(lead: dict):
    """
    Upsert a lead by email (unique key).
    Returns the document id.
    """
    if "email" not in lead or not lead["email"]:
        raise ValueError("Lead must contain 'email'")

    res = await leads_coll.update_one(
        {"email": lead["email"]},
        {"$set": lead, "$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
        upsert=True,
    )
    # fetch and return the lead
    doc = await leads_coll.find_one({"email": lead["email"]})
    return doc["_id"]

async def get_lead_by_email(email: str):
    return await leads_coll.find_one({"email": email})

async def append_conversation_message(email: str, role: str, content: str):
    """
    Append a message (role: 'megan'/'system'/'lead'/'sender') to conversation history for a lead.
    """
    timestamp = datetime.datetime.utcnow()
    entry = {"role": role, "content": content, "ts": timestamp}
    await conversations_coll.update_one(
        {"email": email},
        {"$push": {"messages": entry}, "$set": {"last_updated": timestamp}},
        upsert=True,
    )

async def get_conversation_messages(email: str):
    """Get all conversation messages for a lead (no limit)."""
    doc = await conversations_coll.find_one({"email": email})
    if not doc:
        return []
    return doc.get("messages", [])

# ====== Product helpers ======
async def upsert_product(product: dict):
    """
    Upsert product by article_number (best-effort). product must contain 'article_number'.
    """
    if not product.get("article_number"):
        raise ValueError("Product must have 'article_number'")
    product_doc = {**product, "updated_at": datetime.datetime.utcnow()}
    await products_coll.update_one(
        {"article_number": product["article_number"]},
        {"$set": product_doc, "$setOnInsert": {"created_at": datetime.datetime.utcnow()}},
        upsert=True,
    )
    return await products_coll.find_one({"article_number": product["article_number"]})

async def get_product_by_article(article_number: str):
    return await products_coll.find_one({"article_number": article_number})

async def search_products_text(query: str):
    """
    Simple text search: matches article number, description, or fallback fuzzy by regex.
    Returns all matching products.
    """
    query = query.strip()
    if not query:
        return []

    # Try exact article number match
    doc = await products_coll.find_one({"article_number": {"$regex": f"^{re.escape(query)}$", "$options": "i"}})
    if doc:
        return [doc]

    # Try partial article number match
    cursor = products_coll.find({"article_number": {"$regex": re.escape(query), "$options": "i"}})
    matches = await cursor.to_list(length=None)
    if matches:
        return matches

    # Fallback: regex search in description
    cursor = products_coll.find({"description": {"$regex": re.escape(query), "$options": "i"}})
    matches = await cursor.to_list(length=None)
    return matches

# Optional: create text index once (run manually)
async def ensure_product_index():
    # Creates a text index on description and article_number for faster text search
    await products_coll.create_index([("description", "text"), ("article_number", "text")], background=True)

# ====== Customer helpers ======

async def upsert_customer(customer: dict):
    """
    Upsert a customer by email (unique key).
    """
    if "email" not in customer or not customer["email"]:
        raise ValueError("Customer must contain 'email'")

    res = await customers_coll.update_one(
        {"email": customer["email"]},
        {
            "$set": customer,
            "$setOnInsert": {"created_at": datetime.datetime.utcnow()},
        },
        upsert=True,
    )

    doc = await customers_coll.find_one({"email": customer["email"]})
    return doc


async def get_customer_by_email(email: str):
    """
    Fetch an existing customer by email.
    """
    return await customers_coll.find_one({"email": email})


async def get_all_customers():
    """Get all customers without limits."""
    cursor = customers_coll.find({})
    return await cursor.to_list(length=None)


async def delete_customer_by_email(email: str) -> bool:
    """
    Delete a single customer by email.
    Returns True if a document was deleted, False otherwise.
    """
    result = await customers_coll.delete_one({"email": email})
    return result.deleted_count > 0


async def delete_customers_by_emails(emails: List[str]) -> int:
    """
    Delete multiple customers by email list.
    Returns the number of documents deleted.
    """
    if not emails:
        return 0
    
    result = await customers_coll.delete_many({"email": {"$in": emails}})
    return result.deleted_count


async def find_customers_by_emails(emails: List[str]) -> List[dict]:
    """
    Find customers by a list of emails.
    Useful for previewing before deletion.
    """
    if not emails:
        return []
    
    cursor = customers_coll.find({"email": {"$in": emails}})
    return await cursor.to_list(length=None)


# ====== DCS-Customer helpers ======

async def upsert_dcs_customer(dcs_customer: dict):
    """
    Upsert a DCS customer by email (unique key).
    """
    if "email" not in dcs_customer or not dcs_customer["email"]:
        raise ValueError("DCS Customer must contain 'email'")

    res = await dcs_customers_coll.update_one(
        {"email": dcs_customer["email"]},
        {
            "$set": dcs_customer,
            "$setOnInsert": {"created_at": datetime.datetime.utcnow()},
        },
        upsert=True,
    )

    doc = await dcs_customers_coll.find_one({"email": dcs_customer["email"]})
    return doc


async def get_dcs_customer_by_email(email: str):
    """
    Fetch an existing DCS customer by email.
    """
    return await dcs_customers_coll.find_one({"email": email})


async def get_all_dcs_customers():
    """Get all DCS customers without limits."""
    cursor = dcs_customers_coll.find({})
    return await cursor.to_list(length=None)


async def delete_dcs_customer_by_email(email: str) -> bool:
    """
    Delete a single DCS customer by email.
    Returns True if a document was deleted, False otherwise.
    """
    result = await dcs_customers_coll.delete_one({"email": email})
    return result.deleted_count > 0


async def delete_dcs_customers_by_emails(emails: List[str]) -> int:
    """
    Delete multiple DCS customers by email list.
    Returns the number of documents deleted.
    """
    if not emails:
        return 0
    
    result = await dcs_customers_coll.delete_many({"email": {"$in": emails}})
    return result.deleted_count


async def find_dcs_customers_by_emails(emails: List[str]) -> List[dict]:
    """
    Find DCS customers by a list of emails.
    Useful for previewing before deletion.
    """
    if not emails:
        return []
    
    cursor = dcs_customers_coll.find({"email": {"$in": emails}})
    return await cursor.to_list(length=None)


# ====== GCC-Leads helpers ======

async def upsert_gcc_lead(gcc_lead: dict):
    """
    Upsert a GCC lead by email (unique key).
    """
    if "email" not in gcc_lead or not gcc_lead["email"]:
        raise ValueError("GCC Lead must contain 'email'")

    res = await gcc_leads_coll.update_one(
        {"email": gcc_lead["email"]},
        {
            "$set": gcc_lead,
            "$setOnInsert": {"created_at": datetime.datetime.utcnow()},
        },
        upsert=True,
    )

    doc = await gcc_leads_coll.find_one({"email": gcc_lead["email"]})
    return doc


async def get_gcc_lead_by_email(email: str):
    """
    Fetch an existing GCC lead by email.
    """
    return await gcc_leads_coll.find_one({"email": email})


async def get_all_gcc_leads():
    """Get all GCC leads without limits."""
    cursor = gcc_leads_coll.find({})
    return await cursor.to_list(length=None)


async def delete_gcc_lead_by_email(email: str) -> bool:
    """
    Delete a single GCC lead by email.
    Returns True if a document was deleted, False otherwise.
    """
    result = await gcc_leads_coll.delete_one({"email": email})
    return result.deleted_count > 0


async def delete_gcc_leads_by_emails(emails: List[str]) -> int:
    """
    Delete multiple GCC leads by email list.
    Returns the number of documents deleted.
    """
    if not emails:
        return 0
    
    result = await gcc_leads_coll.delete_many({"email": {"$in": emails}})
    return result.deleted_count


async def find_gcc_leads_by_emails(emails: List[str]) -> List[dict]:
    """
    Find GCC leads by a list of emails.
    Useful for previewing before deletion.
    """
    if not emails:
        return []
    
    cursor = gcc_leads_coll.find({"email": {"$in": emails}})
    return await cursor.to_list(length=None)


async def search_gcc_leads_by_name(name_query: str) -> List[dict]:
    """
    Search GCC leads by name (case-insensitive).
    Searches in both first_name and last_name fields.
    """
    if not name_query:
        return []
    
    cursor = gcc_leads_coll.find({
        "$or": [
            {"first_name": {"$regex": re.escape(name_query), "$options": "i"}},
            {"last_name": {"$regex": re.escape(name_query), "$options": "i"}}
        ]
    })
    
    return await cursor.to_list(length=None)


async def get_gcc_leads_by_status(status: str) -> List[dict]:
    """
    Get GCC leads filtered by status.
    """
    cursor = gcc_leads_coll.find({"status": status})
    return await cursor.to_list(length=None)


async def count_gcc_leads() -> int:
    """
    Get total count of GCC leads.
    """
    return await gcc_leads_coll.count_documents({})


async def count_gcc_leads_by_status(status: str) -> int:
    """
    Count GCC leads by status.
    """
    return await gcc_leads_coll.count_documents({"status": status})


# ====== Cross-collection deletion helpers ======

async def delete_user_data_by_email(email: str) -> dict:
    """
    Delete user data from all collections by email.
    Returns a summary of deletions.
    """
    result_summary = {
        "email": email,
        "customers_deleted": 0,
        "dcs_customers_deleted": 0,
        "gcc_leads_deleted": 0,
        "leads_deleted": 0,
        "conversations_deleted": 0
    }
    
    # Delete from Customers collection
    customer_result = await customers_coll.delete_one({"email": email})
    result_summary["customers_deleted"] = customer_result.deleted_count
    
    # Delete from DCS-Customers collection
    dcs_result = await dcs_customers_coll.delete_one({"email": email})
    result_summary["dcs_customers_deleted"] = dcs_result.deleted_count
    
    # Delete from GCC-Leads collection
    gcc_result = await gcc_leads_coll.delete_one({"email": email})
    result_summary["gcc_leads_deleted"] = gcc_result.deleted_count
    
    # Delete from Leads collection
    lead_result = await leads_coll.delete_one({"email": email})
    result_summary["leads_deleted"] = lead_result.deleted_count
    
    # Delete from Conversations collection
    conversation_result = await conversations_coll.delete_one({"email": email})
    result_summary["conversations_deleted"] = conversation_result.deleted_count
    
    return result_summary


async def delete_user_data_by_emails(emails: List[str]) -> dict:
    """
    Delete user data from all collections by multiple emails.
    Returns a summary of deletions.
    """
    if not emails:
        return {"total_emails": 0, "deletions": {}}
    
    result_summary = {
        "total_emails": len(emails),
        "deletions": {
            "customers": 0,
            "dcs_customers": 0,
            "gcc_leads": 0,
            "leads": 0,
            "conversations": 0
        }
    }
    
    # Delete from Customers collection
    customers_result = await customers_coll.delete_many({"email": {"$in": emails}})
    result_summary["deletions"]["customers"] = customers_result.deleted_count
    
    # Delete from DCS-Customers collection
    dcs_result = await dcs_customers_coll.delete_many({"email": {"$in": emails}})
    result_summary["deletions"]["dcs_customers"] = dcs_result.deleted_count
    
    # Delete from GCC-Leads collection
    gcc_result = await gcc_leads_coll.delete_many({"email": {"$in": emails}})
    result_summary["deletions"]["gcc_leads"] = gcc_result.deleted_count
    
    # Delete from Leads collection
    leads_result = await leads_coll.delete_many({"email": {"$in": emails}})
    result_summary["deletions"]["leads"] = leads_result.deleted_count
    
    # Delete from Conversations collection
    conversations_result = await conversations_coll.delete_many({"email": {"$in": emails}})
    result_summary["deletions"]["conversations"] = conversations_result.deleted_count
    
    return result_summary


async def preview_user_data_by_emails(emails: List[str]) -> dict:
    """
    Preview user data across all collections before deletion.
    Returns a summary of found records.
    """
    if not emails:
        return {"total_emails": 0, "preview": {}}
    
    preview_summary = {
        "total_emails": len(emails),
        "preview": {
            "customers": [],
            "dcs_customers": [],
            "gcc_leads": [],
            "leads": [],
            "conversations": []
        }
    }
    
    # Find in Customers collection
    customers_cursor = customers_coll.find({"email": {"$in": emails}})
    preview_summary["preview"]["customers"] = await customers_cursor.to_list(length=None)
    
    # Find in DCS-Customers collection
    dcs_cursor = dcs_customers_coll.find({"email": {"$in": emails}})
    preview_summary["preview"]["dcs_customers"] = await dcs_cursor.to_list(length=None)
    
    # Find in GCC-Leads collection
    gcc_cursor = gcc_leads_coll.find({"email": {"$in": emails}})
    preview_summary["preview"]["gcc_leads"] = await gcc_cursor.to_list(length=None)
    
    # Find in Leads collection
    leads_cursor = leads_coll.find({"email": {"$in": emails}})
    preview_summary["preview"]["leads"] = await leads_cursor.to_list(length=None)
    
    # Find in Conversations collection
    conversations_cursor = conversations_coll.find({"email": {"$in": emails}})
    preview_summary["preview"]["conversations"] = await conversations_cursor.to_list(length=None)
    
    return preview_summary


# ====== Campaign helpers ======

async def create_campaign(campaign: dict):
    """
    Create a campaign document once.
    """
    campaign["created_at"] = datetime.datetime.utcnow()
    campaign["history"] = []
    res = await campaigns_coll.insert_one(campaign)
    return res.inserted_id


async def append_campaign_history(campaign_id, email: str, status: str, meta: dict | None = None):
    """
    Append campaign send history.
    One campaign document → many history entries.
    """
    entry = {
        "email": email,
        "status": status,   # sent / failed / opened later
        "meta": meta or {},
        "ts": datetime.datetime.utcnow(),
    }

    await campaigns_coll.update_one(
        {"_id": campaign_id},
        {
            "$push": {"history": entry},
            "$set": {"last_updated": datetime.datetime.utcnow()},
        },
    )


# ====== Index creation helpers ======

async def ensure_gcc_leads_indexes():
    """
    Create indexes for GCC leads collection for better performance.
    """
    # Index on email (unique)
    await gcc_leads_coll.create_index([("email", 1)], unique=True, background=True)
    
    # Index on status for filtering
    await gcc_leads_coll.create_index([("status", 1)], background=True)
    
    # Index on created_at for sorting
    await gcc_leads_coll.create_index([("created_at", -1)], background=True)
    
    # Text index for name searching
    await gcc_leads_coll.create_index(
        [("first_name", "text"), ("last_name", "text")],
        background=True
    )