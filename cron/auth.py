from dotenv import load_dotenv
import os

load_dotenv()


# Security: API key to authenticate with host servers
HOST_API_KEY = os.getenv("HOST_API_KEY")
if not HOST_API_KEY:
    raise ValueError("HOST_API_KEY environment variable not set")


def get_auth_headers() -> dict:
    """Get headers with API key for host authentication"""
    return {"x-api-key": HOST_API_KEY}
