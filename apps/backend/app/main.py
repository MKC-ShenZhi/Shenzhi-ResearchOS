from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from app.api import chat, knowledge, search, uploads
from app.core.logging import configure_logging, http_logging_middleware, log_exception, request_duration_ms
from app.core.errors import BusinessError, INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE
from app.core.responses import fail
from app.core.request_context import (
    REQUEST_ID_HEADER,
    get_request_id,
)
from app.services.sessions import repository


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await repository.recover()
    yield
    await repository.close()


app = FastAPI(title='ShenZhi AI API', version='1.0.0', lifespan=lifespan)
configure_logging()
logger = logging.getLogger(__name__)
for router in (chat.router, knowledge.router, search.router, uploads.router):
    app.include_router(router)


app.middleware('http')(http_logging_middleware)


@app.exception_handler(BusinessError)
async def business_error(_request: Request, error: BusinessError):
    return fail(error.code, error.message, error.status)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, _error: RequestValidationError):
    return fail(20001, '请求参数不合法，请检查问题长度、模型和附件数量', 422)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, error: Exception):
    request_id = getattr(request.state, 'request_id', None) or get_request_id() or '-'
    log_exception(
        logger,
        'exception.unexpected',
        {
            'request_id': request_id,
            'route': request.url.path,
            'method': request.method,
            'status_code': 500,
            'duration_ms': request_duration_ms(request),
            'error_type': type(error).__name__,
            'error_code': INTERNAL_ERROR_CODE,
        },
        error,
    )
    response = fail(INTERNAL_ERROR_CODE, INTERNAL_ERROR_MESSAGE, 500)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}
