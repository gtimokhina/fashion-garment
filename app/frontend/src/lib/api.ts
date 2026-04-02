export function getApiBase(): string {
  return (
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "")) ||
    "http://127.0.0.1:8000"
  );
}

/** Stored paths are like `uploads/<file>`; serve from the API origin (matches ``NEXT_PUBLIC_API_URL``). */
export function imagePublicUrl(filePath: string): string {
  const path = filePath.replace(/^\/+/, "");
  return `${getApiBase()}/${path}`;
}
