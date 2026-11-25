import { logJson } from "@/lib/deploy";

/** CSP violation reports (report-only phase): one JSON log line each, nothing stored. */
export async function POST(req: Request) {
  const text = (await req.text()).slice(0, 4000);
  let report: unknown = text;
  try {
    report = JSON.parse(text);
  } catch {
    // keep the raw text
  }
  logJson("warn", "csp violation", { report });
  return new Response(null, { status: 204 });
}
