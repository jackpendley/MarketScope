// Minimal structured logging: one JSON object per line, easy to grep locally and to
// ship to CloudWatch/Datadog later. Never log request URLs or credentials.

type Level = "info" | "warn" | "error";
export type Logger = Record<Level, (event: string, fields?: Record<string, unknown>) => void>;

function emit(level: Level, event: string, fields: Record<string, unknown> = {}) {
  const line = JSON.stringify({ ts: new Date().toISOString(), level, event, ...fields });
  if (level === "error") console.error(line);
  else console.log(line);
}

export const jsonLogger: Logger = {
  info: (event, fields) => emit("info", event, fields),
  warn: (event, fields) => emit("warn", event, fields),
  error: (event, fields) => emit("error", event, fields),
};

export const silentLogger: Logger = { info: () => {}, warn: () => {}, error: () => {} };
