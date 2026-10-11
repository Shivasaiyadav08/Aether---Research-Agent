// The same-origin server proxy adds the verified Clerk session token.
export const API_URL = "/api/backend";

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new Error(
      "Cannot reach the backend. Start FastAPI on port 8000 and check its terminal.",
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `Request failed (${response.status}). Check the submitted values.`,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export async function readSSE(
  response: Response,
  onEvent: (event: import("@/types").WorkflowEvent) => void,
) {
  if (!response.body)
    throw new Error("This browser did not provide a response stream.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let ended = false;
  function consume() {
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (!data) continue; // Real heartbeat comments carry no workflow event.
      const event = JSON.parse(data);
      if (event.type === "done" || event.type === "error") ended = true;
      onEvent(event);
    }
  }
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      consume();
    }
    buffer += decoder.decode();
    consume();
    if (!ended)
      throw new Error(
        "The answer stream was interrupted. Regenerate the question to retry.",
      );
  } finally {
    reader.releaseLock();
  }
}
