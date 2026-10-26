-- Inventory (/w/[id]/inventory): what e-waste comes in, what's inside it, and what gets cut out.
--
-- catalog     device_categories -> device_models and component_types -> components, plus device_bom:
--             the parts usually inside a model, or inside a typical device of a category. Two levels
--             on each side, so anything can be recorded before its exact model or part is known.
-- intake      intake_batches (a delivery or pallet) and intake_lines ("50 desktops", "400 kg laptops").
-- processing  units: one device, or a tray of them, carrying a printed label through the X-ray and
--             Lazarus (lazarus_runs.unit_id). xray_scans: one X-ray image (one view) of a unit.
--             scan_detections: components found in a scan, drawn by a person or found by the model.
-- matching    component_reference_images: labelled crops with embeddings (pgvector) that the model
--             matches new detections against (match_components).
-- stock       inventory_movements: a log that only grows. Intake lines and processed units write to
--             it through triggers; people add recovered, extracted and adjustment rows. The counts
--             are views over it, so a correction is a new row, never an edit.
-- science     component_yield_tests: copper and gold recovered from a sample of a component.
--
-- The X-ray PC uploads through the 'xray-ingest' Edge Function (docs/xray-ingest.md) with the same
-- device tokens as Lazarus. The analysis worker (service role) takes queued scans with claim_xray_scans().

create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------- catalog
create table public.device_categories (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  parent_id uuid references public.device_categories(id) on delete restrict,
  code text not null check (code ~ '^[A-Z0-9][A-Z0-9-]{0,63}$'),
  name text not null check (char_length(btrim(name)) between 1 and 120),
  description text check (description is null or char_length(description) <= 2000),
  position double precision not null default 0,
  archived_at timestamptz,
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, code)
);
create index device_categories_parent_idx on public.device_categories (parent_id) where parent_id is not null;

create table public.device_models (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  device_category_id uuid not null references public.device_categories(id) on delete restrict,
  code text check (code is null or code ~ '^[A-Z0-9][A-Z0-9-]{0,63}$'),
  manufacturer text check (manufacturer is null or char_length(manufacturer) <= 120),
  name text not null check (char_length(btrim(name)) between 1 and 200),             -- iMac 27-inch (2019)
  model_number text check (model_number is null or char_length(model_number) <= 120), -- A2115
  year smallint check (year is null or year between 1950 and 2100),
  aliases text[] not null default '{}',                                               -- other names, for search
  notes text check (notes is null or char_length(notes) <= 4000),
  archived_at timestamptz,
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, code)
);
create index device_models_category_idx on public.device_models (workspace_id, device_category_id);

create table public.component_types (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  parent_id uuid references public.component_types(id) on delete restrict,
  code text not null check (code ~ '^[A-Z0-9][A-Z0-9-]{0,63}$'),   -- also the detector's class name
  name text not null check (char_length(btrim(name)) between 1 and 120),
  description text check (description is null or char_length(description) <= 2000),
  typical_mass_g numeric(12,3) check (typical_mass_g is null or typical_mass_g > 0),
  position double precision not null default 0,
  archived_at timestamptz,
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, code)
);
create index component_types_parent_idx on public.component_types (parent_id) where parent_id is not null;

create table public.components (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  component_type_id uuid not null references public.component_types(id) on delete restrict,
  code text check (code is null or code ~ '^[A-Z0-9][A-Z0-9-]{0,63}$'),
  manufacturer text check (manufacturer is null or char_length(manufacturer) <= 120),
  name text not null check (char_length(btrim(name)) between 1 and 200),
  part_number text check (part_number is null or char_length(part_number) <= 120),
  typical_mass_g numeric(12,3) check (typical_mass_g is null or typical_mass_g > 0),
  notes text check (notes is null or char_length(notes) <= 4000),
  archived_at timestamptz,
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, code)
);
create index components_type_idx on public.components (workspace_id, component_type_id);

-- Parts list. A line belongs to a model, or to a category for devices whose model isn't known (or has
-- no list of its own). quantity is a typical count and may be fractional: 0.5 = about half have one.
create table public.device_bom (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  device_category_id uuid references public.device_categories(id) on delete cascade,
  device_model_id uuid references public.device_models(id) on delete cascade,
  component_type_id uuid not null references public.component_types(id) on delete restrict,
  component_id uuid references public.components(id) on delete restrict,
  quantity numeric(10,2) not null check (quantity > 0),
  notes text check (notes is null or char_length(notes) <= 1000),
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint device_bom_one_owner check (num_nonnulls(device_category_id, device_model_id) = 1)
);
create unique index device_bom_line_uq on public.device_bom
  (device_category_id, device_model_id, component_type_id, component_id) nulls not distinct;
create index device_bom_model_idx on public.device_bom (device_model_id) where device_model_id is not null;

-- ---------------------------------------------------------------- intake
create table public.intake_batches (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  received_at timestamptz not null default now(),
  source text check (source is null or char_length(source) <= 200),          -- supplier, donor or client
  reference text check (reference is null or char_length(reference) <= 200),  -- PO, manifest or pallet number
  notes text check (notes is null or char_length(notes) <= 4000),
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index intake_batches_ws_idx on public.intake_batches (workspace_id, received_at desc);

-- A count, a weight or both. workspace_id comes from the batch, device_category_id from the model.
create table public.intake_lines (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references public.intake_batches(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  device_category_id uuid not null references public.device_categories(id) on delete restrict,
  device_model_id uuid references public.device_models(id) on delete restrict,
  quantity integer check (quantity is null or quantity >= 0),
  weight_kg numeric(12,3) check (weight_kg is null or weight_kg >= 0),
  notes text check (notes is null or char_length(notes) <= 4000),
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint intake_lines_amount check (quantity is not null or weight_kg is not null)
);
create index intake_lines_batch_idx on public.intake_lines (batch_id);
create index intake_lines_ws_idx on public.intake_lines (workspace_id, device_category_id);

-- ---------------------------------------------------------------- units
-- The thing on the tray: usually one device, sometimes several of a kind (a tray of phones). Its code
-- goes on the printed label. The device type may be filled in after the X-ray upload, but a unit
-- needs one before it can be marked processed (which takes its devices out of stock).
create sequence public.units_code_seq;
create table public.units (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  code text not null default ('U-' || to_char(nextval('public.units_code_seq'), 'FM000000'))
    check (code ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'),
  device_category_id uuid references public.device_categories(id) on delete restrict,
  device_model_id uuid references public.device_models(id) on delete restrict,
  device_count integer not null default 1 check (device_count between 1 and 10000),
  intake_line_id uuid references public.intake_lines(id) on delete set null,
  status text not null default 'open' check (status in ('open', 'processed', 'void')),
  started_at timestamptz not null default now(),
  processed_at timestamptz,
  notes text check (notes is null or char_length(notes) <= 4000),
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (workspace_id, code),
  constraint units_processed_has_type check (status <> 'processed' or device_category_id is not null)
);
create index units_ws_idx on public.units (workspace_id, started_at desc);
create index units_intake_idx on public.units (intake_line_id) where intake_line_id is not null;
grant usage on sequence public.units_code_seq to authenticated, service_role;

alter table public.lazarus_runs add column unit_id uuid references public.units(id) on delete set null;
create index lazarus_runs_unit_idx on public.lazarus_runs (unit_id) where unit_id is not null;

-- ---------------------------------------------------------------- X-ray scans
-- One image (one view) of a unit. The original is kept as the X-ray wrote it (often 16-bit TIFF or
-- DICOM, which browsers can't show); preview_path is an 8-bit PNG/JPEG for Warp. Files live in the
-- private 'xray-scans' bucket at <workspace_id>/<scan_id>/<file>.
-- Coordinates: boxes are in pixels of the original image, origin top-left. bed_transform is a 3x3
-- homography (row-major) from those pixels to Lazarus bed millimetres, set once the scan is registered
-- against markers on the tray that both machines can see.
create table public.xray_scans (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  unit_id uuid references public.units(id) on delete set null,
  device_id uuid references public.lazarus_devices(id) on delete set null,   -- the uploading PC; null from Warp
  external_scan_id text check (external_scan_id is null or char_length(external_scan_id) between 1 and 200),
  view text check (view is null or char_length(view) between 1 and 40),     -- top, side, ...
  captured_at timestamptz not null default now(),
  storage_path text not null unique,
  filename text not null check (char_length(filename) between 1 and 255),
  content_type text check (content_type is null or char_length(content_type) <= 100),
  size_bytes bigint check (size_bytes is null or size_bytes between 0 and 104857600),
  width int check (width is null or width > 0),
  height int check (height is null or height > 0),
  bit_depth smallint check (bit_depth is null or bit_depth between 1 and 32),
  preview_path text unique,
  pixel_size_mm numeric(10,5) check (pixel_size_mm is null or pixel_size_mm > 0),
  registered boolean not null default false,
  bed_transform double precision[] check (bed_transform is null or (array_ndims(bed_transform) = 1 and cardinality(bed_transform) = 9)),
  status text not null default 'uploading' check (status in ('uploading', 'queued', 'analyzing', 'analyzed', 'failed')),
  analysis_model text check (analysis_model is null or char_length(analysis_model) <= 120),
  analysis_error text check (analysis_error is null or char_length(analysis_error) <= 4000),
  analysis_started_at timestamptz,
  analyzed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),   -- kV, mA, exposure, vendor fields
  notes text check (notes is null or char_length(notes) <= 4000),
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (device_id, external_scan_id),
  constraint xray_scan_path_scoped check (storage_path like workspace_id::text || '/' || id::text || '/%'),
  constraint xray_preview_path_scoped check (preview_path is null or preview_path like workspace_id::text || '/' || id::text || '/%')
);
create index xray_scans_ws_idx on public.xray_scans (workspace_id, captured_at desc);
create index xray_scans_unit_idx on public.xray_scans (unit_id) where unit_id is not null;
create index xray_scans_queue_idx on public.xray_scans (captured_at) where status in ('queued', 'analyzing');

-- Status: a person's box is 'confirmed' (or 'rejected'). The model's are 'auto' (sure enough to count)
-- or 'needs_review' (shown in the review queue, not counted). Any change a person makes is a review;
-- predicted_* keep the model's first answer, so its accuracy can be measured against the corrections.
create table public.scan_detections (
  id uuid primary key default gen_random_uuid(),
  scan_id uuid not null references public.xray_scans(id) on delete cascade,
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  component_type_id uuid not null references public.component_types(id) on delete restrict,
  component_id uuid references public.components(id) on delete restrict,
  x numeric(10,2) not null check (x >= 0),
  y numeric(10,2) not null check (y >= 0),
  w numeric(10,2) not null check (w > 0),
  h numeric(10,2) not null check (h > 0),
  polygon jsonb check (polygon is null or jsonb_typeof(polygon) = 'array'),   -- [[x, y], ...] in the same pixels
  source text not null default 'human' check (source in ('human', 'model')),
  model_version text check (model_version is null or char_length(model_version) <= 120),
  confidence real check (confidence is null or confidence between 0 and 1),
  predicted_component_type_id uuid references public.component_types(id) on delete set null,
  predicted_component_id uuid references public.components(id) on delete set null,
  status text not null default 'confirmed' check (status in ('auto', 'needs_review', 'confirmed', 'rejected')),
  reviewed_by uuid references public.profiles(id) on delete set null,
  reviewed_at timestamptz,
  metadata jsonb not null default '{}'::jsonb check (jsonb_typeof(metadata) = 'object'),   -- match candidates, distances
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scan_detections_human_status check (source = 'model' or status in ('confirmed', 'rejected'))
);
create index scan_detections_scan_idx on public.scan_detections (scan_id);
create index scan_detections_type_idx on public.scan_detections (workspace_id, component_type_id);
create index scan_detections_review_idx on public.scan_detections (workspace_id, created_at) where status = 'needs_review';

-- ---------------------------------------------------------------- reference crops
-- A crop of a known component: a confirmed detection, or a separate image file in 'xray-scans'.
-- Embeddings can be any length; each row says which model made it, and matches only compare rows
-- from the same model. No vector index yet: exact search is fast at this size. Once a model is
-- chosen, add an HNSW expression index for its dimension (cast embedding to vector(n)).
create table public.component_reference_images (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  component_type_id uuid not null references public.component_types(id) on delete cascade,
  component_id uuid references public.components(id) on delete cascade,
  detection_id uuid references public.scan_detections(id) on delete cascade,
  storage_path text unique check (storage_path is null or storage_path like workspace_id::text || '/%'),
  embedding extensions.vector,
  embedding_model text check (embedding_model is null or char_length(embedding_model) <= 120),
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint reference_image_source check (storage_path is not null or detection_id is not null),
  constraint reference_embedding_model check ((embedding is null) = (embedding_model is null))
);
create index component_reference_images_type_idx on public.component_reference_images (workspace_id, component_type_id);
create index component_reference_images_model_idx on public.component_reference_images (workspace_id, embedding_model)
  where embedding is not null;

-- ---------------------------------------------------------------- stock log
-- Devices: received (intake lines) and processed (units), components: recovered (cut out, into the
-- bins) and extracted (used up by the science team); either can have adjustments (stocktakes,
-- scrap). quantity and weight_kg are signed. Component rows may say what kind of device the parts
-- came from (from_device_*), which is how the Inventory page splits parts to cut by product.
create table public.inventory_movements (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  item_kind text not null check (item_kind in ('device', 'component')),
  device_category_id uuid references public.device_categories(id),
  device_model_id uuid references public.device_models(id),
  component_type_id uuid references public.component_types(id),
  component_id uuid references public.components(id),
  from_device_category_id uuid references public.device_categories(id),
  from_device_model_id uuid references public.device_models(id),
  quantity integer not null default 0,
  weight_kg numeric(12,3),
  reason text not null check (reason in ('received', 'processed', 'recovered', 'extracted', 'adjustment')),
  intake_line_id uuid references public.intake_lines(id),
  unit_id uuid references public.units(id),
  note text check (note is null or char_length(note) <= 1000),
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  constraint inventory_movements_item check (
    (item_kind = 'device' and device_category_id is not null and component_type_id is null and component_id is null
       and from_device_category_id is null and from_device_model_id is null
       and reason in ('received', 'processed', 'adjustment'))
    or (item_kind = 'component' and component_type_id is not null and device_category_id is null and device_model_id is null
       and reason in ('recovered', 'extracted', 'adjustment'))),
  constraint inventory_movements_nonzero check (quantity <> 0 or coalesce(weight_kg, 0) <> 0)
);
create index inventory_movements_ws_idx on public.inventory_movements (workspace_id, item_kind, created_at desc);
create index inventory_movements_intake_idx on public.inventory_movements (intake_line_id) where intake_line_id is not null;
create index inventory_movements_unit_idx on public.inventory_movements (unit_id) where unit_id is not null;

-- ---------------------------------------------------------------- yield tests
create table public.component_yield_tests (
  id uuid primary key default gen_random_uuid(),
  workspace_id uuid not null references public.workspaces(id) on delete cascade,
  component_type_id uuid not null references public.component_types(id) on delete restrict,
  component_id uuid references public.components(id) on delete restrict,
  tested_at date not null default current_date,
  sample_count integer check (sample_count is null or sample_count > 0),   -- components in the sample
  sample_mass_g numeric(12,3) check (sample_mass_g is null or sample_mass_g > 0),
  copper_g numeric(12,4) check (copper_g is null or copper_g >= 0),
  copper_purity_pct numeric(6,3) check (copper_purity_pct is null or copper_purity_pct between 0 and 100),
  gold_mg numeric(12,4) check (gold_mg is null or gold_mg >= 0),
  gold_purity_pct numeric(6,3) check (gold_purity_pct is null or gold_purity_pct between 0 and 100),
  other_results jsonb not null default '{}'::jsonb check (jsonb_typeof(other_results) = 'object'),  -- {"silver_mg": 12.5}
  method text check (method is null or char_length(method) <= 200),
  notes text check (notes is null or char_length(notes) <= 4000),
  tested_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_by uuid default auth.uid() references public.profiles(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint component_yield_tests_sample check (sample_count is not null or sample_mass_g is not null)
);
create index component_yield_tests_type_idx on public.component_yield_tests (workspace_id, component_type_id, tested_at desc);

-- ---------------------------------------------------------------- row rules (all inventory tables)
-- Before each insert/update: take the workspace from the parent row where there is one, fill the
-- category or type from a model or part, check that everything the row points at is in the same
-- workspace (and that a category isn't inside itself), and stamp created_by / updated_at. One function
-- for every table, working on the row as JSON, so each table only needs the columns it has.
create or replace function public.inventory_prepare_row()
returns trigger language plpgsql security definer set search_path = '' as $$
declare
  r jsonb := to_jsonb(new);
  ws uuid;
  v uuid;
  ok boolean;
  ref record;
begin
  ws := case tg_table_name
          when 'intake_lines' then (select b.workspace_id from public.intake_batches b where b.id = (r->>'batch_id')::uuid)
          when 'scan_detections' then (select s.workspace_id from public.xray_scans s where s.id = (r->>'scan_id')::uuid)
          else (r->>'workspace_id')::uuid end;
  if ws is null then raise exception 'parent not found' using errcode = '23503'; end if;
  if tg_op = 'UPDATE' and ws is distinct from old.workspace_id then
    raise exception 'rows cannot move to another workspace' using errcode = '42501';
  end if;
  r := r || jsonb_build_object('workspace_id', ws);

  -- A model decides the category and a part decides the type. Parts lists keep model lines apart
  -- from category lines, so there the category stays empty.
  if r->>'device_model_id' is not null then
    select m.device_category_id into v from public.device_models m
     where m.id = (r->>'device_model_id')::uuid and m.workspace_id = ws;
    if v is null then raise exception 'device model not found' using errcode = '23503'; end if;
    if tg_table_name <> 'device_bom' then r := r || jsonb_build_object('device_category_id', v); end if;
  end if;
  if r->>'component_id' is not null then
    select c.component_type_id into v from public.components c
     where c.id = (r->>'component_id')::uuid and c.workspace_id = ws;
    if v is null then raise exception 'component not found' using errcode = '23503'; end if;
    r := r || jsonb_build_object('component_type_id', v);
  end if;
  if r->>'from_device_model_id' is not null then
    select m.device_category_id into v from public.device_models m
     where m.id = (r->>'from_device_model_id')::uuid and m.workspace_id = ws;
    if v is null then raise exception 'device model not found' using errcode = '23503'; end if;
    r := r || jsonb_build_object('from_device_category_id', v);
  end if;

  for ref in select * from (values
      ('parent_id', tg_table_name::text), ('device_category_id', 'device_categories'),
      ('from_device_category_id', 'device_categories'),
      ('component_type_id', 'component_types'), ('predicted_component_type_id', 'component_types'),
      ('predicted_component_id', 'components'), ('batch_id', 'intake_batches'),
      ('intake_line_id', 'intake_lines'), ('unit_id', 'units'), ('scan_id', 'xray_scans'),
      ('detection_id', 'scan_detections'), ('device_id', 'lazarus_devices')) t(col, tbl)
  loop
    continue when r->>ref.col is null;
    execute format('select exists (select 1 from public.%I where id = $1 and workspace_id = $2)', ref.tbl)
      into ok using (r->>ref.col)::uuid, ws;
    if not ok then
      raise exception '% not found', replace(regexp_replace(ref.col, '_id$', ''), '_', ' ') using errcode = '23503';
    end if;
  end loop;

  if r->>'parent_id' is not null then
    execute format($q$
      with recursive up as (
        select t.id, t.parent_id, 1 as depth from public.%1$I t where t.id = $1
        union all
        select t.id, t.parent_id, up.depth + 1 from public.%1$I t join up on t.id = up.parent_id where up.depth < 50)
      select exists (select 1 from up where up.id = $2)$q$, tg_table_name) into ok using (r->>'parent_id')::uuid, (r->>'id')::uuid;
    if ok then raise exception 'a category cannot be inside itself' using errcode = '23514'; end if;
  end if;

  if tg_op = 'INSERT' then
    if r ? 'created_by' and (select auth.uid()) is not null then
      r := r || jsonb_build_object('created_by', (select auth.uid()));
    end if;
  else
    if r ? 'created_by' then r := r || jsonb_build_object('created_by', to_jsonb(old)->'created_by'); end if;
    if r ? 'created_at' then r := r || jsonb_build_object('created_at', to_jsonb(old)->'created_at'); end if;
    if r ? 'updated_at' then r := r || jsonb_build_object('updated_at', now()); end if;
  end if;
  new := jsonb_populate_record(new, r);
  return new;
end $$;
revoke execute on function public.inventory_prepare_row() from public, anon, authenticated;

do $$
declare t text;
begin
  foreach t in array array['device_categories', 'device_models', 'component_types', 'components', 'device_bom',
                           'intake_batches', 'intake_lines', 'units', 'xray_scans', 'scan_detections',
                           'component_reference_images', 'inventory_movements', 'component_yield_tests'] loop
    execute format('create trigger inv_10_prepare before insert or update on public.%I
                      for each row execute function public.inventory_prepare_row()', t);
  end loop;
end $$;

create or replace function public.scan_detections_review()
returns trigger language plpgsql set search_path = '' as $$
begin
  if tg_op = 'INSERT' then
    if new.source = 'model' then
      new.predicted_component_type_id := new.component_type_id;
      new.predicted_component_id := new.component_id;
    else
      new.predicted_component_type_id := null;
      new.predicted_component_id := null;
      new.confidence := null;
      new.reviewed_by := coalesce((select auth.uid()), new.reviewed_by);
      new.reviewed_at := coalesce(new.reviewed_at, now());
    end if;
  else
    new.source := old.source;
    new.predicted_component_type_id := old.predicted_component_type_id;
    new.predicted_component_id := old.predicted_component_id;
    if (select auth.uid()) is not null then
      new.reviewed_by := (select auth.uid());
      new.reviewed_at := now();
      if new.status in ('auto', 'needs_review') then new.status := 'confirmed'; end if;
    end if;
  end if;
  return new;
end $$;
revoke execute on function public.scan_detections_review() from public, anon, authenticated;
create trigger inv_20_review before insert or update on public.scan_detections
  for each row execute function public.scan_detections_review();

create or replace function public.units_processed_at()
returns trigger language plpgsql set search_path = '' as $$
begin
  if new.status <> 'processed' then
    new.processed_at := null;
  elsif tg_op = 'INSERT' or old.status <> 'processed' then
    new.processed_at := coalesce(new.processed_at, now());
  end if;
  return new;
end $$;
revoke execute on function public.units_processed_at() from public, anon, authenticated;
create trigger inv_20_processed_at before insert or update of status on public.units
  for each row execute function public.units_processed_at();

-- ---------------------------------------------------------------- stock log triggers
-- Intake lines and processed units keep the device rows of the log in step with them. A change adds
-- one row that undoes the old effect and one for the new effect, so the log only ever grows.
create or replace function public.inventory_log_devices(
  p_ws uuid, p_category uuid, p_model uuid, p_quantity integer, p_weight_kg numeric,
  p_reason text, p_intake_line uuid, p_unit uuid, p_note text)
returns void language sql security definer set search_path = '' as $$
  insert into public.inventory_movements
    (workspace_id, item_kind, device_category_id, device_model_id, quantity, weight_kg, reason, intake_line_id, unit_id, note)
  select p_ws, 'device', p_category, p_model, coalesce(p_quantity, 0), nullif(p_weight_kg, 0), p_reason, p_intake_line, p_unit, p_note
   where coalesce(p_quantity, 0) <> 0 or coalesce(p_weight_kg, 0) <> 0;
$$;
revoke execute on function public.inventory_log_devices(uuid, uuid, uuid, integer, numeric, text, uuid, uuid, text)
  from public, anon, authenticated;

create or replace function public.intake_lines_log()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'UPDATE' then
    if (new.device_category_id, new.device_model_id, new.quantity, new.weight_kg)
       is not distinct from (old.device_category_id, old.device_model_id, old.quantity, old.weight_kg) then
      return null;
    end if;
    perform public.inventory_log_devices(old.workspace_id, old.device_category_id, old.device_model_id,
      -old.quantity, -old.weight_kg, 'received', old.id, null, 'Intake line changed');
  end if;
  perform public.inventory_log_devices(new.workspace_id, new.device_category_id, new.device_model_id,
    new.quantity, new.weight_kg, 'received', new.id, null, null);
  return null;
end $$;
revoke execute on function public.intake_lines_log() from public, anon, authenticated;
create trigger inv_30_log after insert or update on public.intake_lines
  for each row execute function public.intake_lines_log();

create or replace function public.units_log()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  if tg_op = 'UPDATE' then
    if (new.status = 'processed') = (old.status = 'processed')
       and (new.status <> 'processed'
            or (new.device_category_id, new.device_model_id, new.device_count)
               is not distinct from (old.device_category_id, old.device_model_id, old.device_count)) then
      return null;
    end if;
    if old.status = 'processed' then   -- put the old devices back
      perform public.inventory_log_devices(old.workspace_id, old.device_category_id, old.device_model_id,
        old.device_count, null, 'processed', null, old.id, 'Unit changed');
    end if;
  end if;
  if new.status = 'processed' then
    perform public.inventory_log_devices(new.workspace_id, new.device_category_id, new.device_model_id,
      -new.device_count, null, 'processed', null, new.id, null);
  end if;
  return null;
end $$;
revoke execute on function public.units_log() from public, anon, authenticated;
create trigger inv_30_log after insert or update on public.units
  for each row execute function public.units_log();

-- ---------------------------------------------------------------- counts (invoker: RLS applies)
create view public.inventory_device_stock with (security_invoker = true) as
select m.workspace_id, m.device_category_id, m.device_model_id,
       coalesce(sum(m.quantity) filter (where m.reason = 'received'), 0) as received,
       coalesce(-sum(m.quantity) filter (where m.reason = 'processed'), 0) as processed,
       coalesce(sum(m.quantity) filter (where m.reason = 'adjustment'), 0) as adjusted,
       sum(m.quantity) as on_hand,
       coalesce(sum(m.weight_kg) filter (where m.reason = 'received'), 0) as received_kg,
       max(m.created_at) as last_change_at
  from public.inventory_movements m
 where m.item_kind = 'device'
 group by m.workspace_id, m.device_category_id, m.device_model_id;

create view public.inventory_component_stock with (security_invoker = true) as
select m.workspace_id, m.component_type_id, m.component_id,
       coalesce(sum(m.quantity) filter (where m.reason = 'recovered'), 0) as recovered,
       coalesce(-sum(m.quantity) filter (where m.reason = 'extracted'), 0) as extracted,
       coalesce(sum(m.quantity) filter (where m.reason = 'adjustment'), 0) as adjusted,
       sum(m.quantity) as on_hand,
       coalesce(sum(m.weight_kg), 0) as on_hand_kg,
       max(m.created_at) as last_change_at
  from public.inventory_movements m
 where m.item_kind = 'component'
 group by m.workspace_id, m.component_type_id, m.component_id;

-- Components seen in X-ray scans: people's boxes and the model's 'auto' answers. Several views of one
-- unit show the same parts, so each unit counts its view with the most (a scan without a unit counts
-- on its own). found_in = units (or unassigned scans) the component was seen in.
create view public.inventory_components_identified with (security_invoker = true) as
with per_scan as (
  select d.workspace_id, coalesce(s.unit_id, s.id) as unit_key, d.scan_id, d.component_type_id, d.component_id,
         count(*) as n, max(d.created_at) as last_at
    from public.scan_detections d
    join public.xray_scans s on s.id = d.scan_id
   where d.status in ('auto', 'confirmed')
   group by d.workspace_id, coalesce(s.unit_id, s.id), d.scan_id, d.component_type_id, d.component_id
), per_unit as (
  select workspace_id, unit_key, component_type_id, component_id, max(n) as n, max(last_at) as last_at
    from per_scan
   group by workspace_id, unit_key, component_type_id, component_id
)
select workspace_id, component_type_id, component_id,
       sum(n) as identified, count(*) as found_in, max(last_at) as last_identified_at
  from per_unit
 group by workspace_id, component_type_id, component_id;

-- Components expected in what has arrived: intake device counts times the model's parts list, or the
-- category's when the model has none or isn't known. Weight-only lines aren't counted.
create view public.inventory_components_expected with (security_invoker = true) as
select l.workspace_id, b.component_type_id, b.component_id, sum(l.quantity * b.quantity) as expected
  from public.intake_lines l
  join public.device_bom b
    on b.device_model_id = l.device_model_id
    or (b.device_category_id = l.device_category_id
        and not exists (select 1 from public.device_bom mb where mb.device_model_id = l.device_model_id))
 where l.quantity > 0
 group by l.workspace_id, b.component_type_id, b.component_id;

-- Parts to cut, per kind of processed device (its model, or its category when the model isn't known)
-- and component type: how many the parts lists say were inside, and how many have been cut out of
-- that kind of device. Parts logged without a source device come back with no category or model.
create or replace function public.inventory_parts_to_cut(p_workspace uuid)
returns table (device_category_id uuid, device_model_id uuid, component_type_id uuid, expected numeric, cut bigint)
language sql stable security invoker set search_path = '' as $$
  with processed as (
    select s.device_category_id, s.device_model_id, s.processed
      from public.inventory_device_stock s
     where s.workspace_id = p_workspace and s.processed > 0
  ), expected as (
    select p.device_category_id, p.device_model_id, b.component_type_id, sum(p.processed * b.quantity) as expected
      from processed p
      join public.device_bom b
        on b.device_model_id = p.device_model_id
        or (b.device_category_id = p.device_category_id
            and not exists (select 1 from public.device_bom mb where mb.device_model_id = p.device_model_id))
     group by 1, 2, 3
  ), cut as (
    select m.from_device_category_id, m.from_device_model_id, m.component_type_id, sum(m.quantity) as cut
      from public.inventory_movements m
     where m.workspace_id = p_workspace and m.item_kind = 'component' and m.reason = 'recovered'
     group by 1, 2, 3
  )
  select x.device_category_id, x.device_model_id, x.component_type_id, sum(x.expected), sum(x.cut)::bigint
    from (select e.device_category_id, e.device_model_id, e.component_type_id, e.expected, 0::bigint as cut from expected e
          union all
          select c.from_device_category_id, c.from_device_model_id, c.component_type_id, 0::numeric, c.cut from cut c) x
   group by x.device_category_id, x.device_model_id, x.component_type_id;
$$;
revoke execute on function public.inventory_parts_to_cut(uuid) from public, anon;
grant execute on function public.inventory_parts_to_cut(uuid) to authenticated, service_role;

-- ---------------------------------------------------------------- matching and the worker queue
-- Nearest reference crops to an embedding (cosine distance), from the same embedding model. expected
-- says whether the device's parts list has that component type: the worker can prefer those without
-- hiding a part nobody expected.
create or replace function public.match_components(
  p_workspace uuid, p_embedding extensions.vector, p_embedding_model text,
  p_device_category uuid default null, p_device_model uuid default null, p_limit int default 5)
returns table (reference_id uuid, component_type_id uuid, component_id uuid, distance double precision, expected boolean)
language sql stable security invoker set search_path = '' as $$
  select r.id, r.component_type_id, r.component_id,
         (r.embedding operator(extensions.<=>) p_embedding)::double precision,
         exists (select 1 from public.device_bom b
                  where b.component_type_id = r.component_type_id
                    and (b.device_model_id = p_device_model
                         or (b.device_model_id is null and b.device_category_id = p_device_category)))
    from public.component_reference_images r
   where r.workspace_id = p_workspace
     and r.embedding_model = p_embedding_model
     and extensions.vector_dims(r.embedding) = extensions.vector_dims(p_embedding)
   order by r.embedding operator(extensions.<=>) p_embedding
   limit least(greatest(p_limit, 1), 50);
$$;
revoke execute on function public.match_components(uuid, extensions.vector, text, uuid, uuid, int) from public, anon;
grant execute on function public.match_components(uuid, extensions.vector, text, uuid, uuid, int) to authenticated, service_role;

-- Worker queue: hands out queued scans (and ones stuck in 'analyzing' for 15 minutes) without two
-- workers getting the same scan. Service role only.
create or replace function public.claim_xray_scans(p_limit int default 1, p_model text default null)
returns setof public.xray_scans language plpgsql security definer set search_path = '' as $$
begin
  return query
  update public.xray_scans s
     set status = 'analyzing', analysis_started_at = now(), analysis_error = null,
         analysis_model = coalesce(p_model, s.analysis_model)
   where s.id in (select q.id from public.xray_scans q
                   where q.status = 'queued'
                      or (q.status = 'analyzing' and q.analysis_started_at < now() - interval '15 minutes')
                   order by q.captured_at
                   limit least(greatest(p_limit, 1), 100)
                   for update skip locked)
  returning s.*;
end $$;
revoke execute on function public.claim_xray_scans(int, text) from public, anon, authenticated;
grant execute on function public.claim_xray_scans(int, text) to service_role;

-- ---------------------------------------------------------------- RLS
-- Members read and write; owners/admins delete. Rows in use can't be deleted (archive them instead).
do $$
declare t text;
begin
  foreach t in array array['device_categories', 'device_models', 'component_types', 'components', 'device_bom',
                           'intake_batches', 'units', 'xray_scans', 'component_reference_images',
                           'component_yield_tests'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('revoke all on public.%I from anon', t);
    execute format('create policy %1$s_select on public.%1$I for select to authenticated
                      using (public.is_workspace_member(workspace_id))', t);
    execute format('create policy %1$s_insert on public.%1$I for insert to authenticated
                      with check (public.is_workspace_member(workspace_id))', t);
    execute format('create policy %1$s_update on public.%1$I for update to authenticated
                      using (public.is_workspace_member(workspace_id)) with check (public.is_workspace_member(workspace_id))', t);
    execute format('create policy %1$s_delete on public.%1$I for delete to authenticated
                      using (public.is_workspace_admin(workspace_id))', t);
  end loop;
end $$;

-- Intake lines are never deleted (set the count to 0 instead), so the log always has their source.
alter table public.intake_lines enable row level security;
revoke all on public.intake_lines from anon;
create policy intake_lines_select on public.intake_lines for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy intake_lines_insert on public.intake_lines for insert to authenticated
  with check (public.is_workspace_member(workspace_id));
create policy intake_lines_update on public.intake_lines for update to authenticated
  using (public.is_workspace_member(workspace_id)) with check (public.is_workspace_member(workspace_id));

-- Scans: the analysis fields belong to the worker and the ingest function (service role).
revoke insert, update on public.xray_scans from authenticated;
grant insert (id, workspace_id, unit_id, view, captured_at, storage_path, filename, content_type, size_bytes,
              width, height, bit_depth, preview_path, pixel_size_mm, metadata, notes, status)
  on public.xray_scans to authenticated;
grant update (unit_id, view, preview_path, pixel_size_mm, notes, status) on public.xray_scans to authenticated;

-- Detections: people draw and review boxes; model rows come from the worker. A person can delete their
-- own boxes; model answers are rejected instead, so they still count towards its accuracy.
alter table public.scan_detections enable row level security;
revoke all on public.scan_detections from anon;
revoke insert, update on public.scan_detections from authenticated;
grant insert (id, scan_id, component_type_id, component_id, x, y, w, h, polygon, status) on public.scan_detections to authenticated;
grant update (component_type_id, component_id, x, y, w, h, polygon, status) on public.scan_detections to authenticated;
create policy scan_detections_select on public.scan_detections for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy scan_detections_insert on public.scan_detections for insert to authenticated
  with check (public.is_workspace_member(workspace_id));
create policy scan_detections_update on public.scan_detections for update to authenticated
  using (public.is_workspace_member(workspace_id)) with check (public.is_workspace_member(workspace_id));
create policy scan_detections_delete on public.scan_detections for delete to authenticated
  using (public.is_workspace_admin(workspace_id)
         or (public.is_workspace_member(workspace_id) and source = 'human' and created_by = (select auth.uid())));

-- Stock log: read by members; people add recovered, extracted and adjustment rows. Nobody edits or
-- deletes rows; received and processed rows come only from the triggers above.
alter table public.inventory_movements enable row level security;
revoke all on public.inventory_movements from anon, authenticated;
grant select on public.inventory_movements to authenticated;
grant insert (id, workspace_id, item_kind, device_category_id, device_model_id, component_type_id, component_id,
              from_device_category_id, from_device_model_id, quantity, weight_kg, reason, unit_id, note)
  on public.inventory_movements to authenticated;
create policy inventory_movements_select on public.inventory_movements for select to authenticated
  using (public.is_workspace_member(workspace_id));
create policy inventory_movements_insert on public.inventory_movements for insert to authenticated
  with check (public.is_workspace_member(workspace_id) and reason in ('recovered', 'extracted', 'adjustment'));

revoke all on public.inventory_device_stock, public.inventory_component_stock,
              public.inventory_components_identified, public.inventory_components_expected from anon;

-- ---------------------------------------------------------------- storage
-- Private bucket for X-ray originals, previews and reference crops: <workspace_id>/<scan_id>/<file>.
-- Members can upload from Warp; the X-ray PC uploads through signed URLs from the ingest function.
insert into storage.buckets (id, name, public, file_size_limit)
values ('xray-scans', 'xray-scans', false, 104857600)
on conflict (id) do update set public = false, file_size_limit = excluded.file_size_limit;

create policy xray_objects_select on storage.objects for select to authenticated
  using (bucket_id = 'xray-scans' and public.is_workspace_member(public.storage_workspace_id(name)));
create policy xray_objects_insert on storage.objects for insert to authenticated
  with check (bucket_id = 'xray-scans' and public.is_workspace_member(public.storage_workspace_id(name)));
create policy xray_objects_update on storage.objects for update to authenticated
  using (bucket_id = 'xray-scans' and public.is_workspace_member(public.storage_workspace_id(name)))
  with check (bucket_id = 'xray-scans' and public.is_workspace_member(public.storage_workspace_id(name)));
create policy xray_objects_delete on storage.objects for delete to authenticated
  using (bucket_id = 'xray-scans' and public.is_workspace_admin(public.storage_workspace_id(name)));

-- ---------------------------------------------------------------- realtime
alter publication supabase_realtime add table public.units, public.xray_scans, public.scan_detections, public.inventory_movements;
