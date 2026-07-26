import { authedBackendFetch } from "@/lib/proxy";

// BFF streaming proxy — the centerpiece of the streaming UX.
//
// The senior move: pipe upstream.body (a ReadableStream) STRAIGHT THROUGH in a
// new Response. Never `await upstream.text()` — that buffers the whole stream
// and destroys token-by-token rendering. nodejs runtime + force-dynamic so the
// route is never statically optimized / buffered.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  const body = await req.text();
  const upstream = await authedBackendFetch("/v1/recommend/stream", {
    method: "POST",
    body,
  });

  // Non-OK (e.g. 429 quota, 401, 503 kill switch) → forward status + body so the
  // client hook can show a friendly message. Retry-After preserved for 429.
  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "");
    const headers = new Headers({ "Content-Type": "application/json" });
    const retryAfter = upstream.headers.get("Retry-After");
    if (retryAfter) headers.set("Retry-After", retryAfter);
    return new Response(text, { status: upstream.status, headers });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      // Disable proxy buffering (nginx/ingress) so tokens flush immediately.
      "X-Accel-Buffering": "no",
    },
  });
}
