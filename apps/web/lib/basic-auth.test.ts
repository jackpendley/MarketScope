import { describe, expect, it } from "vitest";
import { basicAuthConfigFromEnv, isAuthorized } from "./basic-auth";

const config = { user: "marketscope", password: "s3cret:with-colon" };
const header = (user: string, password: string) =>
  `Basic ${Buffer.from(`${user}:${password}`).toString("base64")}`;

describe("isAuthorized", () => {
  it("accepts the configured credentials (passwords may contain colons)", () => {
    expect(isAuthorized(header("marketscope", "s3cret:with-colon"), config)).toBe(true);
  });

  it.each([
    ["wrong password", header("marketscope", "nope")],
    ["wrong user", header("admin", "s3cret:with-colon")],
    ["missing header", null],
    ["other scheme", "Bearer abc"],
    ["no separator", `Basic ${Buffer.from("justuser").toString("base64")}`],
    ["empty", "Basic "],
  ])("rejects %s", (_label, value) => {
    expect(isAuthorized(value, config)).toBe(false);
  });
});

describe("basicAuthConfigFromEnv", () => {
  it("is disabled without a password (local dev, e2e)", () => {
    expect(basicAuthConfigFromEnv({})).toBeNull();
  });
  it("defaults the user name", () => {
    expect(basicAuthConfigFromEnv({ BASIC_AUTH_PASSWORD: "x" })).toEqual({
      user: "marketscope",
      password: "x",
    });
  });
});
