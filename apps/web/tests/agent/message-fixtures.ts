import type { AgentMessage, MarkdownBlock } from "../../clients/backend/agent-message";

export interface MockMessageEvent { id: string; event: string; data: unknown }

export function messageFixture(status: AgentMessage["status"] = "done", id = "msg_mock"): Omit<AgentMessage, "blocks"> & { blocks: MarkdownBlock[] } {
  return {
    id, role: "assistant", status, created_at: 1795651200.125, schema_version: 1,
    metadata: { model: "mock/model", duration_ms: 9, nested: [null, false, 0, { label: "中文 🧪" }] },
    blocks: [
      { id: "b2", type: "markdown", content: "# 回答\n\n结果 [[cite:r2]]，再次引用 [[cite:r2]]。\n\n| a | b |\n|---|---|\n|1|2|\n" },
      { id: "b1", type: "markdown", content: "```python\nx = '<tag>'\n```\n\n$x^2$ [[cite:r1]]\r\n尾部空格  \n" },
    ],
    references: [
      { id: "r2", type: "paper", title: "测试论文", url: null, entity_id: "paper:1", authors: ["乙", "甲"], year: 2026, venue: "Fixture", doi: "10.0/fixture" },
      { id: "r1", type: "webpage", title: "测试网页", url: "https://example.test/?q=a%20b#part" },
    ],
  };
}

export function messageEvents(message = messageFixture()): MockMessageEvent[] {
  const events: Array<{ event: string; data: unknown }> = [
    { event: "message_start", data: { message: {
      ...structuredClone(message), status: "running", blocks: [], references: [], metadata: { model: "mock/model" },
    } } },
  ];
  for (const reference of message.references) {
    events.push({ event: "reference_upsert", data: { message_id: message.id, reference: structuredClone(reference) } });
  }
  for (const block of message.blocks) {
    events.push({ event: "block_start", data: { message_id: message.id, block: { ...block, content: "" } } });
    for (const delta of [block.content.slice(0, 23), block.content.slice(23, 29), block.content.slice(29)]) {
      events.push({ event: "block_delta", data: { message_id: message.id, block_id: block.id, delta } });
    }
    events.push({ event: "block_end", data: { message_id: message.id, block_id: block.id } });
  }
  events.push({ event: "message_end", data: { message: structuredClone(message) } });
  return events.map((event, index) => ({ id: String(index), ...event }));
}

/** Fragment the actual UTF-8 byte stream, including SSE fields and JSON strings. */
export function mockSse(events: MockMessageEvent[]): Response {
  const text = ": keepalive\r\n\r\n" + events.map((event) =>
    `id: ${event.id}\r\nevent: ${event.event}\r\ndata: ${JSON.stringify(event.data, null, 2).replaceAll("\n", "\r\ndata: ")}\r\n\r\n: ping\r\n\r\n`).join("");
  const bytes = new TextEncoder().encode(text);
  return new Response(new ReadableStream<Uint8Array>({
    start(controller) {
      for (let offset = 0; offset < bytes.length;) {
        const length = offset % 5 + 1;
        controller.enqueue(bytes.slice(offset, offset + length));
        offset += length;
      }
      controller.close();
    },
  }), { headers: { "content-type": "text/event-stream" } });
}
