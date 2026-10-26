// Inventory page data (shared by the server page and the client view): processed devices grouped
// by product, and the parts still to cut from them.

/** Row of the inventory_parts_to_cut RPC. Parts logged without a source device have no category. */
export type PartsRow = {
  device_category_id: string | null; device_model_id: string | null; component_type_id: string;
  expected: number; cut: number;
};
export type StockRow = { device_category_id: string | null; device_model_id: string | null; processed: number | null };
export type CategoryRef = { id: string; name: string };
export type ModelRef = { id: string; device_category_id: string; manufacturer: string | null; name: string };
export type ComponentTypeRef = { id: string; code: string; name: string; parent_id: string | null };

/** A kind of processed device: a model, or a category when the model isn't known. */
export type Product = { key: string; name: string; detail: string; processed: number; categoryId: string; modelId: string | null };
export type PartTile = { componentTypeId: string; code: string; name: string; expected: number; cut: number; left: number; done: boolean };

/** Short labels for the parts wheel, where a slice has room for a word or two. */
const SHORT_PART_NAMES: Record<string, string> = {
  MOTHERBOARD: "Motherboard", DAUGHTERBOARD: "Other board", "OPTICAL-DRIVE": "Optical drive", PSU: "Power supply",
  "BATTERY-LI-ION": "Li-ion battery", "BATTERY-OTHER": "Battery", "DISPLAY-PANEL": "Display", "CAMERA-MODULE": "Camera",
  HEATSINK: "Heat sink", CABLE: "Cables", CHASSIS: "Case panels", RAM: "RAM", CPU: "CPU", GPU: "GPU", HDD: "Hard drive", SSD: "SSD",
};
export const shortPartName = (t: Pick<PartTile, "code" | "name">) => SHORT_PART_NAMES[t.code] ?? t.name;

export const ALL_PRODUCTS = "all";
export const MAX_LOGGED_PARTS = 10000;
const productKey = (categoryId: string, modelId: string | null) => modelId ?? `category:${categoryId}`;

export function buildProducts(stock: StockRow[], parts: PartsRow[], categories: CategoryRef[], models: ModelRef[]): Product[] {
  const categoryName = new Map(categories.map((c) => [c.id, c.name]));
  const model = new Map(models.map((m) => [m.id, m]));
  const out = new Map<string, Product>();
  const add = (categoryId: string | null, modelId: string | null, processed: number) => {
    if (!categoryId) return;
    const key = productKey(categoryId, modelId);
    const p = out.get(key);
    if (p) { p.processed += processed; return; }
    const m = modelId ? model.get(modelId) : undefined;
    out.set(key, {
      key, categoryId, modelId, processed,
      name: m ? [m.manufacturer, m.name].filter(Boolean).join(" ") : categoryName.get(categoryId) ?? "Unknown device",
      detail: m ? categoryName.get(categoryId) ?? "" : "Model not set",
    });
  };
  for (const s of stock) if ((s.processed ?? 0) > 0) add(s.device_category_id, s.device_model_id, s.processed ?? 0);
  // Parts logged against a kind of device nothing has been processed for yet still get a row
  for (const r of parts) if (r.cut > 0) add(r.device_category_id, r.device_model_id, 0);
  return [...out.values()].sort((a, b) => b.processed - a.processed || a.name.localeCompare(b.name));
}

/** Parts to cut for one product, or for everything (product = null, including parts with no source),
 *  in catalog order so the wheel's slices stay put as counts change. */
export function partTiles(parts: PartsRow[], types: ComponentTypeRef[], product: Product | null): PartTile[] {
  const type = new Map(types.map((t, i) => [t.id, { ...t, order: i }]));
  const sum = new Map<string, { expected: number; cut: number }>();
  for (const r of parts) {
    if (product && (product.modelId
      ? r.device_model_id !== product.modelId
      : r.device_model_id !== null || r.device_category_id !== product.categoryId)) continue;
    const s = sum.get(r.component_type_id) ?? { expected: 0, cut: 0 };
    s.expected += Number(r.expected); s.cut += Number(r.cut);
    sum.set(r.component_type_id, s);
  }
  const order = (id: string) => type.get(id)?.order ?? Number.MAX_SAFE_INTEGER;
  return [...sum.entries()].map(([id, s]) => {
    const expected = Math.round(s.expected);
    const left = Math.max(expected - s.cut, 0);
    return { componentTypeId: id, code: type.get(id)?.code ?? "", name: type.get(id)?.name ?? "Unknown part",
             expected, cut: s.cut, left, done: expected > 0 && left === 0 };
  }).filter((t) => t.expected > 0 || t.cut > 0)
    .sort((a, b) => order(a.componentTypeId) - order(b.componentTypeId));
}

/** Component types for the part picker: top-level types are groups, the types inside them items. */
export function partGroups(types: ComponentTypeRef[]): { label: string; items: ComponentTypeRef[] }[] {
  const children = new Map<string, ComponentTypeRef[]>();
  for (const t of types) if (t.parent_id) children.set(t.parent_id, [...(children.get(t.parent_id) ?? []), t]);
  const groups = types.filter((t) => !t.parent_id && children.has(t.id)).map((t) => ({ label: t.name, items: children.get(t.id)! }));
  const loose = types.filter((t) => !t.parent_id && !children.has(t.id));
  return loose.length ? [...groups, { label: "Other", items: loose }] : groups;
}
