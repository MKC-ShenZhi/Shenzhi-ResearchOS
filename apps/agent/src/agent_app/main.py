"""Agent Platform API process entry point."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_app.api.routes import router
from agent_app.errors import BusinessError

app = FastAPI(title='ShenZhi Agent Platform', version='0.1.0')
app.include_router(router)


@app.exception_handler(BusinessError)
async def business_error_handler(_request: Request, exc: BusinessError):
    return JSONResponse(status_code=exc.status,
                        content={'error': {'code': exc.code, 'message': exc.message}})


@app.get('/internal/v1/health')
async def health() -> dict[str, str]:
    return {'status': 'ok', 'service': 'agent'}
