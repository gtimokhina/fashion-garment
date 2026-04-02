"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import Link from "next/link";
import { getApiBase } from "@/lib/api";
import { getDesignerName, getDesignerNotes, getDesignerTags } from "@/lib/annotations";
import { AnnotationEditModal } from "@/components/AnnotationEditModal";
import { Spinner } from "@/components/Spinner";

type ImageItem = {
  id: number;
  file_path: string;
  url: string;
  description: string;
  /** Structured AI fields: ``{ value, confidence }`` or legacy plain strings. */
  metadata: Record<string, unknown>;
  /** Raw JSON from the vision model when stored; omitted or null for older rows. */
  ai_raw_response?: string | null;
  annotations: Record<string, unknown>;
  created_at: string;
  /** Embedding cosine similarity (0–1) when semantic / hybrid search is used. */
  semantic_score?: number | null;
  /** Lexical match 0 or 1 when hybrid search is used. */
  keyword_score?: number | null;
  /** Hybrid combined score: 0.5×keyword + 0.5×embedding when hybrid mode. */
  combined_score?: number | null;
};

type FacetOption = { value: string; count: number };

type Facets = {
  garment_types: FacetOption[];
  styles: FacetOption[];
  materials: FacetOption[];
  color_palettes: FacetOption[];
  patterns: FacetOption[];
  seasons: FacetOption[];
  occasions: FacetOption[];
  consumer_profiles: FacetOption[];
  trend_notes: FacetOption[];
  location_contexts: FacetOption[];
};

/** Query param names (must match backend ``META_FILTER_KEYS``). */
const FILTER_PARAM_KEYS = [
  "garment_type",
  "style",
  "material",
  "color_palette",
  "pattern",
  "season",
  "occasion",
  "consumer_profile",
  "trend_notes",
  "location_context",
] as const;

type FilterParamKey = (typeof FILTER_PARAM_KEYS)[number];

const FACET_OPTIONS_KEY: Record<FilterParamKey, keyof Facets> = {
  garment_type: "garment_types",
  style: "styles",
  material: "materials",
  color_palette: "color_palettes",
  pattern: "patterns",
  season: "seasons",
  occasion: "occasions",
  consumer_profile: "consumer_profiles",
  trend_notes: "trend_notes",
  location_context: "location_contexts",
};

function emptyFilters(): Record<FilterParamKey, string> {
  return Object.fromEntries(FILTER_PARAM_KEYS.map((k) => [k, ""])) as Record<FilterParamKey, string>;
}

/** Mirrors backend ``metadata_fields.heuristic_confidence_for_value`` for legacy rows. */
const UNCERTAINTY_HINTS =
  /\b(unknown|unclear|not\s+visible|cannot\s+(see|determine)|n\/?a|none\s+visible)\b/i;

function heuristicConfidenceForValue(value: string): number {
  const v = value.trim();
  if (!v) return 0;
  if (UNCERTAINTY_HINTS.test(v)) return 0.35;
  const words = Math.min(
    v.split(/\s+/).filter((w) => w.length > 0).length,
    12,
  );
  return Math.min(0.95, 0.5 + Math.min(0.45, 0.04 * words));
}

function metaFieldDisplay(raw: unknown): { value: string; confidence: number } {
  if (raw !== null && typeof raw === "object" && "value" in raw) {
    const o = raw as { value?: unknown; confidence?: unknown };
    const value = typeof o.value === "string" ? o.value : String(o.value ?? "");
    const c = o.confidence;
    if (typeof c === "number" && !Number.isNaN(c)) {
      return { value, confidence: Math.max(0, Math.min(1, c)) };
    }
    return { value, confidence: heuristicConfidenceForValue(value) };
  }
  const s = raw == null ? "" : String(raw);
  return { value: s, confidence: heuristicConfidenceForValue(s) };
}

const AI_META_ORDER = [
  "garment_type",
  "style",
  "material",
  "color_palette",
  "pattern",
  "season",
  "occasion",
  "consumer_profile",
  "trend_notes",
  "location_context",
  "location_continent",
  "location_country",
  "location_city",
  "time_year",
  "time_month",
  "designer",
] as const;

const AI_META_LABELS: Record<(typeof AI_META_ORDER)[number], string> = {
  garment_type: "Garment type",
  style: "Style",
  material: "Material",
  color_palette: "Color palette",
  pattern: "Pattern",
  season: "Season",
  occasion: "Occasion",
  consumer_profile: "Consumer profile",
  trend_notes: "Trend notes",
  location_context: "Location (scene)",
  location_continent: "Continent",
  location_country: "Country",
  location_city: "City",
  time_year: "Year",
  time_month: "Month",
  designer: "Designer / brand",
};

function altFromDescription(text: string, max = 100): string {
  const t = text.trim();
  if (!t) return "Fashion inspiration image";
  return t.length <= max ? t : `${t.slice(0, max).trim()}…`;
}

function buildImagesQuery(filters: Record<FilterParamKey, string>, q: string, semantic: boolean): string {
  const p = new URLSearchParams();
  for (const key of FILTER_PARAM_KEYS) {
    const v = filters[key]?.trim();
    if (v) p.set(key, v);
  }
  if (q) p.set("q", q);
  if (semantic) p.set("semantic", "1");
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

function buildFacetsQuery(filters: Record<FilterParamKey, string>): string {
  const p = new URLSearchParams();
  for (const key of FILTER_PARAM_KEYS) {
    const v = filters[key]?.trim();
    if (v) p.set(key, v);
  }
  const qs = p.toString();
  return qs ? `?${qs}` : "";
}

export default function GalleryPage() {
  const [editingImage, setEditingImage] = useState<ImageItem | null>(null);
  const [items, setItems] = useState<ImageItem[] | null>(null);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [imagesError, setImagesError] = useState<string | null>(null);
  const [facetsError, setFacetsError] = useState<string | null>(null);

  const [filters, setFilters] = useState<Record<FilterParamKey, string>>(emptyFilters);
  const [searchInput, setSearchInput] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [semanticSearch, setSemanticSearch] = useState(false);
  const [keywordFallback, setKeywordFallback] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(searchInput), 320);
    return () => clearTimeout(t);
  }, [searchInput]);

  const loadFacets = useCallback(async () => {
    const res = await fetch(`${getApiBase()}/api/images/facets${buildFacetsQuery(filters)}`);
    if (!res.ok) throw new Error("Failed to load filters");
    return res.json() as Promise<Facets>;
  }, [filters]);

  const loadImages = useCallback(
    async (f: Record<FilterParamKey, string>, q: string, semantic: boolean) => {
      const res = await fetch(`${getApiBase()}/api/images${buildImagesQuery(f, q, semantic)}`);
      if (!res.ok) throw new Error(res.statusText);
      return res.json() as Promise<{
        items: ImageItem[];
        keyword_fallback?: boolean | null;
      }>;
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
    loadImages(filters, debouncedQ, semanticSearch)
      .then((data) => {
        if (!cancelled) {
          setItems(data.items);
          setKeywordFallback(Boolean(data.keyword_fallback));
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
  }, [loadImages, filters, debouncedQ, semanticSearch]);

  function setFilter(key: FilterParamKey, value: string) {
    setFilters((prev) => ({ ...prev, [key]: value }));
  }

  function clearFilters() {
    setFilters(emptyFilters());
    setSearchInput("");
    setDebouncedQ("");
    setSemanticSearch(false);
    setKeywordFallback(false);
  }

  const filtersActive = useMemo(() => {
    const meta = FILTER_PARAM_KEYS.some((k) => filters[k]?.trim());
    return meta || debouncedQ.trim() !== "" || semanticSearch;
  }, [filters, debouncedQ, semanticSearch]);

  function onAnnotationSaved(row: ImageItem) {
    setItems((prev) =>
      prev
        ? prev.map((x) =>
            x.id === row.id
              ? {
                  ...row,
                  ai_raw_response: row.ai_raw_response ?? x.ai_raw_response,
                  semantic_score: x.semantic_score,
                  keyword_score: x.keyword_score,
                  combined_score: x.combined_score,
                }
              : x,
          )
        : null,
    );
  }

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-7xl flex-col gap-8 px-6 py-10 lg:flex-row">
      <aside className="w-full shrink-0 space-y-6 lg:sticky lg:top-6 lg:max-h-[calc(100vh-5rem)] lg:w-[22rem] lg:overflow-y-auto lg:self-start xl:w-96">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Gallery
          </h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
            Filter by AI attributes. With <strong>Semantic search</strong>,
            results are ranked by a <strong>hybrid score</strong> (50% keyword overlap + 50% description
            embedding similarity; see Score % on cards).
          </p>
        </div>

        <div className="space-y-2">
          <label htmlFor="search" className="text-xs font-medium uppercase tracking-wide text-zinc-500">
            Search
          </label>
          <input
            id="search"
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="e.g. denim, studio…"
            className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 shadow-sm placeholder:text-zinc-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
          />
          <label className="flex cursor-pointer items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
            <input
              type="checkbox"
              checked={semanticSearch}
              onChange={(e) => setSemanticSearch(e.target.checked)}
              className="rounded border-zinc-400 text-blue-600 focus:ring-blue-500 dark:border-zinc-600 dark:bg-zinc-900"
            />
            <span title="Hybrid ranking: 0.5×keyword (description/notes/tags substring) + 0.5×embedding cosine. Tunable via HYBRID_* and SEMANTIC_* in backend .env.">
              Semantic search
            </span>
          </label>
        </div>

        <div className="space-y-4 rounded-2xl border border-zinc-200 bg-zinc-50/80 p-4 dark:border-zinc-800 dark:bg-zinc-900/40">
          {facetsError ? (
            <p className="text-xs text-amber-700 dark:text-amber-400">{facetsError}</p>
          ) : null}

          <FilterSection title="Garment">
            <FilterSelect
              label="Garment type"
              value={filters.garment_type}
              onChange={(v) => setFilter("garment_type", v)}
              options={facets?.garment_types ?? []}
              disabled={!facets}
            />
            <FilterSelect
              label="Material"
              value={filters.material}
              onChange={(v) => setFilter("material", v)}
              options={facets?.materials ?? []}
              disabled={!facets}
            />
            <FilterSelect
              label="Pattern"
              value={filters.pattern}
              onChange={(v) => setFilter("pattern", v)}
              options={facets?.patterns ?? []}
              disabled={!facets}
            />
            <FilterSelect
              label="Color palette"
              value={filters.color_palette}
              onChange={(v) => setFilter("color_palette", v)}
              options={facets?.color_palettes ?? []}
              disabled={!facets}
              hint="Substring match on stored palette text."
            />
          </FilterSection>

          <FilterSection title="Style & audience">
            <FilterSelect
              label="Style"
              value={filters.style}
              onChange={(v) => setFilter("style", v)}
              options={facets?.styles ?? []}
              disabled={!facets}
            />
            <FilterSelect
              label="Occasion"
              value={filters.occasion}
              onChange={(v) => setFilter("occasion", v)}
              options={facets?.occasions ?? []}
              disabled={!facets}
            />
            <FilterSelect
              label="Consumer profile"
              value={filters.consumer_profile}
              onChange={(v) => setFilter("consumer_profile", v)}
              options={facets?.consumer_profiles ?? []}
              disabled={!facets}
            />
            <FilterSelect
              label="Trend notes"
              value={filters.trend_notes}
              onChange={(v) => setFilter("trend_notes", v)}
              options={facets?.trend_notes ?? []}
              disabled={!facets}
            />
          </FilterSection>

          <FilterSection title="Location">
            <FilterSelect
              label="Scene / context"
              value={filters.location_context}
              onChange={(v) => setFilter("location_context", v)}
              options={facets?.location_contexts ?? []}
              disabled={!facets}
            />
          </FilterSection>

          <FilterSection title="Time">
            <FilterSelect
              label="Season"
              value={filters.season}
              onChange={(v) => setFilter("season", v)}
              options={facets?.seasons ?? []}
              disabled={!facets}
            />
          </FilterSection>

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
        <AnnotationEditModal
          image={editingImage}
          open={editingImage !== null}
          onClose={() => setEditingImage(null)}
          onSaved={(data) => onAnnotationSaved(data as ImageItem)}
        />

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
                className="font-medium text-blue-600 hover:underline dark:text-blue-400"
              >
                Reset filters
              </button>{" "}
              or{" "}
              <Link href="/upload" className="font-medium text-blue-600 hover:underline dark:text-blue-400">
                upload
              </Link>
              .
            </p>
          </div>
        ) : null}

        {items && items.length > 0 ? (
          <>
            {keywordFallback && semanticSearch && debouncedQ.trim() ? (
              <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50/80 px-3 py-2 text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100/95">
                No rows met the hybrid score threshold — showing plain text matches (description,
                notes, tags) instead.
              </p>
            ) : null}
            <p className="mb-6 text-sm text-zinc-500">
              {items.length} result{items.length === 1 ? "" : "s"}
              {filtersActive ? " · filtered" : ""}
            </p>
            <ul className="grid grid-cols-1 gap-8 sm:grid-cols-2 xl:grid-cols-3">
              {items.map((img) => (
                <li
                  key={img.id}
                  className="group relative overflow-hidden rounded-2xl border border-zinc-200/80 bg-white shadow-sm ring-1 ring-black/[0.04] transition-shadow hover:shadow-md dark:border-zinc-800 dark:bg-zinc-950 dark:ring-white/[0.06]"
                >
                  {typeof img.combined_score === "number" &&
                  semanticSearch &&
                  debouncedQ.trim() &&
                  !keywordFallback ? (
                    <span
                      className="absolute left-3 top-3 z-10 max-w-[11rem] rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-blue-700 shadow-sm ring-1 ring-blue-200/80 dark:bg-zinc-900/90 dark:text-blue-300 dark:ring-blue-900/60"
                      title={`Combined = 0.5×keyword + 0.5×embedding. Keyword=${((img.keyword_score ?? 0) * 100).toFixed(0)}%, embedding=${((img.semantic_score ?? 0) * 100).toFixed(0)}%.`}
                    >
                      Score {(img.combined_score * 100).toFixed(0)}%
                    </span>
                  ) : typeof img.semantic_score === "number" &&
                    img.semantic_score > 0 &&
                    semanticSearch &&
                    debouncedQ.trim() &&
                    !keywordFallback &&
                    img.combined_score == null ? (
                    <span
                      className="absolute left-3 top-3 z-10 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-blue-700 shadow-sm ring-1 ring-blue-200/80 dark:bg-zinc-900/90 dark:text-blue-300 dark:ring-blue-900/60"
                      title="Embedding-only mode (hybrid=false): cosine similarity to query embedding"
                    >
                      Match {(img.semantic_score * 100).toFixed(0)}%
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setEditingImage(img)}
                    className="absolute right-3 top-3 z-10 rounded-full bg-white/90 px-3 py-1 text-xs font-medium text-zinc-800 shadow-sm ring-1 ring-zinc-200 backdrop-blur hover:bg-white dark:bg-zinc-900/90 dark:text-zinc-100 dark:ring-zinc-700"
                  >
                    Edit
                  </button>
                  <div className="aspect-[4/3] overflow-hidden bg-zinc-100 dark:bg-zinc-900">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={img.url}
                      alt={altFromDescription(img.description)}
                      className="h-full w-full object-cover transition duration-300 group-hover:scale-[1.02]"
                      loading="lazy"
                    />
                  </div>
                  <div className="space-y-3 border-t border-zinc-100 p-4 dark:border-zinc-800">
                    <DescriptionBlock description={img.description} />
                    <AiAttributesCollapsible metadata={img.metadata} rawJson={img.ai_raw_response} />
                    <div
                      className="my-1 border-t border-dashed border-zinc-200 pt-3 dark:border-zinc-700"
                      role="separator"
                      aria-hidden
                    />
                    <DesignerAnnotationsBlock annotations={img.annotations} />
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

function AiAttributesCollapsible({
  metadata,
  rawJson,
}: {
  metadata: Record<string, unknown>;
  rawJson: string | null | undefined;
}) {
  const [open, setOpen] = useState(false);
  const rows = useMemo(
    () =>
      AI_META_ORDER.map((key) => {
        const { value, confidence } = metaFieldDisplay(metadata[key]);
        return { key, label: AI_META_LABELS[key], value, confidence };
      }).filter((r) => r.value.trim().length > 0),
    [metadata],
  );
  const hasRaw = Boolean(rawJson?.trim());
  if (rows.length === 0 && !hasRaw) {
    return null;
  }

  return (
    <div className="rounded-xl border border-blue-200/80 bg-blue-50/40 dark:border-blue-900/50 dark:bg-blue-950/20">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-xl px-3 py-2.5 text-left text-xs font-medium text-blue-900 hover:bg-blue-100/50 dark:text-blue-100 dark:hover:bg-blue-950/40"
      >
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-300">
            AI Attributes
          </span>
          {rows.length > 0 ? (
            <span className="tabular-nums text-zinc-500 dark:text-zinc-500">({rows.length})</span>
          ) : null}
        </span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-4 w-4 shrink-0 text-blue-600 transition-transform duration-200 dark:text-blue-400 ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open ? (
        <div className="space-y-3 border-t border-blue-200/60 px-3 pb-3 pt-1 dark:border-blue-900/50">
          {rows.length > 0 ? (
            <dl className="space-y-1.5 text-xs">
              {rows.map((r) => (
                <div key={r.key} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                  <dt className="shrink-0 font-medium text-zinc-600 dark:text-zinc-400">{r.label}</dt>
                  <dd className="min-w-0 flex-1 text-right text-zinc-800 dark:text-zinc-200">
                    <span className="break-words">{r.value}</span>
                    <span
                      className="ml-2 tabular-nums text-zinc-500 dark:text-zinc-500"
                      title="Model-reported or estimated confidence (0–1); see backend metadata_fields module."
                    >
                      {(r.confidence * 100).toFixed(0)}%
                    </span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : null}
          <AiDetailsPanel rawJson={rawJson} parsedMetadata={metadata} />
        </div>
      ) : null}
    </div>
  );
}

function AiDetailsPanel({
  rawJson,
  parsedMetadata,
}: {
  rawJson: string | null | undefined;
  parsedMetadata: Record<string, unknown>;
}) {
  const [open, setOpen] = useState(false);
  const parsedStr = useMemo(() => {
    try {
      return JSON.stringify(parsedMetadata, null, 2);
    } catch {
      return "{}";
    }
  }, [parsedMetadata]);

  return (
    <div className="rounded-lg border border-slate-200/90 bg-slate-50/80 p-2 dark:border-slate-700/80 dark:bg-slate-950/40">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left text-xs font-medium text-slate-800 hover:bg-slate-100/80 dark:text-slate-200 dark:hover:bg-slate-900/60"
      >
        <span>View AI details</span>
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`h-4 w-4 shrink-0 text-slate-500 transition-transform duration-200 ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
            clipRule="evenodd"
          />
        </svg>
      </button>
      {open ? (
        <div className="space-y-4 border-t border-slate-200/80 px-2 pb-3 pt-3 dark:border-slate-700/80">
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
              Raw model output
            </p>
            <pre className="mt-1 max-h-56 overflow-auto rounded-lg bg-white p-2.5 text-[11px] leading-relaxed text-slate-800 [overflow-wrap:anywhere] whitespace-pre-wrap ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-200 dark:ring-slate-700">
              {rawJson?.trim()
                ? rawJson
                : "No raw response stored for this image (e.g. older uploads before this feature)."}
            </pre>
          </div>
          <div>
            <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-400">
              Parsed structured metadata
            </p>
            <pre className="mt-1 max-h-56 overflow-auto rounded-lg bg-white p-2.5 text-[11px] leading-relaxed text-slate-800 [overflow-wrap:anywhere] whitespace-pre-wrap ring-1 ring-slate-200 dark:bg-slate-900 dark:text-slate-200 dark:ring-slate-700">
              {parsedStr}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

/** Long descriptions collapse to 3 lines; chevron toggles full text. */
function DescriptionBlock({ description }: { description: string }) {
  const [expanded, setExpanded] = useState(false);
  const trimmed = description.trim();
  const body = trimmed || "No description yet.";
  const collapsible = trimmed.length > 200;

  return (
    <div>
      <div className="flex items-start justify-between gap-2">
        <p className="text-[10px] font-semibold uppercase tracking-wide text-blue-600 dark:text-blue-400">
          Description
        </p>
        {collapsible ? (
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="-mr-1 -mt-0.5 shrink-0 rounded-md p-1 text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/40"
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse description" : "Expand description"}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`h-4 w-4 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
              aria-hidden
            >
              <path
                fillRule="evenodd"
                d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
                clipRule="evenodd"
              />
            </svg>
          </button>
        ) : null}
      </div>
      <p
        className={`mt-1 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300 ${
          collapsible && !expanded ? "line-clamp-3" : ""
        }`}
      >
        {body}
      </p>
    </div>
  );
}

function DesignerAnnotationsBlock({ annotations }: { annotations: Record<string, unknown> }) {
  const tags = getDesignerTags(annotations);
  const notes = getDesignerNotes(annotations);
  const designer = getDesignerName(annotations);
  const has = tags.length > 0 || notes.trim().length > 0 || designer.length > 0;
  return (
    <div
      className={`rounded-xl border p-3 ${has ? "border-amber-200/90 bg-amber-50/60 dark:border-amber-900/60 dark:bg-amber-950/25" : "border-dashed border-zinc-200 bg-zinc-50/50 dark:border-zinc-700 dark:bg-zinc-900/40"}`}
    >
      <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-800 dark:text-amber-200/90">
        Annotations
      </p>
      {!has ? (
        <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-500">
          None yet — use Edit to add tags, notes, or designer.
        </p>
      ) : (
        <>
          {designer ? (
            <p className="mt-1 text-xs font-medium text-amber-950 dark:text-amber-100/95">
              Designer: {designer}
            </p>
          ) : null}
          {tags.length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {tags.map((t, i) => (
                <li
                  key={`${i}-${t}`}
                  className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-950 dark:bg-amber-900/55 dark:text-amber-50"
                >
                  {t}
                </li>
              ))}
            </ul>
          ) : null}
          {notes.trim() ? (
            <p className="mt-2 text-xs leading-relaxed text-amber-950 dark:text-amber-100/95">{notes}</p>
          ) : null}
        </>
      )}
    </div>
  );
}

function FilterSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-500">
        {title}
      </p>
      <div className="space-y-3">{children}</div>
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
  options: FacetOption[];
  hint?: string;
  disabled?: boolean;
}) {
  const displayOptions = useMemo(() => {
    if (!value) return options;
    const has = options.some((o) => o.value === value);
    if (has) return options;
    return [{ value, count: 0 }, ...options];
  }, [options, value]);

  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-zinc-600 dark:text-zinc-400">{label}</label>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-zinc-300 bg-white px-2 py-2 text-sm text-zinc-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-600 dark:bg-zinc-950 dark:text-zinc-100"
      >
        <option value="">Any</option>
        {displayOptions.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.value} ({opt.count})
          </option>
        ))}
      </select>
      {hint ? <p className="text-[10px] leading-snug text-zinc-500">{hint}</p> : null}
    </div>
  );
}
