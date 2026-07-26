import { describe, expect, it } from "vitest";

import { parseSSEFrame, splitFrames } from "@/lib/sse";

describe("parseSSEFrame", () => {
  it("parses a token frame from the backend's sse_event format", () => {
    const frame = parseSSEFrame("event: token\ndata: Hello");
    expect(frame).toEqual({ event: "token", data: "Hello" });
  });

  it("parses the done sentinel frame", () => {
    const frame = parseSSEFrame("event: done\ndata: [DONE]");
    expect(frame).toEqual({ event: "done", data: "[DONE]" });
  });

  it("strips a single leading space after data: per the SSE spec", () => {
    const frame = parseSSEFrame("data:  two-spaces");
    // Only ONE leading space is stripped — the second is content.
    expect(frame?.data).toBe(" two-spaces");
  });

  it("joins multi-line data fields with newlines", () => {
    const frame = parseSSEFrame("event: token\ndata: line1\ndata: line2");
    expect(frame?.data).toBe("line1\nline2");
  });

  it("returns null for an empty block", () => {
    expect(parseSSEFrame("")).toBeNull();
    expect(parseSSEFrame("   \n  ")).toBeNull();
  });

  it("tolerates carriage returns (\\r\\n line endings)", () => {
    const frame = parseSSEFrame("event: token\r\ndata: Hi\r");
    expect(frame).toEqual({ event: "token", data: "Hi" });
  });
});

describe("splitFrames", () => {
  it("splits complete frames on the blank-line delimiter and keeps the remainder", () => {
    const buffer = "event: token\ndata: a\n\nevent: token\ndata: b\n\nevent: tok";
    const { frames, rest } = splitFrames(buffer);
    expect(frames).toHaveLength(2);
    expect(rest).toBe("event: tok");
  });

  it("returns no frames when nothing is complete yet", () => {
    const { frames, rest } = splitFrames("event: token\ndata: par");
    expect(frames).toHaveLength(0);
    expect(rest).toBe("event: token\ndata: par");
  });

  it("a single \\n must NOT be treated as a frame boundary", () => {
    // Multi-line content within one frame stays one frame.
    const { frames } = splitFrames("event: token\ndata: l1\ndata: l2\n\n");
    expect(frames).toHaveLength(1);
    expect(parseSSEFrame(frames[0])?.data).toBe("l1\nl2");
  });
});
