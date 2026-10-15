import { apiJson, apiPath, ApiError } from "./http";

export interface PrivatePaper {
  id: number;
  filename: string;
  title: string;
  size_bytes: number;
  created_at: string;
}

export function listPrivatePapers(folderId: number) {
  return apiJson<{ items: PrivatePaper[] }>(`/private-papers?folder_id=${folderId}`);
}

export async function uploadPrivatePaper(folderId: number, file: File) {
  if (file.size > 20 * 1024 * 1024) throw new ApiError(20006, "私有论文不能超过 20 MB", 413);
  const body = new FormData();
  body.append("file", file);
  try {
    return await apiJson<PrivatePaper>(`/private-papers?folder_id=${folderId}`, { method: "POST", body });
  } catch (error) {
    if (error instanceof ApiError && error.status === 413) {
      throw new ApiError(error.code, "私有论文超过上传大小限制（20 MB）", 413,
        { requestId: error.requestId });
    }
    throw error;
  }
}

export function privatePaperFileHref(id: number) {
  return apiPath(`/private-papers/${id}/file`);
}

export function deletePrivatePaper(id: number) {
  return apiJson<void>(`/private-papers/${id}`, { method: "DELETE" });
}
