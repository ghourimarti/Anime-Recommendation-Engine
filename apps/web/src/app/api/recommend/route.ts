import { proxyJson } from "@/lib/proxy";

// BFF: structured (persisted) recommendation. Primary page action → 3 cards +
// query_history_id + quota counted once. Forwards 429 + Retry-After verbatim.
export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  const body = await req.text();
  return proxyJson("/v1/recommend", { method: "POST", body });
}
