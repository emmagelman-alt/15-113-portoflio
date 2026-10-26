"use server";

// Excerpt of Warp's lib/actions.ts: the shared sign-in check and the two Inventory actions.
// The rest of the file (projects, tasks, members) isn't part of the inventory and is left out.

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { isAllowedEmail } from "@/lib/auth-domain";
import { MAX_LOGGED_PARTS } from "@/lib/inventory";

type Result<T = null> = { ok: true; data: T } | { ok: false; error: string };

async function requireUser() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getClaims();
  if (!data?.claims) redirect("/auth/login");
  if (!isAllowedEmail(data.claims.email)) {
    await supabase.auth.signOut();
    redirect("/auth/login?error=domain");
  }
  return { supabase, userId: data.claims.sub as string };
}

/** Logs parts cut out by hand (Inventory page). A model, else a category, says what they came from. */
export async function logCutParts(input: {
  id: string; workspaceId: string; componentTypeId: string; quantity: number;
  fromDeviceModelId?: string | null; fromDeviceCategoryId?: string | null;
}): Promise<Result> {
  const { supabase } = await requireUser();
  if (!Number.isInteger(input.quantity) || input.quantity < 1 || input.quantity > MAX_LOGGED_PARTS)
    return { ok: false, error: `Enter a whole number from 1 to ${MAX_LOGGED_PARTS.toLocaleString("en-US")}.` };
  const { error } = await supabase.from("inventory_movements").insert({
    id: input.id, workspace_id: input.workspaceId, item_kind: "component", reason: "recovered",
    component_type_id: input.componentTypeId, quantity: input.quantity,
    from_device_model_id: input.fromDeviceModelId ?? null,
    from_device_category_id: input.fromDeviceModelId ? null : input.fromDeviceCategoryId ?? null,
  });
  // Client-generated id: a retried submit hits the primary key instead of logging the parts twice
  if (error && error.code !== "23505") return { ok: false, error: error.message };
  revalidatePath(`/w/${input.workspaceId}/inventory`);
  return { ok: true, data: null };
}

/** Loads the starter catalog (device categories, models, component types, parts lists). Owners/admins. */
export async function loadStarterCatalog(workspaceId: string): Promise<Result> {
  const { supabase } = await requireUser();
  const { error } = await supabase.rpc("inventory_seed_starter_catalog", { p_workspace: workspaceId });
  if (error) return { ok: false, error: error.message };
  revalidatePath(`/w/${workspaceId}/inventory`);
  return { ok: true, data: null };
}
