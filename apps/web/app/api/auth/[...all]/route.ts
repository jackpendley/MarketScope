import { toNextJsHandler } from "better-auth/next-js";
import { getAuth } from "@/lib/server/auth";

// Better Auth's endpoints (sign-in, sign-out, session, change-password). Sign-up is disabled.
export const { GET, POST } = toNextJsHandler((request: Request) => getAuth().handler(request));
