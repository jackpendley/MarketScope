import { describe, expect, it } from "vitest";
import { requiresTls, usesTransactionPooler } from "./client";

describe("requiresTls", () => {
  it("requires TLS for remote hosts", () => {
    expect(requiresTls("postgresql://aws-0-us-east-1.pooler.supabase.com:5432/postgres")).toBe(
      true,
    );
  });
  it("skips TLS for local databases", () => {
    expect(requiresTls("postgres://localhost:5432/marketscope_dev")).toBe(false);
    expect(requiresTls("postgres://postgres@127.0.0.1:5432/x")).toBe(false);
  });
  it("defers to an explicit sslmode", () => {
    expect(requiresTls("postgresql://db.example.com/x?sslmode=verify-full")).toBe(false);
  });
});

describe("usesTransactionPooler", () => {
  it("detects the Supabase transaction pooler port", () => {
    expect(
      usesTransactionPooler("postgresql://aws-0-us-east-1.pooler.supabase.com:6543/postgres"),
    ).toBe(true);
    expect(
      usesTransactionPooler("postgresql://aws-0-us-east-1.pooler.supabase.com:5432/postgres"),
    ).toBe(false);
    expect(usesTransactionPooler("postgres://localhost/marketscope_dev")).toBe(false);
  });
});
