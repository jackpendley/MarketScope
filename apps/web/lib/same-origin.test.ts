import { describe, expect, it } from "vitest";
import { isSameOriginMutation } from "./same-origin";

describe("isSameOriginMutation", () => {
  it("allows reads and same-host writes", () => {
    expect(isSameOriginMutation("GET", null, "marketscope-delta.vercel.app")).toBe(true);
    expect(
      isSameOriginMutation(
        "POST",
        "https://marketscope-delta.vercel.app",
        "marketscope-delta.vercel.app",
      ),
    ).toBe(true);
    expect(isSameOriginMutation("POST", "http://localhost:3200", "localhost:3200")).toBe(true);
  });
  it("refuses writes from other origins or without an origin", () => {
    expect(
      isSameOriginMutation("POST", "https://evil.example", "marketscope-delta.vercel.app"),
    ).toBe(false);
    expect(
      isSameOriginMutation(
        "POST",
        "https://marketscope-delta.vercel.app.evil.example",
        "marketscope-delta.vercel.app",
      ),
    ).toBe(false);
    expect(isSameOriginMutation("POST", null, "marketscope-delta.vercel.app")).toBe(false);
    expect(isSameOriginMutation("POST", "null", "marketscope-delta.vercel.app")).toBe(false);
    expect(isSameOriginMutation("POST", "not a url", "x")).toBe(false);
  });
});
