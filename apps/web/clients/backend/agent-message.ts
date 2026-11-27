/** Message schema v1. Extend the block discriminator here when a type ships. */
import { z } from "zod";
import type { SseEvent } from "./sse";

const identifier = z.string().min(1);
const status = z.enum(["running", "done", "failed", "stopped", "timeout", "awaiting_input"]);

export const markdownBlockSchema = z.object({
  id: identifier,
  type: z.literal("markdown"),
  content: z.string(),
}).strict();

export const referenceSchema = z.object({
  id: identifier.regex(/^[A-Za-z0-9_.:-]+$/),
  type: z.enum(["paper", "author", "institution", "webpage", "dataset", "funding"]),
  title: z.string().min(1),
  url: z.string().nullable().optional(),
  entity_id: z.string().nullable().optional(),
  authors: z.array(z.string()).nullable().optional(),
  year: z.number().int().nullable().optional(),
  venue: z.string().nullable().optional(),
  doi: z.string().nullable().optional(),
}).strict();

// Preserve future blocks as opaque data so the dispatcher can show a fallback.
// No other concrete block schema is defined at this stage. A malformed Markdown
// block must still fail validation rather than entering the fallback branch.
const unknownBlockSchema = z.object({
  id: identifier, type: identifier.refine((value) => value !== "markdown"),
}).catchall(z.unknown());
const blockSchema = z.union([markdownBlockSchema, unknownBlockSchema]);
export const agentMessageSchema = z.object({
  id: identifier,
  role: z.literal("assistant"),
  status,
  created_at: z.number().finite().nonnegative(),
  schema_version: z.literal(1),
  metadata: z.record(z.string(), z.unknown()).nullable().optional(),
  blocks: z.array(blockSchema),
  references: z.array(referenceSchema),
}).strict().superRefine((message, context) => {
  for (const key of ["blocks", "references"] as const) {
    const ids = message[key].map((item) => item.id);
    if (new Set(ids).size !== ids.length) {
      context.addIssue({ code: "custom", path: [key], message: "Duplicate ID" });
    }
  }
  const ids = new Set(message.references.map((reference) => reference.id));
  for (const block of message.blocks) {
    if (block.type !== "markdown" || typeof block.content !== "string") continue;
    for (const match of block.content.matchAll(/\[\[cite:([^\[\]\r\n]*)\]\]/g)) {
      if (!ids.has(match[1])) context.addIssue({ code: "custom", path: ["blocks"], message: "Unresolved citation" });
    }
  }
});

export type AgentMessage = z.infer<typeof agentMessageSchema>;
export type MarkdownBlock = z.infer<typeof markdownBlockSchema>;
export type ContentBlock = AgentMessage["blocks"][number];
export type Reference = z.infer<typeof referenceSchema>;

export function isMarkdownBlock(block: ContentBlock): block is MarkdownBlock {
  return block.type === "markdown" && typeof block.content === "string";
}

// API v2 adds its own version at the event envelope, outside the AIMessage.
const envelope = { schema_version: z.literal(1).optional() };
const messageEventSchemas = {
  message_start: z.object({ ...envelope, message: agentMessageSchema.refine((message) => message.status === "running") }).strict(),
  block_start: z.object({ ...envelope, message_id: identifier, block: blockSchema }).strict(),
  block_delta: z.object({ ...envelope, message_id: identifier, block_id: identifier, delta: z.string() }).strict(),
  block_end: z.object({ ...envelope, message_id: identifier, block_id: identifier }).strict(),
  reference_upsert: z.object({ ...envelope, message_id: identifier, reference: referenceSchema }).strict(),
  message_end: z.object({ ...envelope, message: agentMessageSchema.refine((message) => message.status !== "running") }).strict(),
};

type MessageEventName = keyof typeof messageEventSchemas;
export type AgentMessageEvent = {
  [Name in MessageEventName]: { event: Name; data: z.infer<typeof messageEventSchemas[Name]>; id?: string }
}[MessageEventName];

export class AgentMessageProtocolError extends Error {
  constructor(cause: unknown) {
    super("回复数据格式异常，请重新连接或刷新结果", { cause });
    this.name = "AgentMessageProtocolError";
  }
}

export function parseAgentMessage(value: unknown, expectedStatus?: AgentMessage["status"]): AgentMessage {
  const parsed = agentMessageSchema.safeParse(value);
  if (!parsed.success) throw new AgentMessageProtocolError(parsed.error);
  if (expectedStatus !== undefined && parsed.data.status !== expectedStatus) {
    throw new AgentMessageProtocolError("Message status differs from its result/turn");
  }
  return parsed.data;
}

export function parseAgentMessageEvent(event: SseEvent): AgentMessageEvent | null {
  if (!Object.hasOwn(messageEventSchemas, event.event)) return null;
  const name = event.event as MessageEventName;
  try {
    const data = messageEventSchemas[name].parse(JSON.parse(event.data));
    return { event: name, data, ...(event.id === undefined ? {} : { id: event.id }) } as AgentMessageEvent;
  } catch (cause) {
    throw new AgentMessageProtocolError(cause);
  }
}
