from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool
from app.core.identity import request_owner
from app.core.responses import ok
from app.api._support.upload_reader import read_upload
from app.services.chat.repository import repository
from app.services.uploads.parser import parse_document

router = APIRouter(prefix='/api/v1/uploads', tags=['uploads'])


def public_upload(item: dict) -> dict:
    return {key: value for key, value in item.items() if key not in ('text', 'owner', 'created_at')}


@router.post('')
async def upload(request: Request, owner: str = Depends(request_owner)):
    filename, data = await read_upload(request)
    parsed = await run_in_threadpool(parse_document, data, filename)
    return ok(public_upload(repository.save_upload(owner, filename, parsed)))


@router.get('/{file_id}')
async def upload_status(file_id: str, owner: str = Depends(request_owner)):
    return ok(public_upload(repository.upload(file_id, owner)))
