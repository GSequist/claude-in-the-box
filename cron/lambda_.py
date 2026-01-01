import asyncio
from host_cleanup_ import fire_host_cleanup


def lambda_handler(request=None):
    """
    Entry point for GCP Cloud Functions or AWS Lambda.

    Args:
        request: Flask Request object (GCP) or EventBridge data (AWS) - not used
    """
    asyncio.run(fire_host_cleanup())
    return {"statusCode": 200, "body": "Host cleanup completed"}
