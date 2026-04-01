"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/api";
import { Spinner } from "@/components/Spinner";

type ImageItem = {
  id: number;
  file_path: string;
  url: string;
  description: string;
  metadata: Record<string, string>;
  annotations: Record<string, unknown>;
  created_at: string;
};

function shortDescription(text: string, max = 120): string {
  const t = text.trim();
  if (!t) return "No description yet.";
  if (t.length <= max) return t;
  return `${t.slice(0, max).trim()}…`;
}

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
    <div className="mx-auto max-w-6xl px-6 py-12">
      <header className="flex flex-col gap-4 border-b border-zinc-200 pb-8 dark:border-zinc-800 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Gallery
          </h1>
          <p className="mt-1 max-w-md text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
            Inspiration images with AI-generated descriptions.
          </p>
        </div>
        <Link
          href="/upload"
          className="inline-flex shrink-0 items-center justify-center rounded-full bg-zinc-900 px-5 py-2.5 text-sm font-medium text-white shadow-sm hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          Upload image
        </Link>
      </header>

      {error ? (
        <p className="mt-10 text-sm text-red-600 dark:text-red-400">{error}</p>
      ) : null}

      {items === null && !error ? (
        <div className="mt-16 flex flex-col items-center justify-center gap-3 text-zinc-500">
          <Spinner />
          <p className="text-sm">Loading gallery…</p>
        </div>
      ) : null}

      {items && items.length === 0 ? (
        <div className="mt-16 rounded-2xl border border-dashed border-zinc-300 bg-zinc-50/50 py-16 text-center dark:border-zinc-600 dark:bg-zinc-900/30">
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            No images yet.{" "}
            <Link href="/upload" className="font-medium text-violet-600 hover:underline dark:text-violet-400">
              Upload your first
            </Link>
            .
          </p>
        </div>
      ) : null}

      {items && items.length > 0 ? (
        <ul className="mt-10 grid grid-cols-1 gap-8 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((img) => (
            <li
              key={img.id}
              className="group overflow-hidden rounded-2xl border border-zinc-200/80 bg-white shadow-sm ring-1 ring-black/[0.04] transition-shadow hover:shadow-md dark:border-zinc-800 dark:bg-zinc-950 dark:ring-white/[0.06]"
            >
              <div className="aspect-[4/3] overflow-hidden bg-zinc-100 dark:bg-zinc-900">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={img.url}
                  alt={shortDescription(img.description, 80)}
                  className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
                  loading="lazy"
                />
              </div>
              <div className="border-t border-zinc-100 p-4 dark:border-zinc-800">
                <p className="line-clamp-3 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
                  {shortDescription(img.description)}
                </p>
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
