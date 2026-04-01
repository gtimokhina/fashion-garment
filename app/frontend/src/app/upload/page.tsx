"use client";

import { useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/api";

export default function UploadPage() {
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = e.currentTarget;
    const input = form.elements.namedItem("file") as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) {
      setStatus("error");
      setMessage("Choose a file first.");
      return;
    }

    setStatus("uploading");
    setMessage("");

    const body = new FormData();
    body.append("file", file);

    try {
      const res = await fetch(`${getApiBase()}/api/images/upload`, {
        method: "POST",
        body,
      });
      if (!res.ok) {
        const err = (await res.json().catch(() => ({}))) as { detail?: string };
        throw new Error(err.detail ?? res.statusText);
      }
      setStatus("done");
      setMessage("Upload saved.");
      input.value = "";
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Upload failed");
    }
  }

  return (
    <div className="mx-auto max-w-lg px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
        Upload
      </h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        JPEG, PNG, GIF, or WebP. Files are stored on the API server under{" "}
        <code className="rounded bg-zinc-100 px-1 text-xs dark:bg-zinc-900">uploads/</code>.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <input
          name="file"
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          className="block w-full text-sm text-zinc-600 file:mr-4 file:rounded-md file:border-0 file:bg-zinc-900 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-zinc-800 dark:text-zinc-400 dark:file:bg-zinc-100 dark:file:text-zinc-900 dark:hover:file:bg-zinc-200"
        />
        <button
          type="submit"
          disabled={status === "uploading"}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 disabled:opacity-50 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          {status === "uploading" ? "Uploading…" : "Upload"}
        </button>
      </form>

      {message ? (
        <p
          className={`mt-4 text-sm ${status === "error" ? "text-red-600 dark:text-red-400" : "text-zinc-600 dark:text-zinc-400"}`}
        >
          {message}
        </p>
      ) : null}

      {status === "done" ? (
        <p className="mt-4 text-sm">
          <Link href="/gallery" className="font-medium text-zinc-900 underline dark:text-zinc-100">
            View gallery
          </Link>
        </p>
      ) : null}
    </div>
  );
}
