export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try { response = await fetch('/api/v1/admin-console' + path, { ...options, credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json', ...options.headers } }); }
  catch (error) { if (error instanceof DOMException && error.name === 'AbortError') throw error; throw new ApiError(503, '无法连接管理后端，请稍后刷新'); }
  let body;
  try { body = await response.json(); } catch { throw new ApiError(response.status, '管理后端响应无效'); }
  if (!response.ok || body.code !== 0) {
    if (response.status === 401) window.dispatchEvent(new Event('admin-session-expired'));
    throw new ApiError(response.status, body.message || ({403:'访问被拒绝',503:'管理服务暂不可用'}[response.status] ?? '请求失败'));
  }
  return body.data;
}
