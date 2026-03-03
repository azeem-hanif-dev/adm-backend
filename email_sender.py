# email_sender.py
import os
import json
import aiohttp
from dotenv import load_dotenv
from typing import Optional
load_dotenv()


class EmailSender:
    """
    Handles email sending using SendGrid API asynchronously.
    Supports multiple sender emails and signatures.
    """

    def __init__(self):
        self.api_key = os.getenv("SENDGRID_API_KEY")
        
        if not self.api_key:
            raise ValueError("Missing SENDGRID_API_KEY in .env")
        
        # Load signatures from HTML files
        self.signatures = {
            "customers": self._load_signature_file("megan-signature.html"),
            "dcs_customers": self._load_signature_file("dcs-signature.html"),
            "gcc_leads": self._load_signature_file("signature.html")
        }

    def _load_signature_file(self, filename: str) -> str:
        """Load signature from HTML file."""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""  # Return empty if file doesn't exist

    def get_sender_email(self, company_type: str) -> str:
        """Get sender email for company type."""
        email_map = {
            "customers": os.getenv("FROM_EMAIL_Cappah"),
            "dcs_customers": os.getenv("FROM_EMAIL_DCS"),
            "gcc_leads": os.getenv("FROM_EMAIL_GCC")
        }
        
        email = email_map.get(company_type)
        if not email:
            raise ValueError(f"Sender email not configured for {company_type} in .env")
        return email

    async def send_email(
        self, 
        session: aiohttp.ClientSession, 
        recipient: str, 
        subject: str, 
        html_body: str, 
        company_type: str,
        brochure_base64: Optional[str] = None,
        brochure_filename: Optional[str] = None,
        brochure_mime: Optional[str] = None
    ):
        """Send a single email asynchronously via SendGrid API."""
        
        # Debug: save HTML to file
        with open("debug_sent.html", "w", encoding="utf-8") as f:
            f.write(html_body)

        # Get sender email and signature
        from_email = self.get_sender_email(company_type)
        signature = self.signatures.get(company_type, "")
        
        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8"
        }

        # Combine content with signature
        html_content = f"{html_body}<br><br>{signature}"
        
        # Prepare attachments if brochure provided
        attachments = []
        if brochure_base64 and brochure_filename and brochure_mime:
            attachments.append({
                "content": brochure_base64,
                "type": brochure_mime,
                "filename": brochure_filename,
                "disposition": "inline",
                "content_id": brochure_filename
            })

        data = {
            "personalizations": [
                {
                    "to": [{"email": recipient}],
                    "subject": subject,
                    "custom_args": {"preserve_html": "true"}
                }
            ],
            "from": {"email": from_email},
            "content": [{"type": "text/html", "value": html_content}],
            "attachments": attachments,
            "mail_settings": {
                "sandbox_mode": {"enable": False},
                "bypass_spam_management": {"enable": True},
                "bypass_bounce_management": {"enable": True},
                "bypass_unsubscribe_management": {"enable": True}
            },
            "tracking_settings": {
                "click_tracking": {"enable": False, "enable_text": False},
                "open_tracking": {"enable": False},
                "ganalytics": {"enable": False}
            },
            "is_multiple": False
        }

        async with session.post(url, headers=headers, data=json.dumps(data)) as resp:
            if resp.status not in [200, 202]:
                error = await resp.text()
                print(f"❌ Failed for {recipient}: {resp.status} - {error}")
                return False
            else:
                print(f"✅ Sent to {recipient} from {from_email}")
                return True