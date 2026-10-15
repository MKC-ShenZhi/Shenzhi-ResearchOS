import { apiJson, ApiError } from "./http";

export interface UploadFileResult {
  file_id: string;
  filename: string;
  parse_status: "ok" | "failed";
  original_length: number;
  final_length: number;
  truncated: boolean;
  warning?: string;
}

export async function uploadFile(file: File) {
  if (file.size > 20 * 1024 * 1024) throw new ApiError(20006, "附件不能超过 20 MB", 413);
  const body = new FormData();
  body.append("file", file);
  try {
    return await apiJson<UploadFileResult>("/uploads", { method: "POST", body });
  } catch (error) {
    if (error instanceof ApiError && error.status === 413) {
      throw new ApiError(error.code, "附件超过上传大小限制（20 MB），请选择更小的文件", 413,
        { requestId: error.requestId });
    }
    throw error;
  }
}

export function getUploadStatus(fileId: string) {
  return apiJson<UploadFileResult>(`/uploads/${encodeURIComponent(fileId)}`);
}
