"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/api";
import { Spinner } from "@/components/Spinner";

const ACCEPT = "image/jpeg,image/png,image/gif,image/webp";

function parseErrorDetail(data: unknown): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d)) return JSON.stringify(d);
  }
  return "Request failed";
}

export default function UploadPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [status, setStatus] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  const uploadFile = useCallback(async (file: File) => {
    if (!file.type.match(/^image\/(jpeg|png|gif|webp)$/i)) {
      setStatus("error");
      setMessage("Use JPEG, PNG, GIF, or WebP.");
      return;
    }

    setStatus("uploading");
    setMessage("Analyzing with AI…");

    const body = new FormData();
    body.append("file", file);

    try {
      const res = await fetch(`${getApiBase()}/api/images/upload`, {
        method: "POST",
        body,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(parseErrorDetail(data) || res.statusText);
      }
      setStatus("done");
      setMessage("Saved to the library.");
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      setStatus("error");
      setMessage(err instanceof Error ? err.message : "Upload failed");
    }
  }, []);


  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const file = inputRef.current?.files?.[0];
    if (!file) {
      setStatus("error");
      setMessage("Choose or drop a file first.");
      return;
    }
    void uploadFile(file);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    if (status === "uploading") return;
    const file = e.dataTransfer.files?.[0];
    if (file) void uploadFile(file);
  }

  return (
    <div className="mx-auto max-w-xl px-6 py-12">
      <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
        Upload
      </h1>
      <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
        Drop an inspiration image here or browse. We classify it and add it to your gallery.
      </p>

      <form onSubmit={onSubmit} className="mt-8 space-y-6">
        <div
          onDragEnter={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOver(false);
          }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={onDrop}
          className={[
            "relative rounded-2xl border-2 border-dashed px-6 py-14 text-center transition-colors",
            status === "uploading" && "pointer-events-none opacity-80",
            dragOver
              ? "border-violet-500 bg-violet-50/60 dark:border-violet-400 dark:bg-violet-950/30"
              : "border-zinc-300 bg-zinc-50/80 dark:border-zinc-600 dark:bg-zinc-900/40",
          ].join(" ")}
        >
          {status === "uploading" ? (
            <div className="flex flex-col items-center gap-4">
              <Spinner className="h-10 w-10 border-[3px]" />
              <p className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Uploading &amp; classifying…
              </p>
            </div>
          ) : (
            <>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                Drag and drop an image
              </p>
              <p className="mt-1 text-xs text-zinc-500">or</p>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="mt-4 rounded-full bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                Choose file
              </button>
            </>
          )}
          <input
            ref={inputRef}
            name="file"
            type="file"
            accept={ACCEPT}
            className="hidden"
            disabled={status === "uploading"}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void uploadFile(f);
            }}
          />
        </div>

        <button
          type="submit"
          disabled={status === "uploading"}
          className="w-full rounded-xl border border-zinc-300 bg-white py-3 text-sm font-medium text-zinc-800 shadow-sm hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-200 dark:hover:bg-zinc-900"
        >
          Upload selected file
        </button>
      </form>

      {message && status !== "uploading" ? (
        <p
          className={`mt-4 text-sm ${status === "error" ? "text-red-600 dark:text-red-400" : "text-zinc-600 dark:text-zinc-400"}`}
        >
          {message}
        </p>
      ) : null}

      {status === "done" ? (
        <p className="mt-6 text-center text-sm">
          <Link
            href="/gallery"
            className="font-medium text-violet-600 underline decoration-violet-300 underline-offset-4 hover:text-violet-700 dark:text-violet-400 dark:decoration-violet-700 dark:hover:text-violet-300"
          >
            Open gallery
          </Link>
        </p>
      ) : null}
    </div>
  );
}
