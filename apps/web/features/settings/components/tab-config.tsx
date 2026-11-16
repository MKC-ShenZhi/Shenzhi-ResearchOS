import { BarChart3, Bell, Bot, KeyRound, Sparkles, UserRound } from "lucide-react";

export type SettingsTab =
  | "profile"
  | "subscription"
  | "usage"
  | "agent"
  | "mcp"
  | "api"
  | "notifications";

export function McpIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="10 24 166 166" fill="none" stroke="currentColor" strokeWidth={12}
      strokeLinecap="round" aria-hidden="true" className={className}>
      <path d="M25 97.8528L92.8823 29.9706C102.255 20.598 117.451 20.598 126.823 29.9706C136.196 39.3431 136.196 54.5391 126.823 63.9117L75.5581 115.177" />
      <path d="M76.2653 114.47L126.823 63.9117C136.196 54.5391 151.392 54.5391 160.765 63.9117L161.118 64.2652C170.491 73.6378 170.491 88.8338 161.118 98.2063L99.7248 159.6C96.6006 162.724 96.6006 167.789 99.7248 170.913L112.331 183.52" />
      <path d="M109.853 46.9411L59.6482 97.1457C50.2757 106.518 50.2757 121.714 59.6482 131.087C69.0208 140.459 84.2168 140.459 93.5894 131.087L143.794 80.8822" />
    </svg>
  );
}

export const SETTINGS_TABS = [
  { value: "profile", message: "profile", icon: UserRound },
  { value: "subscription", message: "subscription", icon: Sparkles },
  { value: "usage", message: "usage", icon: BarChart3 },
  { value: "agent", message: "agent", icon: Bot },
  { value: "mcp", message: "mcp", icon: McpIcon },
  { value: "api", message: "api", icon: KeyRound },
  { value: "notifications", message: "notifications", icon: Bell },
] as const;

export function isSettingsTab(value: string | null): value is SettingsTab {
  return SETTINGS_TABS.some((tab) => tab.value === value);
}
