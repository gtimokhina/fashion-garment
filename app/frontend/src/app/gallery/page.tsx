"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/api";

type ImageItem = { id: number; filename: string; url: string };

export default function GalleryPage() {
  const [items, setItems] = useState<ImageItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`${getApiBase()}/api/images`)
      .then(async (res) => {
        if (!res.ok) throw new Error(res.statusText);
        return res.json() as Promise<{ items: ImageItem[] }>;
      })
      .then((data) => {
        if (!cancelled) setItems(data.items);
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Failed to load images");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-5xl px-6 py-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Gallery
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Images returned from <code className="text-xs">GET /api/images</code>.
          </p>
        </div>
        <Link
          href="/upload"
          className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-800 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-900"
        >
          Upload
        </Link>
      </div>

      {error ? (
        <p className="mt-8 text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : null}

      {items === null && !error ? (
        <p className="mt-8 text-sm text-zinc-500">Loading…</p>
      ) : null}

      {items && items.length === 0 ? (
        <p className="mt-8 text-sm text-zinc-600 dark:text-zinc-400">
          No images yet.{" "}
          <Link href="/upload" className="font-medium underline">
            Upload one
          </Link>
          .
        </p>
      ) : null}

      {items && items.length > 0 ? (
        <ul className="mt-8 grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
          {items.map((img) => (
            <li
              key={img.id}
              className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.url}
                alt={img.filename}
                className="aspect-square w-full object-cover"
                loading="lazy"
              />
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
