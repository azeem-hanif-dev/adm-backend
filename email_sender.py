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
            return ""

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
        # Brochure parameters are now optional and only used if provided
        brochure_base64: Optional[str] = None,
        brochure_filename: Optional[str] = None,
        brochure_mime: Optional[str] = None
    ):
        """
        Send a single email asynchronously via SendGrid API.
        If brochure data is provided, it will be attached as an inline image or attachment.
        Otherwise, no attachments are sent.
        """
        from_email = self.get_sender_email(company_type)
        signature = self.signatures.get(company_type, "")

        url = "https://api.sendgrid.com/v3/mail/send"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json; charset=utf-8"
        }

        # Combine content with signature
        html_content = f"{html_body}<br><br>{signature}"

        # Build the base payload
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

        # Add attachments only if brochure data is present
        # Inside email_sender.py - inside send_email method

# Debug: log what we received
        print(f"📎 Brochure params: base64={bool(brochure_base64)}, filename={brochure_filename}, mime={brochure_mime}")

# Only add attachments if ALL three are truthy AND the base64 string is not empty
        if brochure_base64 and brochure_filename and brochure_mime:
            # Additional check: ensure base64 is not an empty string
            if isinstance(brochure_base64, str) and len(brochure_base64) > 0:
                attachments = [{
                    "content": brochure_base64,
                    "type": brochure_mime,
                    "filename": brochure_filename,
                    "disposition": "inline" if brochure_mime.startswith("image/") else "attachment",
                    "content_id": brochure_filename if brochure_mime.startswith("image/") else None
                }]
                data["attachments"] = attachments
                print(f"✅ Attachments added ({len(attachments)} file(s))")
            else:
                print("⚠️ Brochure base64 is empty string – skipping attachments")
        else:
            print("ℹ️ No valid brochure data – skipping attachments")
        # Send the request
        async with session.post(url, headers=headers, data=json.dumps(data)) as resp:
            if resp.status not in [200, 202]:
                error = await resp.text()
                print(f"❌ Failed for {recipient}: {resp.status} - {error}")
                return False
            else:
                print(f"✅ Sent to {recipient} from {from_email}")
                return True