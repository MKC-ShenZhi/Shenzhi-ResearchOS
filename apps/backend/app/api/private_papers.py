"""Private PDF upload and retrieval for the personal library."""
from fastapi import APIRouter, Depends, Query, Request, Response

from app.api._support.upload_reader import read_upload
from app.core.identity import RequestIdentity, require_user
from app.core.responses import ok
from app.services.library.private_papers import PrivatePaperService

router = APIRouter(prefix='/api/v1/private-papers', tags=['private-papers'])
service = PrivatePaperService()


@router.post('')
async def upload_private_paper(request: Request, folder_id: int = Query(ge=1),
                               identity: RequestIdentity = Depends(require_user)):
    filename, content = await read_upload(request)
    return ok(await service.save(identity.subject_id, folder_id, filename, content))


@router.get('')
async def list_private_papers(folder_id: int = Query(ge=1),
                              identity: RequestIdentity = Depends(require_user)):
    return ok({'items': await service.list(identity.subject_id, folder_id)})


@router.get('/{paper_id}/file')
async def get_private_paper_file(paper_id: int, identity: RequestIdentity = Depends(require_user)):
    content = await service.file(identity.subject_id, paper_id)
    return Response(content, media_type='application/pdf', headers={
        'Content-Disposition': 'inline', 'Cache-Control': 'private, no-store',
        'X-Content-Type-Options': 'nosniff',
    })


@router.delete('/{paper_id}', status_code=204)
async def delete_private_paper(paper_id: int, identity: RequestIdentity = Depends(require_user)):
    await service.delete(identity.subject_id, paper_id)
    return Response(status_code=204)
