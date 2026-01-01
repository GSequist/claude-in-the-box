import os
from fastapi import HTTPException, Header
from typing import Optional

# Security: API key for authenticating requests from api.py
HOST_API_KEY = os.getenv("HOST_API_KEY")
if not HOST_API_KEY:
    raise ValueError("HOST_API_KEY environment variable not set")


def verify_api_key(x_api_key: Optional[str] = Header(None)):
    """Verify API key from request header"""
    if x_api_key != HOST_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return x_api_key
