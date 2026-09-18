import { apiJson } from "./http";

export interface UploadFileResult {
  file_id: string;
  filename: string;
  parse_status: "ok" | "failed";
  original_length: number;
  final_length: number;
  truncated: boolean;
  warning?: string;
}

export function uploadFile(file: File) {
  const body = new FormData();
  body.append("file", file);
  return apiJson<UploadFileResult>("/uploads", { method: "POST", body });
}

export function getUploadStatus(fileId: string) {
  return apiJson<UploadFileResult>(`/uploads/${encodeURIComponent(fileId)}`);
}
