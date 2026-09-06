/** Server-side structured logging only. Keep fields explicit and allowlisted. */

export interface LogFields {
  request_id?: string;
  route?: string;
  method?: string;
  status_code?: number;
  duration_ms?: number;
  error_type?: string;
  error_code?: string | number;
  retryable?: boolean;
  upstream?: string;
  provider?: string;
  operation?: string;
}

const ALLOWED_FIELDS: readonly (keyof LogFields)[] = [
  "request_id",
  "route",
  "method",
  "status_code",
  "duration_ms",
  "error_type",
  "error_code",
  "retryable",
  "upstream",
  "provider",
  "operation",
];

type LogLevel = "info" | "warn" | "error";

function write(level: LogLevel, event: string, fields: LogFields = {}): void {
  const record: Record<string, unknown> = {
    timestamp: new Date().toISOString(),
    level: level.toUpperCase(),
    service: "web",
    environment: process.env.NODE_ENV ?? "development",
    event,
    request_id: fields.request_id ?? "-",
  };

  for (const field of ALLOWED_FIELDS) {
    const value = fields[field];
    if (value !== undefined) record[field] = value;
  }

  const line = JSON.stringify(record);
  if (level === "info") console.info(line);
  else if (level === "warn") console.warn(line);
  else console.error(line);
}

export function logInfo(event: string, fields?: LogFields): void {
  write("info", event, fields);
}

export function logWarn(event: string, fields?: LogFields): void {
  write("warn", event, fields);
}

export function logError(event: string, fields?: LogFields): void {
  write("error", event, fields);
}
