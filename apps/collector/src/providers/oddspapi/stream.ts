// Streaming parse of an OddsPapi historical-odds response (ADR-076).
//
// `res.json()` turns the whole body into one string first, and V8 strings stop at about 512 MB: a busy
// exchange's full history for one game can be larger (ADR-071). This parses the byte stream
// incrementally and keeps only the markets the importer uses (full-game spreads, totals and moneylines),
// so memory grows with those entries, not with the response. Path inside the JSON:
// bookmakers.<book>.markets.<market>.outcomes.<outcome>.players.0[*].
import { JSONParser } from "@streamparser/json";
import type { OddsPapiEntry, OddsPapiHistory } from "./transform";

const ENTRY_PATH = "$.bookmakers.*.markets.*.outcomes.*.players.0.*";

export async function parseHistoryStream(
  body: AsyncIterable<Uint8Array> | ReadableStream<Uint8Array>,
  keepMarkets: ReadonlySet<number>,
): Promise<OddsPapiHistory> {
  const history: OddsPapiHistory = { bookmakers: {} };
  const parser = new JSONParser({ paths: [ENTRY_PATH], keepStack: false });
  parser.onValue = ({ value, stack }) => {
    const book = String(stack[2]?.key);
    const market = String(stack[4]?.key);
    const outcome = String(stack[6]?.key);
    if (!keepMarkets.has(Number(market))) return;
    const markets = (history.bookmakers[book] ??= { markets: {} }).markets;
    const outcomes = (markets[market] ??= { outcomes: {} }).outcomes;
    ((outcomes[outcome] ??= { players: { "0": [] } }).players["0"] ??= []).push(
      value as unknown as OddsPapiEntry,
    );
  };
  const iterable =
    Symbol.asyncIterator in body
      ? (body as AsyncIterable<Uint8Array>)
      : streamIterator(body as ReadableStream<Uint8Array>);
  for await (const chunk of iterable) parser.write(chunk);
  if (!parser.isEnded) parser.end();
  return history;
}

async function* streamIterator(stream: ReadableStream<Uint8Array>) {
  const reader = stream.getReader();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return;
      yield value;
    }
  } finally {
    reader.releaseLock();
  }
}
