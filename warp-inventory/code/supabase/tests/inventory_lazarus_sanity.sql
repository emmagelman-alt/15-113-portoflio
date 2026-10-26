-- Lazarus 2 runs -> inventory (20261026010000_inventory_lazarus_runs.sql): run as superuser after the
-- migrations; everything is rolled back. Every row of the final select should be ok = true.
-- The run metadata copies what Lazarus 2 sends in cycle.json (picks[].parts / picks[].manual).
begin;
insert into auth.users(id,email) values ('00000000-0000-0000-0000-00000000000a','alice@example.com');
create temp table r(test text, ok boolean); grant all on r to anon, authenticated, service_role;

set local role authenticated;
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}',true);
insert into public.workspaces(id,name) values ('11111111-1111-1111-1111-111111111111','Andean');
select public.inventory_seed_starter_catalog('11111111-1111-1111-1111-111111111111');

-- Lazarus writes runs as the service role
reset role;
create temp view parts as
  select c.code as category, m.code as model, t.code as part, p.expected, p.cut
    from public.inventory_parts_to_cut('11111111-1111-1111-1111-111111111111') p
    join public.device_categories c on c.id = p.device_category_id
    left join public.device_models m on m.id = p.device_model_id
    join public.component_types t on t.id = p.component_type_id;
create temp view processed as
  select coalesce(sum(processed), 0) as n from public.inventory_device_stock
   where workspace_id = '11111111-1111-1111-1111-111111111111';
grant select on parts, processed to authenticated;
insert into public.lazarus_devices(id, workspace_id, name, token_hash) values
  ('dddddddd-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','Lazarus 2', repeat('a',64));
insert into public.lazarus_runs(id, workspace_id, device_id, external_run_id, started_at, ended_at, status, metadata) values
  ('eeeeeeee-0000-0000-0000-00000000000a','11111111-1111-1111-1111-111111111111','dddddddd-0000-0000-0000-000000000001',
   '20261024-143654_desktop','2026-10-24 21:36:54+00','2026-10-24 21:40:47+00','complete',
   '{"device_type":"desktop","status":"complete","cuts":[{"n":1,"outcome":"complete"}],
     "picks":[{"n":1,"outcome":"complete","parts":[{"name":"top face","label":"scrap","bin":"drop_bin_minus_x"}],"manual":["board"]}]}'),
  ('eeeeeeee-0000-0000-0000-00000000000b','11111111-1111-1111-1111-111111111111','dddddddd-0000-0000-0000-000000000001',
   '20261022-155310_desktop','2026-10-22 22:53:10+00',null,'complete','{"device_type":"desktop","cuts":[{"outcome":"complete"}],"picks":[]}'),
  ('eeeeeeee-0000-0000-0000-00000000000c','11111111-1111-1111-1111-111111111111','dddddddd-0000-0000-0000-000000000001',
   '20261021-130334_desktop','2026-10-21 20:03:34+00',null,'failed',
   '{"device_type":"desktop","picks":[{"outcome":"pick_out_fail","parts":[{"name":"top face"}],"manual":["board"]}]}'),
  ('eeeeeeee-0000-0000-0000-00000000000d','11111111-1111-1111-1111-111111111111','dddddddd-0000-0000-0000-000000000001',
   '20261019-155511_desktop','2026-10-19 22:55:11+00',null,'incomplete','{"device_type":"desktop","picks":"oops"}'),
  ('eeeeeeee-0000-0000-0000-00000000000f','11111111-1111-1111-1111-111111111111','dddddddd-0000-0000-0000-000000000001',
   '20261025-090000_toaster','2026-10-25 16:00:00+00',null,'complete',
   '{"device_type":"toaster","picks":[{"outcome":"complete","parts":[{"name":"top face"}]}]}');
-- POST /runs while running, then POST /runs/{id}/complete merges the finished cycle.json in
insert into public.lazarus_runs(id, workspace_id, device_id, external_run_id, started_at, status, metadata) values
  ('eeeeeeee-0000-0000-0000-00000000000e','11111111-1111-1111-1111-111111111111','dddddddd-0000-0000-0000-000000000001',
   '20261024-132823_desktop','2026-10-24 20:28:23+00','in_progress','{"device_type":"desktop"}');
insert into r select 'a running run is not processed yet', (select n from processed) = 2;
update public.lazarus_runs set status = 'complete', ended_at = '2026-10-24 20:32:00+00',
  metadata = metadata || '{"picks":[{"n":1,"outcome":"complete","parts":[{"name":"top face","label":"scrap"}],"manual":["board"]}]}'
 where id = 'eeeeeeee-0000-0000-0000-00000000000e';

insert into r select 'complete runs are processed desktops', (select n from processed) = 3;
insert into r select 'each complete run gets its own linked unit, labelled with the run',
  (select count(*) from public.lazarus_runs l join public.units u on u.id = l.unit_id
    where u.code = 'L2-' || l.external_run_id and u.notes = 'Lazarus 2 run ' || l.external_run_id and u.status = 'processed') = 3
  and (select count(*) from public.lazarus_runs where unit_id is null) = 3;
insert into r select 'the unit is processed when the run ended',
  (select u.processed_at = '2026-10-24 21:40:47+00' and u.started_at = '2026-10-24 21:36:54+00'
     from public.units u where u.code = 'L2-20261024-143654_desktop');
insert into r select 'completed picks log the top face as chassis and the board as motherboard',
  (select cut from parts where category = 'DESKTOP' and model is null and part = 'MOTHERBOARD') = 2
  and (select cut from parts where category = 'DESKTOP' and model is null and part = 'CHASSIS') = 2
  and (select sum(cut) from parts) = 4;
insert into r select 'expected parts come from the desktop parts list',
  (select expected from parts where category = 'DESKTOP' and model is null and part = 'RAM') = 6;
insert into r select 'a failed pick logs nothing',
  not exists (select 1 from public.inventory_movements where lazarus_run_id = 'eeeeeeee-0000-0000-0000-00000000000c');
insert into r select 'a device type missing from the catalog is skipped',
  (select unit_id is null from public.lazarus_runs where id = 'eeeeeeee-0000-0000-0000-00000000000f')
  and not exists (select 1 from public.inventory_movements where lazarus_run_id = 'eeeeeeee-0000-0000-0000-00000000000f');

create temp table log_size as select count(*) as n from public.inventory_movements;
update public.lazarus_runs set metadata = metadata, status = 'complete' where id = 'eeeeeeee-0000-0000-0000-00000000000a';
insert into r select 'resending a run adds nothing', (select count(*) from public.inventory_movements) = (select n from log_size);

update public.lazarus_runs set status_override = 'failed' where id = 'eeeeeeee-0000-0000-0000-00000000000a';
insert into r select 'marking a run failed voids its unit and takes its parts back',
  (select n from processed) = 2
  and (select cut from parts where category = 'DESKTOP' and model is null and part = 'MOTHERBOARD') = 1
  and (select status from public.units where code = 'L2-20261024-143654_desktop') = 'void';
insert into r select 'the log only grows', (select count(*) from public.inventory_movements) > (select n from log_size);
update public.lazarus_runs set status_override = null where id = 'eeeeeeee-0000-0000-0000-00000000000a';
insert into r select 'clearing the mark puts them back',
  (select n from processed) = 3
  and (select cut from parts where category = 'DESKTOP' and model is null and part = 'MOTHERBOARD') = 2;

-- people refine the unit: a model moves the device and its parts
set local role authenticated;
update public.units set device_model_id = (select id from public.device_models where code = 'DELL-OPTIPLEX-SFF')
 where code = 'L2-20261024-132823_desktop';
insert into r select 'a model on the unit moves the device and its parts to that model',
  (select cut from parts where model = 'DELL-OPTIPLEX-SFF' and part = 'MOTHERBOARD') = 1
  and (select cut from parts where model = 'DELL-OPTIPLEX-SFF' and part = 'CHASSIS') = 1
  and (select cut from parts where category = 'DESKTOP' and model is null and part = 'MOTHERBOARD') = 1
  and (select n from processed) = 3;
do $$ begin
  insert into public.inventory_movements(workspace_id, item_kind, component_type_id, quantity, reason, lazarus_run_id)
  values ('11111111-1111-1111-1111-111111111111', 'component',
          (select id from public.component_types where code = 'FAN'), 1, 'recovered', 'eeeeeeee-0000-0000-0000-00000000000a');
  insert into r values ('members cannot log rows as a Lazarus run', false);
exception when insufficient_privilege then insert into r values ('members cannot log rows as a Lazarus run', true); end $$;

-- an X-ray unit started by an operator, then linked to the run
insert into public.units(id, workspace_id, code, device_category_id) values
  ('cccccccc-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','U-XRAY-1',
   (select id from public.device_categories where code = 'DESKTOP'));
reset role;
update public.lazarus_runs set unit_id = 'cccccccc-0000-0000-0000-000000000001' where id = 'eeeeeeee-0000-0000-0000-00000000000a';
insert into r select 'linking a run to an operator''s unit finishes it and drops the run''s own unit',
  (select status from public.units where code = 'U-XRAY-1') = 'processed'
  and (select status from public.units where code = 'L2-20261024-143654_desktop') = 'void'
  and (select n from processed) = 3;
insert into r select 'its parts move to the linked unit',
  (select sum(quantity) from public.inventory_movements
    where unit_id = 'cccccccc-0000-0000-0000-000000000001' and item_kind = 'component') = 2
  and (select sum(quantity) from public.inventory_movements m join public.units u on u.id = m.unit_id
        where u.code = 'L2-20261024-143654_desktop' and m.item_kind = 'component') = 0
  and (select cut from parts where category = 'DESKTOP' and model is null and part = 'MOTHERBOARD') = 1;

select test, ok from r order by ok, test;
rollback;
