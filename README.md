# ADM
Auto Digital Marketer
# ADM Campaign Management System

## 📋 Overview

ADM (Automated Digital Marketing) Campaign Management System is a FastAPI-based platform for managing email marketing campaigns. It integrates AI agents (Megan, Anna, Ashley) to generate personalized email content and SendGrid for email delivery.

## 🚀 Features

- **Multi-Company Support**: Manage campaigns for 3 different companies (Cappah, DCS Products, GCC Leads)
- **AI-Powered Content**: Three specialized AI agents generate personalized email content
- **Email Campaigns**: Send bulk emails with inline images and attachments
- **Customer Management**: Three separate customer databases with different schemas
- **Campaign Tracking**: Monitor campaign status and history
- **File Upload**: Support for brochure/image attachments

## 🏗️ Architecture

```
ADM/
├── main.py              # FastAPI application & endpoints
├── models.py           # Pydantic data models
├── services.py         # Business logic & campaign processing
├── utils.py            # Utility functions
├── dependencies.py     # Shared dependencies (AI, EmailSender)
├── agent.py            # CampaignAI class (unified AI agents)
├── email_sender.py     # Email sending with SendGrid
├── db.py              # MongoDB database operations
├── signature_*.html    # Company-specific email signatures
└── requirements.txt    # Python dependencies
```

## 🔧 Installation

### Prerequisites
- Python 3.8+
- MongoDB instance
- SendGrid API key

### Setup

1. **Clone and install dependencies:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

2. **Configure environment variables (.env):**
```env
MONGO_URI=mongodb://localhost:27017/ADM
DEEPSEEK_API_KEY=your_deepseek_api_key
SENDGRID_API_KEY=your_sendgrid_api_key
FROM_EMAIL_CUSTOMERS=customers@cappah.com
FROM_EMAIL_DCS=sales@dcs-products.com
FROM_EMAIL_GCC=gcc@cappah.com
```

3. **Create signature files:**
- `signature_customers.html` - For Cappah regular customers
- `signature_dcs.html` - For DCS Products customers
- `signature_gcc.html` - For GCC leads

4. **Run the application:**
```bash
python main.py
# Or with uvicorn directly:
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## 🌐 API Endpoints

### Base URL: `http://localhost:8000`

### 1. Customer Management

#### GET `/api/customers`
**Description:** Get all regular Cappah customers  
**Response:** List of customer objects with email, name, company, country

#### GET `/api/customers/dcs`
**Description:** Get all DCS Products customers  
**Response:** List of DCS customer objects

#### GET `/api/customers/gcc-leads`
**Description:** Get all GCC leads  
**Response:** List of GCC lead objects

#### POST `/api/customers/select`
**Description:** Select customers by type and optional email filtering  
**Request Body:**
```json
{
  "customer_type": "customers",  // or "dcs_customers" or "gcc_leads"
  "selected_emails": ["email1@example.com"]  // optional
}
```
**Response:** List of CustomerBase objects

### 2. Company Types

#### GET `/api/company-types`
**Description:** Get available company types for dropdown  
**Response:**
```json
[
  {"value": "customers", "label": "Cappah (Regular Customers)"},
  {"value": "dcs_customers", "label": "DCS Products"},
  {"value": "gcc_leads", "label": "GCC Leads"}
]
```

### 3. Campaign Management

#### POST `/api/campaigns/send`
**Description:** Send campaign to selected customers (JSON endpoint)  
**Request Body:**
```json
{
  "campaign_name": "Premium Dustpan Launch",
  "campaign_prompt": "Introduce our new dustpan collection...",
  "subject": "New Dustpan Collection Available",
  "customers": [
    {
      "email": "customer@example.com",
      "name": "John Doe",
      "company_name": "Example Corp",
      "country": "UAE"
    }
  ],
  "company_type": "gcc_leads",
  "brochure_image": null,
  "brochure_mime_type": "image/jpeg"
}
```
**Response:** CampaignResponse with campaign_id and status

#### POST `/api/campaigns/send-with-file`
**Description:** Send campaign with file upload (form-data endpoint)  
**Form Data:**
- `campaign_name`: Campaign name (string)
- `campaign_prompt`: Campaign instructions (string)
- `subject`: Email subject (string)
- `company_type`: "customers", "dcs_customers", or "gcc_leads"
- `customers`: JSON string array of customers  
  Example: `[{"email": "test@example.com", "name": "Test User"}]`
- `brochure_file`: Optional image file

**Response:** Campaign ID and status

#### GET `/api/campaigns/status/{campaign_id}`
**Description:** Get status of a running/completed campaign  
**Response:** Campaign status object with sent/failed counts

#### GET `/api/campaigns/history`
**Description:** Get campaign history  
**Query Parameters:**
- `limit`: Number of records (default: 50)
- `skip`: Records to skip (default: 0)
**Response:** List of past campaigns

## 🤖 AI Agents

The system uses three specialized AI agents:

### 1. **Megan** (`customers`)
- **Role:** Customer Relations & Account Development
- **Target:** Existing Cappah customers
- **Tone:** Professional, warm, familiar
- **Language:** English and Dutch (for Netherlands customers)
- **Features:** Relationship-focused, assumes prior business

### 2. **Anna** (`dcs_customers`)
- **Role:** DCS Products Specialist
- **Target:** DCS customers and leads
- **Tone:** Professional, technical, solution-focused
- **Features:** Product specifications, commercial benefits

### 3. **Ashley** (`gcc_leads`)
- **Role:** GCC Regional Lead Manager
- **Target:** GCC region leads (not yet customers)
- **Tone:** Professional, confident, engaging
- **Features:** Company introduction, GCC market focus

## 📧 Email Configuration

### Sender Emails (.env):
- `FROM_EMAIL_CUSTOMERS`: For Cappah regular customers
- `FROM_EMAIL_DCS`: For DCS Products
- `FROM_EMAIL_GCC`: For GCC region leads

### Signature Files:
Create HTML signature files for each company:
- `signature_customers.html` - Cappah signature
- `signature_dcs.html` - DCS Products signature  
- `signature_gcc.html` - GCC signature

## 🗄️ Database Schema

### Collections:
- **Customers**: Regular Cappah customers
- **DCS-Customers**: DCS Products customers
- **gcc-leads**: GCC region leads
- **Conversations**: Email conversation history
- **Campaigns**: Campaign send records
- **Leads**: General leads
- **Products**: Product catalog

## 🔍 Usage Examples

### 1. Send Campaign via JSON
```bash
curl -X POST "http://localhost:8000/api/campaigns/send" \
  -H "Content-Type: application/json" \
  -d '{
    "campaign_name": "Test Campaign",
    "campaign_prompt": "Test instructions",
    "subject": "Test Subject",
    "customers": [
      {
        "email": "test@example.com",
        "name": "Test User",
        "company_name": "Test Corp",
        "country": "UAE"
      }
    ],
    "company_type": "gcc_leads",
    "brochure_image": null
  }'
```

### 2. Get Campaign Status
```bash
curl "http://localhost:8000/api/campaigns/status/123e4567-e89b-12d3-a456-426614174000"
```

### 3. Get GCC Leads
```bash
curl "http://localhost:8000/api/customers/gcc-leads"
```

### 4. Test with Python
```python
import requests

# Send campaign
response = requests.post(
    "http://localhost:8000/api/campaigns/send",
    json={
        "campaign_name": "Test",
        "campaign_prompt": "Test prompt",
        "subject": "Test Subject",
        "customers": [{"email": "test@example.com", "name": "Test"}],
        "company_type": "gcc_leads"
    }
)
print(response.json())
```

## 🐛 Troubleshooting

### Common Issues:

1. **Missing .env variables:**
   ```
   ValueError: Missing DEEPSEEK_API_KEY or SENDGRID_API_KEY
   ```
   **Solution:** Check your .env file contains all required variables

2. **MongoDB Connection:**
   ```
   pymongo.errors.ServerSelectionTimeoutError
   ```
   **Solution:** Ensure MongoDB is running and MONGO_URI is correct

3. **SendGrid Errors:**
   ```
   Failed to send to recipient@example.com: 403 Forbidden
   ```
   **Solution:** Verify SendGrid API key and sender email configuration

4. **NaN values in country field:**
   ```
   pydantic_core.PydanticSerializationError
   ```
   **Solution:** Clean your database or use the provided cleanup functions

### Logs:
Check application logs for detailed error information:
```bash
# Logs will show in console when running the app
python main.py
```

## 📊 Monitoring

### Campaign Status Fields:
```json
{
  "campaign_id": "uuid",
  "status": "running|completed",
  "total": 100,
  "sent": 85,
  "failed": 15,
  "failed_emails": ["bad@email.com"],
  "start_time": "2024-01-01T00:00:00Z",
  "end_time": "2024-01-01T00:05:00Z",
  "company_type": "gcc_leads"
}
```

### Rate Limiting:
- 1.5 seconds delay between emails to respect SendGrid limits
- Background processing for large campaigns

## 🔒 Security Considerations

1. **API Keys:** Store all API keys in .env file, never in code
2. **Database:** Secure MongoDB with authentication
3. **Validation:** All inputs validated with Pydantic models
4. **CORS:** Configure allowed origins in production
5. **File Uploads:** Validate file types and sizes in production

## 🚀 Production Deployment

### Recommended Setup:
1. **Web Server:** Nginx + Gunicorn/Uvicorn
2. **Database:** MongoDB Atlas or self-hosted with auth
3. **Caching:** Redis for campaign status
4. **Monitoring:** Log aggregation, error tracking
5. **Security:** HTTPS, API rate limiting, authentication

```

## 📄 License

This project is for internal use. Contact the development team for licensing information.

---
