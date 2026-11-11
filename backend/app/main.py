import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles

from .core import init_db, Config, log
from .services import seed_if_empty
from . import routes_cases, routes_other, routes_register

STATIC_DIR = os.getenv("STATIC_DIR", os.path.join(os.path.dirname(__file__), "..", "static"))


@asynccontextmanager
async def lifespan(app):
    init_db()
    await seed_if_empty()
    sched = None
    if not Config.DISABLE_JOBS:
        from .jobs import start_scheduler
        sched = start_scheduler()
    yield
    if sched:
        sched.shutdown(wait=False)


app = FastAPI(title="CRK Service Desk", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
                   allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    fields = ", ".join(str(e["loc"][-1]) for e in exc.errors())
    return JSONResponse(status_code=422, content={"detail": f"Data belum lengkap atau formatnya salah: {fields}"})


app.include_router(routes_cases.router)
app.include_router(routes_other.router)
app.include_router(routes_register.router)


@app.get("/api/health")
async def health():
    return {"ok": True, "mockDb": Config.USE_MOCK_DB}


# ---- frontend (React build) ----
if os.path.isdir(STATIC_DIR):
    assets = os.path.join(STATIC_DIR, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        f = os.path.join(STATIC_DIR, path)
        if path and os.path.isfile(f):
            return FileResponse(f)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
