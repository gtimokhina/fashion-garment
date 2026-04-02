export function getDesignerTags(annotations: Record<string, unknown>): string[] {
  const t = annotations.tags;
  if (Array.isArray(t)) return t.map((x) => String(x).trim()).filter(Boolean);
  return [];
}

export function getDesignerNotes(annotations: Record<string, unknown>): string {
  const n = annotations.notes;
  return typeof n === "string" ? n : "";
}

/** Optional curator-supplied designer/brand (used with the Designer filter). */
export function getDesignerName(annotations: Record<string, unknown>): string {
  const d = annotations.designer;
  return typeof d === "string" ? d.trim() : "";
}
