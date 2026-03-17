import os
import cloudinary
import cloudinary.uploader
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Configure Cloudinary
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

# Path to your local file
file_path = r"C:\Users\tanze\Downloads\Caution Sign Recycled GCC.pdf"  # replace with your local file

# Upload file
try:
    result = cloudinary.uploader.upload(
        file_path,
        resource_type="auto",  # auto detects PDF, images, etc.
        folder="test_uploads"  # optional
    )
    print("File uploaded successfully!")
    print("URL:", result["secure_url"])
except Exception as e:
    print("Upload failed:", e)