-- Starter catalog for the inventory: general device categories, component types and a rough parts list
-- for each device category, plus the desktop models Lazarus 2 has processed so far (from its run photos,
-- Oct 16-23 2026) with what the photos show inside them. Load it into a workspace with
--   select public.inventory_seed_starter_catalog('<workspace id>');
-- as an owner/admin in the app, or in the SQL editor. Safe to run again: codes that already exist are
-- left alone, and a category's or model's parts list is only added while it has none. Other models and
-- part numbers are added by people as they come in. Component type codes are the detector's class
-- names; MOTHERBOARD matches what Lazarus already calls it, and CHASSIS is the cut case panels
-- Lazarus drops in its scrap bin.
create or replace function public.inventory_seed_starter_catalog(p_workspace uuid)
returns jsonb language plpgsql security definer set search_path = '' as $$
declare
  device_cats jsonb := '[
    {"code": "COMPUTERS", "name": "Computers"},
    {"code": "DESKTOP", "name": "Desktop computer", "parent": "COMPUTERS", "description": "Towers, small form factor and mini PCs"},
    {"code": "ALL-IN-ONE", "name": "All-in-one computer", "parent": "COMPUTERS", "description": "Computer built into the display, such as an iMac"},
    {"code": "LAPTOP", "name": "Laptop", "parent": "COMPUTERS"},
    {"code": "SERVER", "name": "Server", "parent": "COMPUTERS", "description": "Rack and tower servers"},
    {"code": "MOBILE", "name": "Phones and tablets"},
    {"code": "PHONE", "name": "Mobile phone", "parent": "MOBILE"},
    {"code": "TABLET", "name": "Tablet", "parent": "MOBILE"},
    {"code": "DISPLAYS", "name": "Displays"},
    {"code": "MONITOR", "name": "Monitor", "parent": "DISPLAYS"},
    {"code": "TV", "name": "Television", "parent": "DISPLAYS"},
    {"code": "PERIPHERALS", "name": "Peripherals and networking"},
    {"code": "PRINTER", "name": "Printer or scanner", "parent": "PERIPHERALS"},
    {"code": "NETWORK", "name": "Networking equipment", "parent": "PERIPHERALS", "description": "Routers, switches, modems and access points"},
    {"code": "STORAGE-DEVICE", "name": "External drive or NAS", "parent": "PERIPHERALS"},
    {"code": "INPUT-DEVICE", "name": "Keyboard, mouse or other input device", "parent": "PERIPHERALS"},
    {"code": "POWER-EQUIPMENT", "name": "Power equipment"},
    {"code": "POWER-ADAPTER", "name": "Power adapter or charger", "parent": "POWER-EQUIPMENT"},
    {"code": "UPS", "name": "Uninterruptible power supply (UPS)", "parent": "POWER-EQUIPMENT"},
    {"code": "CONSUMER", "name": "Consumer electronics"},
    {"code": "GAME-CONSOLE", "name": "Game console", "parent": "CONSUMER"},
    {"code": "AUDIO-VIDEO", "name": "Audio and video equipment", "parent": "CONSUMER"},
    {"code": "MIXED", "name": "Mixed or unsorted e-waste", "description": "Loads that haven''t been sorted yet"}
  ]';
  component_types jsonb := '[
    {"code": "BOARDS", "name": "Circuit boards"},
    {"code": "MOTHERBOARD", "name": "Motherboard / logic board", "parent": "BOARDS"},
    {"code": "DAUGHTERBOARD", "name": "Other circuit board", "parent": "BOARDS", "description": "I/O, controller, power and daughter boards"},
    {"code": "GPU", "name": "Graphics card", "parent": "BOARDS"},
    {"code": "RAM", "name": "Memory module", "parent": "BOARDS"},
    {"code": "CPU", "name": "Processor", "parent": "BOARDS"},
    {"code": "STORAGE", "name": "Storage"},
    {"code": "HDD", "name": "Hard drive", "parent": "STORAGE"},
    {"code": "SSD", "name": "Solid-state drive", "parent": "STORAGE"},
    {"code": "OPTICAL-DRIVE", "name": "Optical drive", "parent": "STORAGE"},
    {"code": "POWER", "name": "Power"},
    {"code": "PSU", "name": "Power supply unit", "parent": "POWER"},
    {"code": "BATTERY-LI-ION", "name": "Lithium-ion battery", "parent": "POWER"},
    {"code": "BATTERY-OTHER", "name": "Other battery", "parent": "POWER", "description": "Lead-acid, NiMH and coin cells"},
    {"code": "TRANSFORMER", "name": "Transformer or coil", "parent": "POWER"},
    {"code": "MOVING-AUDIO", "name": "Motors, fans and speakers"},
    {"code": "FAN", "name": "Fan", "parent": "MOVING-AUDIO"},
    {"code": "MOTOR", "name": "Electric motor", "parent": "MOVING-AUDIO"},
    {"code": "SPEAKER", "name": "Speaker", "parent": "MOVING-AUDIO"},
    {"code": "DISPLAY", "name": "Display"},
    {"code": "DISPLAY-PANEL", "name": "Display panel", "parent": "DISPLAY", "description": "LCD or OLED panel"},
    {"code": "OTHER", "name": "Other parts"},
    {"code": "CAMERA-MODULE", "name": "Camera module", "parent": "OTHER"},
    {"code": "HEATSINK", "name": "Heat sink", "parent": "OTHER"},
    {"code": "CABLE", "name": "Cables and wiring", "parent": "OTHER"},
    {"code": "CHASSIS", "name": "Chassis and case panels", "parent": "OTHER", "description": "Steel case and panels; Lazarus drops the cut top face in its scrap bin"}
  ]';
  -- Rough typical counts, to be corrected from real teardowns and scans
  bom jsonb := '{
    "DESKTOP":        {"MOTHERBOARD": 1, "CPU": 1, "RAM": 2, "PSU": 1, "HDD": 0.5, "FAN": 1.5, "HEATSINK": 1, "OPTICAL-DRIVE": 0.5, "CHASSIS": 1},
    "ALL-IN-ONE":     {"MOTHERBOARD": 1, "CPU": 1, "RAM": 2, "PSU": 1, "HDD": 1, "DISPLAY-PANEL": 1, "FAN": 1, "SPEAKER": 2, "HEATSINK": 1, "CAMERA-MODULE": 1},
    "LAPTOP":         {"MOTHERBOARD": 1, "CPU": 1, "RAM": 1, "SSD": 1, "BATTERY-LI-ION": 1, "DISPLAY-PANEL": 1, "FAN": 1, "SPEAKER": 2, "HEATSINK": 1, "CAMERA-MODULE": 1},
    "SERVER":         {"MOTHERBOARD": 1, "CPU": 2, "RAM": 8, "PSU": 2, "HDD": 4, "FAN": 4, "HEATSINK": 2},
    "PHONE":          {"MOTHERBOARD": 1, "BATTERY-LI-ION": 1, "DISPLAY-PANEL": 1, "CAMERA-MODULE": 2, "SPEAKER": 1},
    "TABLET":         {"MOTHERBOARD": 1, "BATTERY-LI-ION": 1, "DISPLAY-PANEL": 1, "CAMERA-MODULE": 2, "SPEAKER": 2},
    "MONITOR":        {"DAUGHTERBOARD": 2, "PSU": 1, "DISPLAY-PANEL": 1},
    "TV":             {"DAUGHTERBOARD": 2, "PSU": 1, "DISPLAY-PANEL": 1, "SPEAKER": 2},
    "PRINTER":        {"DAUGHTERBOARD": 1, "PSU": 1, "MOTOR": 2},
    "NETWORK":        {"MOTHERBOARD": 1},
    "STORAGE-DEVICE": {"HDD": 1, "DAUGHTERBOARD": 1},
    "INPUT-DEVICE":   {"DAUGHTERBOARD": 1, "CABLE": 1},
    "POWER-ADAPTER":  {"DAUGHTERBOARD": 1, "TRANSFORMER": 1, "CABLE": 1},
    "UPS":            {"DAUGHTERBOARD": 1, "BATTERY-OTHER": 1, "TRANSFORMER": 1},
    "GAME-CONSOLE":   {"MOTHERBOARD": 1, "PSU": 1, "FAN": 1, "HEATSINK": 1, "OPTICAL-DRIVE": 1, "HDD": 1},
    "AUDIO-VIDEO":    {"DAUGHTERBOARD": 1, "SPEAKER": 2}
  }';
  -- Desktops in the Lazarus 2 run photos (not every run has photos, and some show only the closed case).
  device_models jsonb := '[
    {"code": "DELL-OPTIPLEX-SFF", "category": "DESKTOP", "manufacturer": "Dell", "name": "OptiPlex (small form factor)",
     "notes": "Seen in the Lazarus 2 run photos, Oct 2026. The generation isn''t readable in the photos: add the model number when known."},
    {"code": "DELL-OPTIPLEX-MT", "category": "DESKTOP", "manufacturer": "Dell", "name": "OptiPlex (mini tower)",
     "notes": "Seen in the Lazarus 2 run photos, Oct 2026. The generation isn''t readable in the photos: add the model number when known."},
    {"code": "HP-DESKTOP-TOWER", "category": "DESKTOP", "manufacturer": "HP", "name": "Desktop tower (Compaq, ProDesk or EliteDesk)",
     "notes": "Seen in the Lazarus 2 run photos, Oct 2026. At least two case layouts, so probably more than one model: split it once the model numbers are known."}
  ]';
  -- What the photos show inside each model. A plain number was seen; [quantity, note] wasn't confirmed.
  model_bom jsonb := '{
    "DELL-OPTIPLEX-SFF": {"MOTHERBOARD": 1, "HEATSINK": 1, "FAN": 1, "PSU": 1, "CHASSIS": 1,
                          "CPU": [1, "Under the cooler, not visible in the photos"],
                          "RAM": [2, "Slots seen; modules not confirmed"],
                          "HDD": [0.5, "Drive bay not visible in the photos"]},
    "DELL-OPTIPLEX-MT":  {"MOTHERBOARD": 1, "HEATSINK": 1, "PSU": 1, "OPTICAL-DRIVE": 1, "CHASSIS": 1,
                          "FAN": [2, "CPU fan seen; rear case fan likely"],
                          "CPU": [1, "Under the cooler, not visible in the photos"],
                          "RAM": [2, "Slots seen; modules not confirmed"],
                          "HDD": [0.3, "Drive bay empty in most photos checked"]},
    "HP-DESKTOP-TOWER":  {"MOTHERBOARD": 1, "HEATSINK": 1, "FAN": 1, "PSU": 1, "CHASSIS": 1,
                          "CPU": [1, "Under the heat sink, not visible in the photos"],
                          "RAM": [2, "Two modules seen in some photos"],
                          "OPTICAL-DRIVE": [0.5, "Seen in some photos"]}
  }';
  n_categories int := 0; n_models int := 0; n_types int := 0; n_bom int := 0; n int;
begin
  if (select auth.uid()) is not null and not public.is_workspace_admin(p_workspace) then
    raise exception 'Only workspace owners/admins can load the starter catalog' using errcode = '42501';
  end if;
  if not exists (select 1 from public.workspaces where id = p_workspace) then
    raise exception 'workspace not found' using errcode = '23503';
  end if;

  -- Top level first, then the entries inside them
  insert into public.device_categories (workspace_id, code, name, description, position)
  select p_workspace, c.code, c.name, c.description, c.ord
    from rows from (jsonb_to_recordset(device_cats) as (code text, name text, parent text, description text))
         with ordinality as c(code, name, parent, description, ord)
   where c.parent is null
  on conflict (workspace_id, code) do nothing;
  get diagnostics n = row_count; n_categories := n_categories + n;
  insert into public.device_categories (workspace_id, parent_id, code, name, description, position)
  select p_workspace, p.id, c.code, c.name, c.description, c.ord
    from rows from (jsonb_to_recordset(device_cats) as (code text, name text, parent text, description text))
         with ordinality as c(code, name, parent, description, ord)
    join public.device_categories p on p.workspace_id = p_workspace and p.code = c.parent
  on conflict (workspace_id, code) do nothing;
  get diagnostics n = row_count; n_categories := n_categories + n;

  insert into public.component_types (workspace_id, code, name, description, position)
  select p_workspace, c.code, c.name, c.description, c.ord
    from rows from (jsonb_to_recordset(component_types) as (code text, name text, parent text, description text))
         with ordinality as c(code, name, parent, description, ord)
   where c.parent is null
  on conflict (workspace_id, code) do nothing;
  get diagnostics n = row_count; n_types := n_types + n;
  insert into public.component_types (workspace_id, parent_id, code, name, description, position)
  select p_workspace, p.id, c.code, c.name, c.description, c.ord
    from rows from (jsonb_to_recordset(component_types) as (code text, name text, parent text, description text))
         with ordinality as c(code, name, parent, description, ord)
    join public.component_types p on p.workspace_id = p_workspace and p.code = c.parent
  on conflict (workspace_id, code) do nothing;
  get diagnostics n = row_count; n_types := n_types + n;

  insert into public.device_bom (workspace_id, device_category_id, component_type_id, quantity, notes)
  select p_workspace, dc.id, ct.id, q.qty::numeric, 'Starter estimate'
    from jsonb_each(bom) as d(category, parts)
   cross join lateral jsonb_each_text(d.parts) as q(component, qty)
    join public.device_categories dc on dc.workspace_id = p_workspace and dc.code = d.category
    join public.component_types ct on ct.workspace_id = p_workspace and ct.code = q.component
   where not exists (select 1 from public.device_bom b where b.device_category_id = dc.id)
  on conflict do nothing;
  get diagnostics n = row_count; n_bom := n_bom + n;

  insert into public.device_models (workspace_id, device_category_id, code, manufacturer, name, notes)
  select p_workspace, dc.id, m.code, m.manufacturer, m.name, m.notes
    from jsonb_to_recordset(device_models) as m(code text, category text, manufacturer text, name text, notes text)
    join public.device_categories dc on dc.workspace_id = p_workspace and dc.code = m.category
  on conflict (workspace_id, code) do nothing;
  get diagnostics n_models = row_count;

  insert into public.device_bom (workspace_id, device_model_id, component_type_id, quantity, notes)
  select p_workspace, dm.id, ct.id,
         case jsonb_typeof(q.v) when 'array' then (q.v->>0)::numeric else (q.v #>> '{}')::numeric end,
         case jsonb_typeof(q.v) when 'array' then q.v->>1 else 'Seen in Lazarus 2 photos (Oct 2026)' end
    from jsonb_each(model_bom) as d(model, parts)
   cross join lateral jsonb_each(d.parts) as q(component, v)
    join public.device_models dm on dm.workspace_id = p_workspace and dm.code = d.model
    join public.component_types ct on ct.workspace_id = p_workspace and ct.code = q.component
   where not exists (select 1 from public.device_bom b where b.device_model_id = dm.id)
  on conflict do nothing;
  get diagnostics n = row_count; n_bom := n_bom + n;

  return jsonb_build_object('device_categories', n_categories, 'device_models', n_models,
                            'component_types', n_types, 'bom_lines', n_bom);
end $$;
revoke execute on function public.inventory_seed_starter_catalog(uuid) from public, anon;
grant execute on function public.inventory_seed_starter_catalog(uuid) to authenticated;
