"""Agent Platform API process entry point."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import asyncio
import os

from agent_app.api.management import report_router, router as management_router
from agent_app.api.config_management import router as config_management_router
from agent_app.api.routes import router
from agent_app.api.v2 import router as v2_router
from agent_app.errors import BusinessError

@asynccontextmanager
async def lifespan(_app):
    inspector = None
    if os.getenv('AGENT_MANAGEMENT_INSPECTOR_ENABLED', '').lower() == 'true':
        from agent_app.management_operations import watch
        inspector = asyncio.create_task(watch())
    yield
    if inspector:
        inspector.cancel()
        await asyncio.gather(inspector, return_exceptions=True)


app = FastAPI(title='ShenZhi Agent Platform', version='0.1.0', lifespan=lifespan)
app.include_router(router)
app.include_router(v2_router)
app.include_router(management_router)
app.include_router(report_router)
app.include_router(config_management_router)


@app.exception_handler(BusinessError)
async def business_error_handler(_request: Request, exc: BusinessError):
    return JSONResponse(status_code=exc.status,
                        content={'error': {'code': exc.code, 'message': exc.message}})


@app.get('/internal/v1/health')
async def health() -> dict[str, str]:
    return {'status': 'ok', 'service': 'agent'}
