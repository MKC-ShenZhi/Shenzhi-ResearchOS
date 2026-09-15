/**
 * Read deployment environment values without exposing the environment object
 * or logging secrets.
 */
export function optionalEnv(name: string): string | undefined {
  const value = process.env[name]?.trim();
  return value || undefined;
}

export function parseBooleanEnv(name: string, defaultValue = false): boolean {
  const rawValue = process.env[name];
  if (rawValue === undefined) return defaultValue;

  const value = rawValue.trim().toLowerCase();
  if (value === "true") return true;
  if (value === "false") return false;

  throw new Error(`${name} must be either true or false when configured.`);
}

export function parsePositiveIntegerEnv(name: string, defaultValue: number): number {
  const rawValue = optionalEnv(name);
  if (!rawValue) return defaultValue;
  const value = Number(rawValue);
  if (!Number.isSafeInteger(value) || value <= 0) {
    throw new Error(`${name} must be a positive integer when configured.`);
  }
  return value;
}

export function parseCommaSeparatedEnv(name: string): string[] {
  const value = optionalEnv(name);

  if (!value) return [];

  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
