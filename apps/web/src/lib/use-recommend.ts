"use client";

import { useCallback, useRef, useState } from "react";

import { parseSSEFrame, splitFrames } from "@/lib/sse";

export type StreamStatus = "idle" | "streaming" | "done" | "error" | "quota";

interface UseStreamingExplanation {
  status: StreamStatus;
  text: string;
  error: string | null;
  retryAfterSeconds: number | null;
  /** Start streaming a prose explanation for `query` from the BFF stream route. */
  start: (query: string) => Promise<void>;
  /** Abort the in-flight stream (the Stop button). */
  stop: () => void;
  reset: () => void;
}

/** Consume the BFF SSE stream (/api/recommend/stream) token-by-token.
 *
 * Reads response.body via a reader, decodes chunks as they arrive, splits on
 * SSE frame boundaries, and appends `token` events to `text`. AbortController
 * wires the Stop button to the fetch signal so cancelling actually stops the
 * upstream LLM call (and the billing) — not just the UI. */
export function useStreamingExplanation(): UseStreamingExplanation {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [retryAfterSeconds, setRetryAfterSeconds] = useState<number | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    controllerRef.current?.abort();
  }, []);

  const reset = useCallback(() => {
    setStatus("idle");
    setText("");
    setError(null);
    setRetryAfterSeconds(null);
  }, []);

  const start = useCallback(async (query: string) => {
    const controller = new AbortController();
    controllerRef.current = controller;
    setStatus("streaming");
    setText("");
    setError(null);
    setRetryAfterSeconds(null);

    try {
      const res = await fetch("/api/recommend/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
        signal: controller.signal,
      });

      if (res.status === 429) {
        const retry = Number(res.headers.get("Retry-After") ?? "0");
        setRetryAfterSeconds(Number.isFinite(retry) ? retry : null);
        setStatus("quota");
        return;
      }
      if (!res.ok || !res.body) {
        setError(`Request failed (${res.status})`);
        setStatus("error");
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const { frames, rest } = splitFrames(buffer);
        buffer = rest;
        for (const block of frames) {
          const frame = parseSSEFrame(block);
          if (!frame) continue;
          if (frame.event === "done" || frame.data === "[DONE]") {
            setStatus("done");
            return;
          }
          if (frame.event === "token") {
            setText((prev) => prev + frame.data);
          }
        }
      }
      setStatus("done");
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        // User pressed Stop — a clean cancel, not an error.
        setStatus("done");
        return;
      }
      setError(err instanceof Error ? err.message : "stream failed");
      setStatus("error");
    }
  }, []);

  return { status, text, error, retryAfterSeconds, start, stop, reset };
}
