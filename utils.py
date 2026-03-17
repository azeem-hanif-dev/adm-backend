# utils.py
import math
from bson import ObjectId
from typing import Dict, Any

def inject_cid_image(html: str, cid: str = "brochure_image_1") -> str:
    """
    Replace a placeholder [IMAGE_PLACEHOLDER] in the AI-generated HTML
    with a proper inline image using SendGrid's content_id.
    """
    img_block = (
        f'<p style="text-align:center;">'
        f'<img src="cid:{cid}" alt="Brochure" '
        f'style="width:100%; max-width:600px; border-radius:12px; display:block; margin:auto;">'
        f'</p>'
    )

    if "[IMAGE_PLACEHOLDER]" in html:
        return html.replace("[IMAGE_PLACEHOLDER]", img_block)
    else:
        # fallback: insert after second paragraph
        lower = html.lower()
        first_idx = lower.find("</p>")
        if first_idx != -1:
            second_idx = lower.find("</p>", first_idx + len("</p>"))
            if second_idx != -1:
                insert_pos = second_idx + len("</p>")
                return html[:insert_pos] + img_block + html[insert_pos:]
            else:
                # only one paragraph exists, append after first
                insert_pos = first_idx + len("</p>")
                return html[:insert_pos] + img_block + html[insert_pos:]
        else:
            # no paragraph tags, prepend image
            return img_block + html

def convert_objectid_to_str(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Convert ObjectId fields to strings in MongoDB documents."""
    if not doc:
        return doc
    
    # Create a copy to avoid modifying the original
    converted = doc.copy()
    
    # Convert _id field if it exists
    if '_id' in converted and isinstance(converted['_id'], ObjectId):
        converted['_id'] = str(converted['_id'])
    
    # Convert any other ObjectId fields
    for key, value in converted.items():
        if isinstance(value, ObjectId):
            converted[key] = str(value)
        elif isinstance(value, dict):
            converted[key] = convert_objectid_to_str(value)
        elif isinstance(value, list):
            converted[key] = [
                convert_objectid_to_str(item) if isinstance(item, dict) else 
                (str(item) if isinstance(item, ObjectId) else item)
                for item in value
            ]
    
    return converted

def clean_country_value(country: Any) -> str:
    """Clean country value, handling NaN and None."""
    if country is None:
        return ""
    if isinstance(country, float) and math.isnan(country):
        return ""
    return str(country)
# utils.py (add this function)
def inject_preview_image(html: str, pdf_url: str, image_url: str) -> str:
    """
    Replace [MEDIA_PLACEHOLDER] with an inline image (JPEG preview) linked to the PDF.
    """
    linked_image = (
        f'<p style="text-align:center;">'
        f'<a href="{pdf_url}" target="_blank" rel="noopener noreferrer">'
        f'<img src="{image_url}" alt="Brochure – click to open PDF" '
        f'style="width:100%; max-width:600px; border-radius:12px; display:block; margin:auto;">'
        f'</a>'
        f'</p>'
    )
    if "[MEDIA_PLACEHOLDER]" in html:
        return html.replace("[MEDIA_PLACEHOLDER]", linked_image)
    # fallback: insert after second paragraph
    lower = html.lower()
    first_idx = lower.find("</p>")
    if first_idx != -1:
        second_idx = lower.find("</p>", first_idx + 4)
        insert_pos = second_idx + 4 if second_idx != -1 else first_idx + 4
        return html[:insert_pos] + linked_image + html[insert_pos:]
    return linked_image + html
