"use client";

import { usernameClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

/** Browser client for the auth endpoints (same origin, so no baseURL). */
export const authClient = createAuthClient({ plugins: [usernameClient()] });
