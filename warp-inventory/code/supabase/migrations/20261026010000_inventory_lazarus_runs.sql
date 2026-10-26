-- Lazarus 2 runs feed the inventory.
-- A complete run (status_override, else status) is one processed device: a unit with code L2-<run
-- folder>, linked through lazarus_runs.unit_id, typed by the run's device_type (desktop -> DESKTOP).
-- Each completed pick logs what it took out as recovered parts: the top face Lazarus cuts off and
-- drops in the scrap bin counts as CHASSIS, and the board the operator lifts out (picks[].manual
-- "board") as MOTHERBOARD. Other names match a component type code (fan -> FAN, psu -> PSU).
-- Re-sending or re-labelling a run only logs the difference, so the stock log still only grows. A run
-- that stops being complete voids its unit and takes its parts back out. Setting a model on the unit
-- moves the run's parts to that model.

alter table public.inventory_movements
  add column lazarus_run_id uuid references public.lazarus_runs(id) on delete set null;
create index inventory_movements_lazarus_run_idx on public.inventory_movements (lazarus_run_id)
  where lazarus_run_id is not null;

-- Lazarus names ("desktop", "top face", "board") -> catalog codes (DESKTOP, CHASSIS, MOTHERBOARD).
create or replace function public.inventory_lazarus_code(p_name text)
returns text language sql immutable set search_path = '' as $$
  select case lower(btrim(p_name))
           when 'top face' then 'CHASSIS'
           when 'board' then 'MOTHERBOARD'
           else nullif(upper(btrim(regexp_replace(btrim(p_name), '[^A-Za-z0-9]+', '-', 'g'), '-')), '') end;
$$;

create or replace function public.inventory_sync_lazarus_run(p_run uuid)
returns void language plpgsql security definer set search_path = '' as $$
declare
  r public.lazarus_runs;
  own public.units;     -- the unit this sync made for the run (code L2-<run folder>)
  u public.units;       -- the unit the run's parts count against
  v_done boolean;
  v_code text;
  v_category uuid;
  v_when timestamptz;
begin
  select * into r from public.lazarus_runs where id = p_run;
  if not found then return; end if;
  v_done := lower(coalesce(r.status_override, r.status, '')) = 'complete';
  v_code := left('L2-' || regexp_replace(r.external_run_id, '[^A-Za-z0-9._-]+', '_', 'g'), 64);
  v_when := coalesce(r.ended_at, r.started_at);
  select * into own from public.units where workspace_id = r.workspace_id and code = v_code;

  if r.unit_id is not null and r.unit_id is distinct from own.id then
    -- Linked to someone's unit (an X-ray unit, say): finish it, and drop the one made earlier.
    select * into u from public.units where id = r.unit_id;
    if v_done and u.status = 'open' and u.device_category_id is not null then
      update public.units set status = 'processed', processed_at = v_when where id = u.id returning * into u;
    end if;
    if own.status = 'processed' then
      update public.units set status = 'void' where id = own.id;
    end if;
  elsif own.id is not null then
    if own.status <> (case when v_done then 'processed' else 'void' end) then
      update public.units set status = (case when v_done then 'processed' else 'void' end), processed_at = v_when
       where id = own.id returning * into own;
    end if;
    u := own;
  elsif v_done then
    select c.id into v_category from public.device_categories c
     where c.workspace_id = r.workspace_id and c.code = public.inventory_lazarus_code(r.metadata->>'device_type');
    if v_category is null then return; end if;   -- that device type isn't in the catalog yet
    insert into public.units (workspace_id, code, device_category_id, status, started_at, processed_at, notes)
    values (r.workspace_id, v_code, v_category, 'processed', r.started_at, v_when, 'Lazarus 2 run ' || r.external_run_id)
    returning * into u;
  end if;

  -- Parts the completed picks took out, minus what this run already logged.
  insert into public.inventory_movements (workspace_id, item_kind, component_type_id, from_device_category_id,
    from_device_model_id, quantity, reason, unit_id, lazarus_run_id, note)
  select r.workspace_id, 'component', x.component_type_id, x.category_id, x.model_id, sum(x.n)::integer,
         'recovered', x.unit_id, r.id, 'Lazarus 2 run ' || r.external_run_id
    from (select t.id as component_type_id, u.device_category_id as category_id, u.device_model_id as model_id,
                 u.id as unit_id, count(*) as n
            from jsonb_array_elements(case when jsonb_typeof(r.metadata->'picks') = 'array'
                                           then r.metadata->'picks' else '[]'::jsonb end) p
           cross join lateral (
                 select q->>'name' as name
                   from jsonb_array_elements(case when jsonb_typeof(p->'parts') = 'array' then p->'parts' else '[]'::jsonb end) q
                  union all
                 select m #>> '{}'
                   from jsonb_array_elements(case when jsonb_typeof(p->'manual') = 'array' then p->'manual' else '[]'::jsonb end) m) part
            join public.component_types t
              on t.workspace_id = r.workspace_id and t.code = public.inventory_lazarus_code(part.name)
           where v_done and u.status = 'processed' and lower(p->>'outcome') = 'complete'
           group by 1, 2, 3, 4
          union all
          select m.component_type_id, m.from_device_category_id, m.from_device_model_id, m.unit_id, -sum(m.quantity)
            from public.inventory_movements m
           where m.lazarus_run_id = r.id and m.item_kind = 'component' and m.reason = 'recovered'
           group by 1, 2, 3, 4) x
   group by x.component_type_id, x.category_id, x.model_id, x.unit_id
  having sum(x.n) <> 0;

  -- Last, so the update trigger this fires finds nothing left to do.
  if u.id is not null and r.unit_id is distinct from u.id then
    update public.lazarus_runs set unit_id = u.id where id = r.id;
  end if;
end $$;
revoke execute on function public.inventory_sync_lazarus_run(uuid) from public, anon, authenticated;

create or replace function public.lazarus_runs_inventory()
returns trigger language plpgsql security definer set search_path = '' as $$
begin
  perform public.inventory_sync_lazarus_run(new.id);
  return null;
end $$;
revoke execute on function public.lazarus_runs_inventory() from public, anon, authenticated;
create trigger inv_40_inventory after insert or update of status, status_override, metadata, unit_id
  on public.lazarus_runs for each row execute function public.lazarus_runs_inventory();

create or replace function public.units_lazarus_parts()
returns trigger language plpgsql security definer set search_path = '' as $$
declare v uuid;
begin
  for v in select id from public.lazarus_runs where unit_id = new.id loop
    perform public.inventory_sync_lazarus_run(v);
  end loop;
  return null;
end $$;
revoke execute on function public.units_lazarus_parts() from public, anon, authenticated;
create trigger inv_40_lazarus_parts after update of device_category_id, device_model_id on public.units
  for each row execute function public.units_lazarus_parts();

-- The runs Warp already has.
do $$
declare v uuid;
begin
  for v in select id from public.lazarus_runs order by started_at, id loop
    perform public.inventory_sync_lazarus_run(v);
  end loop;
end $$;
