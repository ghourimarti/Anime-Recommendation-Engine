import { proxyJson } from "@/lib/proxy";

// BFF: paginated history read → backend /v1/history. Forwards limit/offset.
export const dynamic = "force-dynamic";

export async function GET(req: Request): Promise<Response> {
  const search = new URL(req.url).search;
  return proxyJson(`/v1/history${search}`, { method: "GET" });
}
