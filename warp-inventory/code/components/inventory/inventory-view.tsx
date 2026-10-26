"use client";

import { useMemo, useState, useTransition } from "react";
import { toast } from "sonner";
import { logCutParts, loadStarterCatalog } from "@/lib/actions";
import {
  ALL_PRODUCTS, MAX_LOGGED_PARTS, partGroups, partTiles,
  type ComponentTypeRef, type PartsRow, type Product,
} from "@/lib/inventory";
import { PartsWheel } from "@/components/inventory/parts-wheel";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectGroup, SelectItem, SelectLabel, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

export function InventoryView({ workspaceId, products, parts, componentTypes, isAdmin }: {
  workspaceId: string; products: Product[]; parts: PartsRow[]; componentTypes: ComponentTypeRef[]; isAdmin: boolean;
}) {
  const [selected, setSelected] = useState(ALL_PRODUCTS);
  // A product that disappears on refresh (nothing left for it) falls back to all products
  const product = products.find((p) => p.key === selected) ?? null;
  const tiles = partTiles(parts, componentTypes, product);
  const total = products.reduce((n, p) => n + p.processed, 0);
  const shown = product ? product.processed : total;

  if (!componentTypes.length) return <CatalogEmpty workspaceId={workspaceId} isAdmin={isAdmin} />;

  return (
    <div className="p-4 md:p-6 space-y-5 max-w-6xl">
      <LogPartsForm workspaceId={workspaceId} product={product} componentTypes={componentTypes} />

      <div className="flex flex-wrap items-start gap-6">
        <section aria-labelledby="inv-products" className="flex-[1_1_17rem] min-w-0 space-y-2">
          <div>
            <h2 id="inv-products" className="font-semibold">Processed</h2>
            <p className="text-sm text-muted-foreground">Pick one to see its parts</p>
          </div>
          <ProductButton name="All products" detail={null} count={total} total={total}
            selected={!product} onSelect={() => setSelected(ALL_PRODUCTS)} />
          {products.map((p) => (
            <ProductButton key={p.key} name={p.name} detail={p.detail} count={p.processed} total={total}
              selected={product?.key === p.key} onSelect={() => setSelected(p.key)} />
          ))}
          {!products.length && (
            <p className="pt-1 text-sm text-muted-foreground">No processed devices yet. They show up here once they&apos;re marked processed.</p>
          )}
        </section>

        <section aria-labelledby="inv-parts" className="flex-[999_1_32rem] min-w-0">
          <h2 id="inv-parts" className="font-semibold">Parts to cut from {product ? product.name : "all products"}</h2>
          <p className="mb-3 text-sm text-muted-foreground">
            {shown} processed device{shown === 1 ? "" : "s"}
          </p>
          {tiles.length ? (
            <PartsWheel key={product?.key ?? ALL_PRODUCTS} tiles={tiles} devices={shown} />
          ) : (
            <p className="rounded-lg border border-dashed p-6 text-sm text-muted-foreground">Nothing to cut yet.</p>
          )}
          <p className="mt-3 text-xs text-muted-foreground">Part counts are estimates from each model&apos;s typical parts list.</p>
        </section>
      </div>
    </div>
  );
}

function ProductButton({ name, detail, count, total, selected, onSelect }: {
  name: string; detail: string | null; count: number; total: number; selected: boolean; onSelect: () => void;
}) {
  return (
    <button type="button" aria-pressed={selected} onClick={onSelect}
      className={cn("w-full rounded-lg border px-3.5 py-3 text-left transition-colors hover:bg-accent",
        selected ? "border-primary bg-accent" : "bg-card")}>
      <span className="flex items-baseline justify-between gap-3">
        <span className="min-w-0">
          <span className={cn("block line-clamp-2", selected && "font-semibold")}>{name}</span>
          {detail && <span className="block truncate text-xs text-muted-foreground">{detail}</span>}
        </span>
        <span className="text-xl font-semibold tabular-nums">{count}</span>
      </span>
      <span aria-hidden className="mt-2 block h-1.5 overflow-hidden rounded-full bg-muted">
        <span className="block h-full bg-primary" style={{ width: `${total ? (count / total) * 100 : 0}%` }} />
      </span>
    </button>
  );
}

function LogPartsForm({ workspaceId, product, componentTypes }: {
  workspaceId: string; product: Product | null; componentTypes: ComponentTypeRef[];
}) {
  const groups = useMemo(() => partGroups(componentTypes), [componentTypes]);
  const [part, setPart] = useState("");
  const [qty, setQty] = useState("1");
  const [errors, setErrors] = useState<{ part?: string; qty?: string }>({});
  // One id per entry: a double submit re-sends the same id and is a no-op server-side
  const [draftId, setDraftId] = useState(() => crypto.randomUUID());
  const [pending, start] = useTransition();

  function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (pending) return;
    const n = Number(qty);
    const next = {
      part: part ? undefined : "Choose a part",
      qty: qty.trim() && Number.isInteger(n) && n >= 1 && n <= MAX_LOGGED_PARTS
        ? undefined : `Enter a whole number from 1 to ${MAX_LOGGED_PARTS.toLocaleString("en-US")}`,
    };
    setErrors(next);
    if (next.part || next.qty) return;
    const name = componentTypes.find((t) => t.id === part)?.name ?? "parts";
    start(async () => {
      const res = await logCutParts({
        id: draftId, workspaceId, componentTypeId: part, quantity: n,
        fromDeviceModelId: product?.modelId ?? null,
        fromDeviceCategoryId: product && !product.modelId ? product.categoryId : null,
      });
      if (!res.ok) { toast.error(res.error); return; }
      toast.success(`Added ${n} × ${name}${product ? ` from ${product.name}` : ""}`);
      setDraftId(crypto.randomUUID());
      setPart("");
      setQty("1");
    });
  }

  return (
    <form onSubmit={onSubmit} aria-labelledby="inv-log" noValidate
      className="flex flex-wrap items-end gap-3 rounded-lg border bg-card p-4">
      <div className="flex-[1_1_12rem] min-w-0 self-center">
        <p id="inv-log" className="font-semibold">Log parts cut out</p>
        <p className="truncate text-sm text-muted-foreground">{product ? `From ${product.name}` : "Any device"}</p>
      </div>
      <div className="flex-[2_1_14rem] min-w-0 space-y-1.5">
        <Label htmlFor="inv-part">Part</Label>
        <Select value={part} onValueChange={(v) => { setPart(v); setErrors((e) => ({ ...e, part: undefined })); }} disabled={pending}>
          <SelectTrigger id="inv-part" aria-invalid={!!errors.part} aria-describedby={errors.part ? "inv-error" : undefined}
            className={cn("w-full", errors.part && "border-destructive")}>
            <SelectValue placeholder="Choose a part" />
          </SelectTrigger>
          <SelectContent>
            {groups.map((g) => (
              <SelectGroup key={g.label}>
                <SelectLabel>{g.label}</SelectLabel>
                {g.items.map((t) => <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>)}
              </SelectGroup>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex-[0_1_7rem] min-w-24 space-y-1.5">
        <Label htmlFor="inv-qty">How many</Label>
        <Input id="inv-qty" type="number" inputMode="numeric" step={1} min={1} max={MAX_LOGGED_PARTS} value={qty} disabled={pending}
          aria-invalid={!!errors.qty} aria-describedby={errors.qty ? "inv-error" : undefined}
          onChange={(e) => { setQty(e.target.value); setErrors((x) => ({ ...x, qty: undefined })); }}
          className={cn(errors.qty && "border-destructive")} />
      </div>
      <Button type="submit" disabled={pending}>{pending ? "Adding…" : "Add"}</Button>
      {(errors.part || errors.qty) && (
        <p id="inv-error" role="alert" className="basis-full text-sm text-destructive">{errors.part ?? errors.qty}</p>
      )}
    </form>
  );
}

function CatalogEmpty({ workspaceId, isAdmin }: { workspaceId: string; isAdmin: boolean }) {
  const [pending, start] = useTransition();
  return (
    <div className="p-4 md:p-6">
      <div className="max-w-xl rounded-lg border bg-card p-5">
        <h2 className="font-semibold">Start with the catalog</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Inventory counts devices and the parts inside them, so it needs a list of device types and parts first.
          The starter catalog has general categories, component types and the desktops Lazarus has processed.
        </p>
        {isAdmin ? (
          <Button className="mt-4" disabled={pending} onClick={() => start(async () => {
            const res = await loadStarterCatalog(workspaceId);
            if (!res.ok) toast.error(res.error); else toast.success("Starter catalog loaded");
          })}>
            {pending ? "Loading…" : "Load the starter catalog"}
          </Button>
        ) : (
          <p className="mt-3 text-sm">Ask a workspace owner or admin to load it.</p>
        )}
      </div>
    </div>
  );
}
