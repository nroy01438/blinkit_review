from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aisle.api.routers import admin as admin_router
from aisle.api.routers import upload as upload_router
from aisle.db.connection import get_conn
from aisle.settings import get_settings

app = FastAPI(title="AISLE API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload_router.router)
app.include_router(admin_router.router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    db_ok = True
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db_ok": db_ok, "mock_mode": settings.mock_mode}
