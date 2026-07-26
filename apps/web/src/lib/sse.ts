// Pure SSE parsing — no browser, no network. Unit-tested in isolation so the
// streaming hook can rely on it. Mirrors the frames emitted by the backend's
// anime_core.streaming.sse_event (apps/api):
//   event: token\ndata: <chunk>\n\n
//   event: done\ndata: [DONE]\n\n

export interface SSEFrame {
  event: string | null;
  data: string;
}

/** Parse a single (already-split) SSE frame block into {event, data}.
 * Returns null for an empty/whitespace block. */
export function parseSSEFrame(block: string): SSEFrame | null {
  const normalized = block.replace(/\r/g, "");
  if (!normalized.trim()) return null;

  let event: string | null = null;
  const dataLines: string[] = [];
  for (const line of normalized.split("\n")) {
    if (line.startsWith("event:")) {
      event = line.slice("event:".length).trim();
    } else if (line.startsWith("data:")) {
      // Per the SSE spec, a single leading space after the colon is stripped.
      dataLines.push(line.slice("data:".length).replace(/^ /, ""));
    }
  }
  // Multi-line data: fields are joined with newlines (spec behavior).
  return { event, data: dataLines.join("\n") };
}

/** Split a streaming buffer into complete frames + the trailing partial.
 * SSE frames are delimited by a blank line (\n\n). The last element is the
 * incomplete remainder to carry into the next read. */
export function splitFrames(buffer: string): { frames: string[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, "\n");
  const parts = normalized.split("\n\n");
  const rest = parts.pop() ?? "";
  return { frames: parts.filter((p) => p.trim().length > 0), rest };
}
