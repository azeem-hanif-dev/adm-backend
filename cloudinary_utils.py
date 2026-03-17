import os
import logging
import cloudinary
import cloudinary.uploader
from typing import Optional, Tuple
import io

logger = logging.getLogger(__name__)

async def upload_brochure_to_cloudinary(
    file_bytes: bytes,
    filename: str,
    folder: str = "campaign_brochures"
) -> tuple[str | None, str | None]:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True
    )

    try:
        upload_result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            resource_type="auto",
            folder=folder,
            public_id=os.path.splitext(filename)[0],
            filename=filename,
            use_filename=True,
            unique_filename=True
        )

        pdf_url = upload_result["secure_url"]

        # Build preview URL by inserting '/f_jpg,pg_1/' after '/upload/'
        # This matches your working example and works for both PDFs and images.
        if '/upload/' in pdf_url:
            base, rest = pdf_url.split('/upload/', 1)
            preview_url = f"{base}/upload/f_jpg,pg_1/{rest}"
        else:
            # Fallback (should never happen)
            preview_url = pdf_url

        return pdf_url, preview_url

    except Exception as e:
        logger.exception(f"Cloudinary upload failed: {e}")
        return None, None