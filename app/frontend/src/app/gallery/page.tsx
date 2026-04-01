"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/api";

type ImageItem = {
  id: number;
  file_path: string;
  url: string;
  description: string;
  metadata: Record<string, string>;
  annotations: Record<string, unknown>;
  created_at: string;
};

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
            Full records from <code className="text-xs">GET /api/images</code> (AI metadata +
            annotations).
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
        <ul className="mt-8 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((img) => (
            <li
              key={img.id}
              className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={img.url}
                alt={img.description.slice(0, 80) || img.file_path}
                className="aspect-square w-full object-cover"
                loading="lazy"
              />
              <div className="space-y-1 border-t border-zinc-100 p-3 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
                <p className="line-clamp-3 text-sm text-zinc-800 dark:text-zinc-200">
                  {img.description || "—"}
                </p>
                <p className="font-mono text-[10px] text-zinc-500">
                  {img.metadata.garment_type}
                  {img.metadata.style ? ` · ${img.metadata.style}` : ""}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
