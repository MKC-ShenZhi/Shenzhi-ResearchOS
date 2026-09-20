"""Bounded multipart reader, avoiding UploadFile's disk-spooled temporary files."""
from fastapi import Request
from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header
from app.core.config import MAX_UPLOAD_BYTES
from app.core.errors import BusinessError


async def read_upload(request: Request) -> tuple[str, bytes]:
    content_type, options = parse_options_header(request.headers.get('content-type', ''))
    boundary = options.get(b'boundary')
    if content_type != b'multipart/form-data' or not boundary or len(boundary) > 200:
        raise BusinessError(20006, '请使用 multipart/form-data 上传 file 字段', 400)
    data = bytearray()
    header_name, header_value = bytearray(), bytearray()
    headers = {}
    filename = None
    reading = False
    ended = False

    def part_begin():
        nonlocal reading
        reading = False
        headers.clear()

    def header_field(chunk, start, end):
        header_name.extend(chunk[start:end])

    def header_data(chunk, start, end):
        header_value.extend(chunk[start:end])

    def header_end():
        headers[bytes(header_name).lower()] = bytes(header_value)
        header_name.clear()
        header_value.clear()

    def headers_finished():
        nonlocal filename, reading
        _, opts = parse_options_header(headers.get(b'content-disposition', b''))
        if opts.get(b'name') != b'file' or b'filename' not in opts or filename is not None:
            raise BusinessError(20006, '每次请求只能上传一个 file 字段', 400)
        filename = opts[b'filename'].decode('utf-8', errors='replace')[:500]
        reading = True

    def part_data(chunk, start, end):
        if reading:
            if len(data) + end - start > MAX_UPLOAD_BYTES:
                raise BusinessError(20006, '附件不能超过 20MB', 413)
            data.extend(chunk[start:end])

    def on_end():
        nonlocal ended
        ended = True

    parser = MultipartParser(boundary, {'on_part_begin': part_begin,
        'on_header_field': header_field, 'on_header_value': header_data,
        'on_header_end': header_end, 'on_headers_finished': headers_finished,
        'on_part_data': part_data, 'on_end': on_end})
    total = 0
    try:
        async for chunk in request.stream():
            total += len(chunk)
            if total > MAX_UPLOAD_BYTES + 65536:
                raise BusinessError(20006, '上传请求过大', 413)
            parser.write(chunk)
        parser.finalize()
    except BusinessError:
        raise
    except Exception as exc:
        raise BusinessError(20006, '上传格式不完整或无法解析', 400) from exc
    if not filename or not ended:
        raise BusinessError(20006, '上传内容不完整', 400)
    return filename, bytes(data)
