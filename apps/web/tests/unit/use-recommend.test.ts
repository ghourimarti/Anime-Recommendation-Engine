import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useStreamingExplanation } from "@/lib/use-recommend";

/** Build a mock fetch Response whose body streams the given SSE chunks. */
function streamingResponse(chunks: string[], init?: ResponseInit): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
    ...init,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useStreamingExplanation", () => {
  it("accumulates token frames into text and ends on done", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      streamingResponse([
        "event: token\ndata: Hello \n\n",
        "event: token\ndata: world\n\n",
        "event: done\ndata: [DONE]\n\n",
      ]),
    );

    const { result } = renderHook(() => useStreamingExplanation());
    await act(async () => {
      await result.current.start("anything");
    });

    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.text).toBe("Hello world");
  });

  it("handles a frame split across two network chunks", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      // The frame boundary lands mid-buffer — the hook must buffer the partial.
      streamingResponse([
        "event: token\ndata: Par",
        "tial\n\nevent: done\ndata: [DONE]\n\n",
      ]),
    );

    const { result } = renderHook(() => useStreamingExplanation());
    await act(async () => {
      await result.current.start("anything");
    });

    await waitFor(() => expect(result.current.status).toBe("done"));
    expect(result.current.text).toBe("Partial");
  });

  it("surfaces a 429 as quota status with the Retry-After seconds", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("quota exceeded", {
        status: 429,
        headers: { "Retry-After": "3600" },
      }),
    );

    const { result } = renderHook(() => useStreamingExplanation());
    await act(async () => {
      await result.current.start("anything");
    });

    await waitFor(() => expect(result.current.status).toBe("quota"));
    expect(result.current.retryAfterSeconds).toBe(3600);
  });

  it("treats a non-OK non-429 response as an error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("boom", { status: 503 }),
    );

    const { result } = renderHook(() => useStreamingExplanation());
    await act(async () => {
      await result.current.start("anything");
    });

    await waitFor(() => expect(result.current.status).toBe("error"));
  });
});
