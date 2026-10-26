import { createClient } from "@/lib/supabase/server";
import { MobileNavSlot } from "@/components/app/mobile-nav";
import { InventoryView } from "@/components/inventory/inventory-view";
import { buildProducts, type PartsRow } from "@/lib/inventory";

export const metadata = { title: "Inventory" };

/** PostgREST: table or function not in the schema cache; Postgres: relation does not exist. */
const NOT_SET_UP = new Set(["PGRST202", "PGRST205", "42P01", "42883"]);

export default async function InventoryPage({ params }: { params: Promise<{ workspaceId: string }> }) {
  const { workspaceId } = await params;
  const supabase = await createClient();
  const [stock, parts, categories, models, types, { data: role }] = await Promise.all([
    supabase.from("inventory_device_stock").select("device_category_id,device_model_id,processed").eq("workspace_id", workspaceId),
    supabase.rpc("inventory_parts_to_cut", { p_workspace: workspaceId }),
    supabase.from("device_categories").select("id,name").eq("workspace_id", workspaceId),
    supabase.from("device_models").select("id,device_category_id,manufacturer,name").eq("workspace_id", workspaceId),
    supabase.from("component_types").select("id,code,name,parent_id").eq("workspace_id", workspaceId)
      .is("archived_at", null).order("position").order("name"),
    supabase.rpc("workspace_role", { ws: workspaceId }),
  ]);
  const error = [stock, parts, categories, models, types].find((r) => r.error)?.error;
  const partsRows = (parts.data ?? []) as unknown as PartsRow[];

  return (
    <div className="flex-1 overflow-y-auto">
      <header className="h-14 border-b flex items-center gap-3 px-4 md:px-6">
        <MobileNavSlot />
        <div className="flex-1 min-w-0">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground leading-none">Data</div>
          <h1 className="font-semibold truncate">Inventory</h1>
        </div>
      </header>
      {error ? (
        <div className="p-4 md:p-6">
          <div className="max-w-xl rounded-lg border bg-card p-5 text-sm">
            <p className="font-medium">{NOT_SET_UP.has(error.code) ? "Inventory isn't set up in this database yet" : "Couldn't load the inventory"}</p>
            <p className="mt-1 text-muted-foreground">
              {NOT_SET_UP.has(error.code)
                ? "Apply the inventory migrations in supabase/migrations, then reload this page."
                : error.message}
            </p>
          </div>
        </div>
      ) : (
        <InventoryView
          workspaceId={workspaceId}
          products={buildProducts(stock.data ?? [], partsRows, categories.data ?? [], models.data ?? [])}
          parts={partsRows}
          componentTypes={types.data ?? []}
          isAdmin={role === "owner" || role === "admin"}
        />
      )}
    </div>
  );
}
