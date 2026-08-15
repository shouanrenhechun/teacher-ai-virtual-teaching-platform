from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .api.llm_routes import router as llm_router
from .api.routes import router as core_data_router
from .api.session_routes import router as session_router
from .database.session import init_db


PROJECT_NAME = "师范生 AI 虚拟教学实训平台"
LOCAL_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title=PROJECT_NAME, version="0.1.0", lifespan=lifespan)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_: Request, __: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "数据库暂时不可用，请稍后重试"},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(core_data_router)
app.include_router(llm_router)
app.include_router(session_router)


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "backend",
        "project": PROJECT_NAME,
    }
