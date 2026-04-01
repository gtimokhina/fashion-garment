"use client";

import { useCallback, useEffect, useState } from "react";
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

type Facets = {
  garment_types: string[];
  styles: string[];
  occasions: string[];
  color_palettes: string[];
};

function shortDescription(text: string, max = 120): string {
  const t = text.trim();
  if (!t) return "No description yet.";
  if (t.length <= max) return t;
  return `${t.slice(0, max).trim()}…`;
}

function buildImagesQuery(params: {
  garment_type: string;
  style: string;
  occasion: string;
  color_palette: string;
  q: string;
}): string {
  const p = new URLSearchParams();
  if (params.garment_type) p.set("garment_type", params.garment_type);
  if (params.style) p.set("style", params.style);
  if (params.occasion) p.set("occasion", params.occasion);
  if (params.color_palette) p.set("color_palette", params.color_palette);
  if (params.q) p.set("q", params.q);
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

export default function GalleryPage() {
  const [items, setItems] = useState<ImageItem[] | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [imagesError, setImagesError] = useState<string | null>(null);
  const [facetsError, setFacetsError] = useState<string | null>(null);

  const [garmentType, setGarmentType] = useState("");
  const [style, setStyle] = useState("");
  const [occasion, setOccasion] = useState("");
  const [colorPalette, setColorPalette] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(searchInput), 320);
    return () => clearTimeout(t);
  }, [searchInput]);

  const loadFacets = useCallback(async () => {
    const res = await fetch(`${getApiBase()}/api/images/facets`);
    if (!res.ok) throw new Error("Failed to load filters");
    return res.json() as Promise<Facets>;
  }, []);

  const loadImages = useCallback(
    async (q: { garment_type: string; style: string; occasion: string; color_palette: string; q: string }) => {
      const res = await fetch(`${getApiBase()}/api/images${buildImagesQuery(q)}`);
      if (!res.ok) throw new Error(res.statusText);
      return res.json() as Promise<{ items: ImageItem[] }>;
    },
    [],
  );

  useEffect(() => {
    let cancelled = false;
    loadFacets()
      .then((f) => {
        if (!cancelled) {
          setFacets(f);
          setFacetsError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setFacetsError(e instanceof Error ? e.message : "Failed to load filters");
      });
    return () => {
      cancelled = true;
    };
  }, [loadFacets]);

  useEffect(() => {
    let cancelled = false;
    loadImages({
      garment_type: garmentType,
      style,
      occasion,
      color_palette: colorPalette,
      q: debouncedQ,
    })
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
          setImagesError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled)
          setImagesError(e instanceof Error ? e.message : "Failed to load images");
      });
    return () => {
      cancelled = true;
    };
  }, [loadImages, garmentType, style, occasion, colorPalette, debouncedQ]);

  function clearFilters() {
    setGarmentType("");
    setStyle("");
    setOccasion("");
    setColorPalette("");
    setSearchInput("");
    setDebouncedQ("");
  }

  const filtersActive =
    Boolean(garmentType || style || occasion || colorPalette || debouncedQ);

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-7xl flex-col gap-8 px-6 py-10 lg:flex-row">
      <aside className="w-full shrink-0 space-y-6 lg:sticky lg:top-6 lg:w-72 lg:self-start">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Gallery
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Filter by AI metadata or search descriptions.
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="search" className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Search description
          </label>
          <input
            id="search"
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="e.g. denim, studio…"
            className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm placeholder:text-zinc-400 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
          />
        </div>

        <div className="space-y-4 rounded-2xl border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-900/40">
          {facetsError ? (
            <p className="text-xs text-amber-700 dark:text-amber-400">{facetsError}</p>
          ) : null}

          <FilterSelect
            label="Garment type"
            value={garmentType}
            onChange={setGarmentType}
            options={facets?.garment_types ?? []}
            disabled={!facets}
          />
          <FilterSelect
            label="Style"
            value={style}
            onChange={setStyle}
            options={facets?.styles ?? []}
            disabled={!facets}
          />
          <FilterSelect
            label="Occasion"
            value={occasion}
            onChange={setOccasion}
            options={facets?.occasions ?? []}
            disabled={!facets}
          />
          <FilterSelect
            label="Color palette"
            value={colorPalette}
            onChange={setColorPalette}
            options={facets?.color_palettes ?? []}
            disabled={!facets}
            hint="Match inside stored palette text."
          />

          <button
            type="button"
            onClick={clearFilters}
            className="w-full rounded-lg border border-zinc-300 py-2 text-sm font-medium text-zinc-700 hover:bg-white dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-950"
          >
            Clear filters
          </button>
        </div>

        <Link
          href="/upload"
          className="inline-flex w-full items-center justify-center rounded-full bg-zinc-900 py-2.5 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-zinc-200"
        >
          Upload image
        </Link>
      </aside>

      <section className="min-w-0 flex-1">
        {imagesError ? (
          <p className="text-sm text-red-600 dark:text-red-400">{imagesError}</p>
        ) : null}

        {items === null && !imagesError ? (
          <div className="flex flex-col items-center justify-center gap-3 py-20 text-zinc-500">
            <Spinner />
            <p className="text-sm">Loading gallery…</p>
          </div>
        ) : null}

        {items && items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-zinc-300 bg-zinc-50/50 py-20 text-center dark:border-zinc-600 dark:bg-zinc-900/30">
            <p className="text-sm text-zinc-600 dark:text-zinc-400">
              No images match.{" "}
              <button
                type="button"
                onClick={clearFilters}
                className="font-medium text-violet-600 hover:underline dark:text-violet-400"
              >
                Reset filters
              </button>{" "}
              or{" "}
              <Link href="/upload" className="font-medium text-violet-600 hover:underline dark:text-violet-400">
                upload
              </Link>
              .
            </p>
          </div>
        ) : null}

        {items && items.length > 0 ? (
          <>
            <p className="mb-6 text-sm text-zinc-500">
              {items.length} result{items.length === 1 ? "" : "s"}
              {filtersActive ? " · filtered" : ""}
            </p>
            <ul className="grid grid-cols-1 gap-8 sm:grid-cols-2 xl:grid-cols-3">
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
          </>
        ) : null}
      </section>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
  hint,
  disabled,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">{label}</label>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-zinc-300 bg-white px-2 py-2 text-sm text-zinc-900 focus:border-violet-500 focus:outline-none focus:ring-1 focus:ring-violet-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
      >
        <option value="">Any</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
      {hint ? <p className="text-[10px] leading-snug text-zinc-500">{hint}</p> : null}
    </div>
  );
}
