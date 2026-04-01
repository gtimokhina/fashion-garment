export function getApiBase(): string {
  return (
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "")) ||
    "http://127.0.0.1:8000"
  );
}
