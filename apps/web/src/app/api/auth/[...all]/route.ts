import { toNextJsHandler } from "better-auth/next-js";

import { getAuth } from "@/lib/auth/server";

/** Better Auth's endpoints (/api/auth/*): sign-in, sign-up, OAuth callbacks, sessions, … */
export async function GET(req: Request) {
  return toNextJsHandler(getAuth()).GET(req);
}

export async function POST(req: Request) {
  return toNextJsHandler(getAuth()).POST(req);
}
