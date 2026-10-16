// NFL schedules are conventionally shown in Eastern time. Rendering on the server
// with an explicit zone keeps output deterministic regardless of server locale.
const ZONE = "America/New_York";

const kickoffFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: ZONE,
  weekday: "short",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

const dateHeadingFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: ZONE,
  weekday: "long",
  month: "long",
  day: "numeric",
});

const timestampFormat = new Intl.DateTimeFormat("en-US", {
  timeZone: ZONE,
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  timeZoneName: "short",
});

export const formatKickoff = (iso: string) => kickoffFormat.format(new Date(iso));
export const formatDateHeading = (iso: string) => dateHeadingFormat.format(new Date(iso));
export const formatTimestamp = (iso: string) => timestampFormat.format(new Date(iso));
