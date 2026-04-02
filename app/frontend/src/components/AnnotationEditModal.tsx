"use client";

import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/api";
import { getDesignerName, getDesignerNotes, getDesignerTags } from "@/lib/annotations";

export type AnnotatedItem = {
  id: number;
  annotations: Record<string, unknown>;
};

export function AnnotationEditModal({
  image,
  open,
  onClose,
  onSaved,
}: {
  image: AnnotatedItem | null;
  open: boolean;
  onClose: () => void;
  onSaved: (updated: AnnotatedItem & Record<string, unknown>) => void;
}) {
  const [tagsText, setTagsText] = useState("");
  const [notes, setNotes] = useState("");
  const [designerText, setDesignerText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!image || !open) return;
    setTagsText(getDesignerTags(image.annotations).join(", "));
    setNotes(getDesignerNotes(image.annotations));
    setDesignerText(getDesignerName(image.annotations));
    setError(null);
  }, [image, open]);

  if (!open || !image) return null;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!image) return;
    setSaving(true);
    setError(null);
    const tags = tagsText
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const res = await fetch(`${getApiBase()}/api/images/${image.id}/annotations`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tags, notes, designer: designerText.trim() }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const detail = (data as { detail?: string }).detail;
        throw new Error(typeof detail === "string" ? detail : res.statusText);
      }
      onSaved(data as AnnotatedItem & Record<string, unknown>);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-labelledby="annotation-modal-title"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-6 shadow-xl dark:border-zinc-700 dark:bg-zinc-950">
        <h2 id="annotation-modal-title" className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">
          Edit annotations
        </h2>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Tags, notes, and optional designer are stored separately from AI metadata and included in
          search and filters.
        </p>

        <form onSubmit={onSubmit} className="mt-5 space-y-4">
          <div>
            <label htmlFor="tags" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
              Tags
            </label>
            <input
              id="tags"
              value={tagsText}
              onChange={(e) => setTagsText(e.target.value)}
              placeholder="e.g. resort, ss26, moodboard"
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            />
            <p className="mt-1 text-[10px] text-zinc-500">Comma-separated</p>
          </div>
          <div>
            <label htmlFor="notes" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
              Notes
            </label>
            <textarea
              id="notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={4}
              placeholder="Private observations, sourcing context…"
              className="mt-1 w-full resize-y rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </div>
          <div>
            <label htmlFor="designer" className="text-xs font-medium text-zinc-600 dark:text-zinc-400">
              Designer / brand
            </label>
            <input
              id="designer"
              value={designerText}
              onChange={(e) => setDesignerText(e.target.value)}
              placeholder="e.g. for curation when not in AI metadata"
              className="mt-1 w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-100"
            />
          </div>

          {error ? <p className="text-sm text-red-600 dark:text-red-400">{error}</p> : null}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50 dark:bg-amber-600 dark:hover:bg-amber-500"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
