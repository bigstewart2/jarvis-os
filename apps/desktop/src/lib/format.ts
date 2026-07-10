export function greeting(now: Date = new Date()): string {
  const hour = now.getHours();
  if (hour < 5) return "Up late, Stephen";
  if (hour < 12) return "Good morning, Stephen";
  if (hour < 18) return "Good afternoon, Stephen";
  return "Good evening, Stephen";
}

export function longDate(now: Date = new Date()): string {
  return now.toLocaleDateString(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  });
}

export function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const seconds = Math.round((Date.now() - then) / 1000);
  const future = seconds < 0;
  const s = Math.abs(seconds);
  let value: string;
  if (s < 60) value = "moments";
  else if (s < 3600) value = `${Math.round(s / 60)}m`;
  else if (s < 86400) value = `${Math.round(s / 3600)}h`;
  else value = `${Math.round(s / 86400)}d`;
  if (value === "moments") return future ? "in moments" : "moments ago";
  return future ? `in ${value}` : `${value} ago`;
}

export function eventTime(iso: string): string {
  if (!iso) return "";
  // All-day events come through as bare dates.
  if (!iso.includes("T")) return "all day";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
