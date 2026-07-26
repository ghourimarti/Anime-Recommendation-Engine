import { proxyJson } from "@/lib/proxy";

// BFF: thumbs up/down → backend /v1/feedback.
export const dynamic = "force-dynamic";

export async function POST(req: Request): Promise<Response> {
  const body = await req.text();
  return proxyJson("/v1/feedback", { method: "POST", body });
}
