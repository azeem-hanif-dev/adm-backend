# models.py
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, EmailStr, Field

class CustomerBase(BaseModel):
    email: EmailStr
    name: str
    company_name: Optional[str] = None
    country: Optional[str] = None

class CampaignRequest(BaseModel):
    campaign_name: str
    campaign_prompt: str
    subject: str
    customers: List[CustomerBase]
    company_type: str = Field(..., description="Must be: customers, dcs_customers, or gcc_leads")
    brochure_image: Optional[str] = None
    brochure_mime_type: Optional[str] = "image/jpeg"
    
class CampaignResponse(BaseModel):
    campaign_id: str
    status: str
    total_customers: int
    sent_count: int
    failed_count: int
    start_time: datetime
    end_time: Optional[datetime] = None

class CustomerSelection(BaseModel):
    customer_type: str
    selected_emails: Optional[List[str]] = None