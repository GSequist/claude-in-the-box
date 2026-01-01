from fastapi import FastAPI
from dotenv import load_dotenv
from api_routes import execute_routes, admin_routes, maintenance
from models import (
    microvms,
)

load_dotenv()

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


app.include_router(execute_routes.router)
app.include_router(admin_routes.router)
app.include_router(maintenance.router)


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "active_microvms": len(microvms)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info", access_log=True)
