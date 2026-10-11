import { describe, expect, it } from "vitest";
import { readSSE } from "./api";
import type { WorkflowEvent } from "../types";

function responseFromChunks(chunks: Uint8Array[]) {
  return new Response(
    new ReadableStream({
      start(controller) {
        chunks.forEach((chunk) => controller.enqueue(chunk));
        controller.close();
      },
    }),
  );
}

describe("real SSE transport parsing", () => {
  it("handles arbitrary byte boundaries, Unicode, CRLF, and heartbeats", async () => {
    const data =
      ': heartbeat\r\n\r\ndata: {"type":"token","text":"Evidence 🌌 café"}\r\n\r\ndata: {"type":"done"}\r\n\r\n';
    const bytes = new TextEncoder().encode(data);
    const events: WorkflowEvent[] = [];
    await readSSE(
      responseFromChunks(Array.from(bytes, (byte) => new Uint8Array([byte]))),
      (event) => events.push(event),
    );
    expect(events.map((event) => event.type)).toEqual(["token", "done"]);
    expect(events[0].text).toBe("Evidence 🌌 café");
  });

  it("rejects incomplete answers instead of treating disconnect as success", async () => {
    const bytes = new TextEncoder().encode(
      'data: {"type":"token","text":"Partial"}\n\n',
    );
    await expect(
      readSSE(responseFromChunks([bytes]), () => {}),
    ).rejects.toThrow("interrupted");
  });

  it("delivers provider errors as terminal events", async () => {
    const events: WorkflowEvent[] = [];
    const bytes = new TextEncoder().encode(
      'data: {"type":"error","message":"Service unavailable"}\n\n',
    );
    await readSSE(responseFromChunks([bytes]), (event) => events.push(event));
    expect(events[0].message).toBe("Service unavailable");
  });
});
