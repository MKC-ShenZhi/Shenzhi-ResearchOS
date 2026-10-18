/** Public model catalog contract shared by Chat and Agent. No credentials. */
export type ModelProvider = "openai" | "anthropic" | "google" | "deepseek" | "zhipu" | "platform" | (string & {});

export interface ModelOption {
  value: string;
  label: string;
  provider: ModelProvider;
  provider_id?: string;
  brand?: string;
  aliases?: string[];
  capabilities?: {
    chat: boolean;
    streaming: boolean;
    tool_calling: boolean;
    reasoning: boolean;
    temperature: boolean;
    thinking: string;
    stream_options: boolean;
    chat_max_tokens: number;
    agent_max_tokens: number;
    max_output_tokens: number;
  };
  enabled: boolean;
  reason?: string;
  description?: string;
}
