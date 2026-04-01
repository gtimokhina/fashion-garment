"use client";

import { useEffect, useState } from "react";

const defaultBase = "http://127.0.0.1:8000";

function healthUrl(): string {
  const base =
    (typeof process !== "undefined" &&
      process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "")) ||
    defaultBase;
  return `${base}/health`;
}

export function ApiStatus() {
  const [state, setState] = useState<"loading" | "ok" | "error">("loading");
  const [detail, setDetail] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

    fetch(healthUrl())
      .then(async (res) => {
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        const body = (await res.json()) as { status?: string };
        if (cancelled) return;
        if (body.status === "ok") {
          setState("ok");
          setDetail("Backend reachable.");
        } else {
          setState("error");
          setDetail("Unexpected response.");
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setState("error");
        setDetail(e instanceof Error ? e.message : "Request failed");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const label =
    state === "loading" ? "Checking API…" : state === "ok" ? "API: ok" : "API: unreachable";

  return (
    <div
      className="rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-800 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-200"
      role="status"
    >
      <p className="font-medium">{label}</p>
      {detail ? (
        <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">{detail}</p>
      ) : null}
      <p className="mt-2 text-xs text-zinc-500">
        {healthUrl()} — start backend with{" "}
        <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-900">
          uvicorn main:app --reload
        </code>{" "}
        from <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-900">app/backend</code>
      </p>
    </div>
  );
}
