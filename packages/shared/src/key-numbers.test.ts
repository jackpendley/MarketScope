import { describe, expect, it } from "vitest";
import { detectKeyNumberCrossings } from "./key-numbers";

describe("detectKeyNumberCrossings", () => {
  it("home -2.5 → -3.5 crosses -3 (the spec's example)", () => {
    expect(detectKeyNumberCrossings(-2.5, -3.5)).toEqual([
      { key: 3, signedKey: -3, kind: "crossed" },
    ]);
  });

  it("detects landing on and leaving a key number", () => {
    expect(detectKeyNumberCrossings(-2.5, -3)).toEqual([
      { key: 3, signedKey: -3, kind: "landed-on" },
    ]);
    expect(detectKeyNumberCrossings(-3, -3.5)).toEqual([{ key: 3, signedKey: -3, kind: "left" }]);
  });

  it("works on the underdog side too", () => {
    expect(detectKeyNumberCrossings(6.5, 7.5)).toEqual([{ key: 7, signedKey: 7, kind: "crossed" }]);
  });

  it("crosses several keys on a big move, in the direction of travel", () => {
    expect(detectKeyNumberCrossings(-2.5, -7.5).map((e) => e.signedKey)).toEqual([-3, -7]);
    expect(detectKeyNumberCrossings(-7.5, -2.5).map((e) => e.signedKey)).toEqual([-7, -3]);
  });

  it("a favorite flipping through pick'em crosses both sides of 3", () => {
    expect(detectKeyNumberCrossings(-3.5, 3.5).map((e) => e.signedKey)).toEqual([-3, 3]);
  });

  it("a move through zero that never reaches 3 crosses nothing", () => {
    expect(detectKeyNumberCrossings(-1.5, 1.5)).toEqual([]);
  });

  it("returns nothing for unchanged or non-key moves", () => {
    expect(detectKeyNumberCrossings(-3, -3)).toEqual([]);
    expect(detectKeyNumberCrossings(-4, -5.5)).toEqual([]);
  });

  it("accepts custom key numbers", () => {
    expect(detectKeyNumberCrossings(-9.5, -10.5, [10])).toEqual([
      { key: 10, signedKey: -10, kind: "crossed" },
    ]);
  });

  it("rejects non-finite input", () => {
    expect(() => detectKeyNumberCrossings(Number.NaN, -3)).toThrow(RangeError);
  });
});
