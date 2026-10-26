-- Inventory sanity test (20261023180000_inventory.sql and the starter catalog): run as superuser after
-- the migrations; everything is rolled back. Every row of the final select should be ok = true.
begin;
insert into auth.users(id,email) values
 ('00000000-0000-0000-0000-00000000000a','alice@example.com'),
 ('00000000-0000-0000-0000-00000000000b','bob@example.com');
create temp table r(test text, ok boolean); grant all on r to anon, authenticated, service_role;
create temp table ids(k text primary key, id uuid); grant all on ids to anon, authenticated, service_role;

set local role authenticated;
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}',true);
insert into public.workspaces(id,name) values ('11111111-1111-1111-1111-111111111111','Andean');

-- starter catalog
insert into r select 'seed loads the catalog', public.inventory_seed_starter_catalog('11111111-1111-1111-1111-111111111111')
  = '{"device_categories": 23, "device_models": 3, "component_types": 26, "bom_lines": 100}'::jsonb;
insert into r select 'seed again adds nothing', public.inventory_seed_starter_catalog('11111111-1111-1111-1111-111111111111')
  = '{"device_categories": 0, "device_models": 0, "component_types": 0, "bom_lines": 0}'::jsonb;
insert into r select 'seed adds the desktops Lazarus has processed, under Desktop',
  (select count(*) from public.device_models m join public.device_categories c on c.id = m.device_category_id
    where c.code = 'DESKTOP' and m.code in ('DELL-OPTIPLEX-SFF', 'DELL-OPTIPLEX-MT', 'HP-DESKTOP-TOWER')) = 3;
insert into r select 'model parts lists keep seen and unconfirmed apart',
  (select b.quantity = 1 and b.notes like 'Seen in Lazarus%' from public.device_bom b
     join public.device_models m on m.id = b.device_model_id join public.component_types t on t.id = b.component_type_id
    where m.code = 'DELL-OPTIPLEX-MT' and t.code = 'OPTICAL-DRIVE')
  and (select b.quantity = 0.3 and b.notes like 'Drive bay empty%' from public.device_bom b
     join public.device_models m on m.id = b.device_model_id join public.component_types t on t.id = b.component_type_id
    where m.code = 'DELL-OPTIPLEX-MT' and t.code = 'HDD');
insert into r select 'desktop is inside computers',
  (select p.code from public.device_categories c join public.device_categories p on p.id = c.parent_id where c.code = 'DESKTOP') = 'COMPUTERS';
insert into r select 'catalog rows are stamped with their creator',
  (select bool_and(created_by = '00000000-0000-0000-0000-00000000000a') from public.component_types);
insert into ids select lower(code), id from public.device_categories where code in ('DESKTOP', 'LAPTOP', 'ALL-IN-ONE', 'COMPUTERS');
insert into ids select lower(code), id from public.component_types where code in ('MOTHERBOARD', 'FAN', 'RAM', 'HDD', 'SSD', 'PSU', 'OPTICAL-DRIVE');

-- intake: 50 desktops, 400 kg of laptops
insert into public.intake_batches(id, workspace_id, source) values
  ('aaaaaaaa-0000-0000-0000-000000000001','11111111-1111-1111-1111-111111111111','Pallet from a client');
insert into public.intake_lines(id, batch_id, device_category_id, quantity) values
  ('aaaaaaaa-0000-0000-0000-000000000002','aaaaaaaa-0000-0000-0000-000000000001',(select id from ids where k='desktop'),50);
insert into public.intake_lines(batch_id, device_category_id, weight_kg) values
  ('aaaaaaaa-0000-0000-0000-000000000001',(select id from ids where k='laptop'),400);
insert into r select 'intake line takes the batch workspace',
  (select workspace_id from public.intake_lines where id='aaaaaaaa-0000-0000-0000-000000000002') = '11111111-1111-1111-1111-111111111111';
insert into r select '50 desktops on hand',
  (select on_hand from public.inventory_device_stock where device_category_id=(select id from ids where k='desktop')) = 50;
insert into r select '400 kg of laptops received, no count',
  (select received_kg = 400 and on_hand = 0 from public.inventory_device_stock where device_category_id=(select id from ids where k='laptop'));
insert into r select 'expected motherboards from the category list',
  (select expected from public.inventory_components_expected where component_type_id=(select id from ids where k='motherboard')) = 50;
insert into r select 'fractional list lines (0.5 optical drives each)',
  (select expected from public.inventory_components_expected where component_type_id=(select id from ids where k='optical-drive')) = 25;

-- fixing a typo (50 -> 48) adds rows instead of editing them
update public.intake_lines set quantity = 48 where id = 'aaaaaaaa-0000-0000-0000-000000000002';
insert into r select 'edited line: 48 on hand',
  (select on_hand from public.inventory_device_stock where device_category_id=(select id from ids where k='desktop')) = 48;
insert into r select 'edit added an undo row and a new row',
  (select count(*) = 3 and sum(quantity) = 48 from public.inventory_movements where intake_line_id='aaaaaaaa-0000-0000-0000-000000000002');
update public.intake_lines set notes = 'checked' where id = 'aaaaaaaa-0000-0000-0000-000000000002';
insert into r select 'editing only the notes adds nothing',
  (select count(*) = 3 from public.inventory_movements where intake_line_id='aaaaaaaa-0000-0000-0000-000000000002');
with d as (delete from public.intake_lines where id = 'aaaaaaaa-0000-0000-0000-000000000002' returning 1)
insert into r select 'intake lines cannot be deleted', (select count(*) from d) = 0;

-- a model with its own parts list replaces the category's list
insert into public.device_models(id, workspace_id, device_category_id, manufacturer, name) values
  ('aaaaaaaa-0000-0000-0000-000000000003','11111111-1111-1111-1111-111111111111',(select id from ids where k='all-in-one'),'Apple','iMac 27-inch (2019)');
insert into public.device_bom(workspace_id, device_model_id, component_type_id, quantity) values
  ('11111111-1111-1111-1111-111111111111','aaaaaaaa-0000-0000-0000-000000000003',(select id from ids where k='ram'),4);
insert into public.intake_lines(batch_id, device_model_id, quantity) values
  ('aaaaaaaa-0000-0000-0000-000000000001','aaaaaaaa-0000-0000-0000-000000000003',10);
insert into r select 'model fills in its category',
  (select device_category_id from public.intake_lines where device_model_id='aaaaaaaa-0000-0000-0000-000000000003') = (select id from ids where k='all-in-one');
insert into r select 'model list lines keep the category empty',
  (select device_category_id is null from public.device_bom where device_model_id='aaaaaaaa-0000-0000-0000-000000000003');
insert into r select 'expected RAM: 48 x 2 + 10 x 4',
  (select expected from public.inventory_components_expected where component_type_id=(select id from ids where k='ram')) = 136;
insert into r select 'model list replaces the category list',
  (select expected from public.inventory_components_expected where component_type_id=(select id from ids where k='motherboard')) = 48;

-- units
insert into public.units(id, workspace_id, device_category_id) values
  ('aaaaaaaa-0000-0000-0000-000000000004','11111111-1111-1111-1111-111111111111',(select id from ids where k='desktop'));
insert into r select 'unit gets a label code', (select code ~ '^U-[0-9]{6}$' from public.units where id='aaaaaaaa-0000-0000-0000-000000000004');
update public.units set status = 'processed' where id = 'aaaaaaaa-0000-0000-0000-000000000004';
insert into r select 'processed unit: 47 on hand, processed_at set',
  (select on_hand = 47 and processed = 1 from public.inventory_device_stock where device_category_id=(select id from ids where k='desktop'))
  and (select processed_at is not null from public.units where id='aaaaaaaa-0000-0000-0000-000000000004');
update public.units set status = 'void' where id = 'aaaaaaaa-0000-0000-0000-000000000004';
insert into r select 'voiding it puts the device back',
  (select on_hand = 48 and processed = 0 from public.inventory_device_stock where device_category_id=(select id from ids where k='desktop'))
  and (select processed_at is null from public.units where id='aaaaaaaa-0000-0000-0000-000000000004');
update public.units set status = 'processed' where id = 'aaaaaaaa-0000-0000-0000-000000000004';
insert into public.units(id, workspace_id) values ('aaaaaaaa-0000-0000-0000-000000000005','11111111-1111-1111-1111-111111111111');
do $$ begin
  update public.units set status = 'processed' where id = 'aaaaaaaa-0000-0000-0000-000000000005';
  insert into r values ('unit without a device type cannot be processed', false);
exception when check_violation then insert into r values ('unit without a device type cannot be processed', true); end $$;

-- X-ray scans: two views of the processed desktop
insert into public.xray_scans(id, workspace_id, unit_id, view, storage_path, filename, status) values
  ('aaaaaaaa-0000-0000-0000-000000000006','11111111-1111-1111-1111-111111111111','aaaaaaaa-0000-0000-0000-000000000004','top',
   '11111111-1111-1111-1111-111111111111/aaaaaaaa-0000-0000-0000-000000000006/top.tiff','top.tiff','queued'),
  ('aaaaaaaa-0000-0000-0000-000000000007','11111111-1111-1111-1111-111111111111','aaaaaaaa-0000-0000-0000-000000000004','side',
   '11111111-1111-1111-1111-111111111111/aaaaaaaa-0000-0000-0000-000000000007/side.tiff','side.tiff','queued');
do $$ begin
  insert into public.xray_scans(workspace_id, storage_path, filename) values ('11111111-1111-1111-1111-111111111111','elsewhere/x.tiff','x.tiff');
  insert into r values ('scan files must be in the scan''s folder', false);
exception when check_violation then insert into r values ('scan files must be in the scan''s folder', true); end $$;
do $$ begin
  update public.xray_scans set registered = true where id = 'aaaaaaaa-0000-0000-0000-000000000006';
  insert into r values ('people cannot set registration', false);
exception when insufficient_privilege then insert into r values ('people cannot set registration', true); end $$;

insert into public.scan_detections(scan_id, component_type_id, x, y, w, h) values
  ('aaaaaaaa-0000-0000-0000-000000000006',(select id from ids where k='motherboard'),10,10,300,200),
  ('aaaaaaaa-0000-0000-0000-000000000006',(select id from ids where k='fan'),400,10,80,80),
  ('aaaaaaaa-0000-0000-0000-000000000006',(select id from ids where k='fan'),400,100,80,80),
  ('aaaaaaaa-0000-0000-0000-000000000007',(select id from ids where k='motherboard'),10,10,300,40),
  ('aaaaaaaa-0000-0000-0000-000000000007',(select id from ids where k='fan'),400,10,80,80);
insert into r select 'two views of one unit count once (the view with the most)',
  (select identified = 1 and found_in = 1 from public.inventory_components_identified where component_type_id=(select id from ids where k='motherboard'))
  and (select identified = 2 from public.inventory_components_identified where component_type_id=(select id from ids where k='fan'));
insert into r select 'a person''s box is confirmed and reviewed by them',
  (select bool_and(source = 'human' and status = 'confirmed' and reviewed_by = '00000000-0000-0000-0000-00000000000a') from public.scan_detections);
insert into r select 'detections take the scan''s workspace',
  (select bool_and(workspace_id = '11111111-1111-1111-1111-111111111111') from public.scan_detections);

-- the worker (service role): queue, model answers, matching
reset role; set local role service_role;
select set_config('request.jwt.claims','{"role":"service_role"}',true);
insert into r select 'worker claims one queued scan', (select count(*) from public.claim_xray_scans(1, 'test-model')) = 1;
insert into r select 'next claim gets the other scan only', (select count(*) from public.claim_xray_scans(5, 'test-model')) = 1;
insert into r select 'nothing left to claim', (select count(*) from public.claim_xray_scans(5)) = 0;
create temp table before_reg as select captured_at, created_at from public.xray_scans where id = 'aaaaaaaa-0000-0000-0000-000000000006';
update public.xray_scans set registered = true, pixel_size_mm = 0.139,
       bed_transform = '{0.139,0,12.5, 0,0.139,-40.25, 0,0,1}' where id = 'aaaaaaaa-0000-0000-0000-000000000006';
insert into r select 'registration round-trips exactly',
  (select registered and bed_transform = '{0.139,0,12.5,0,0.139,-40.25,0,0,1}'::double precision[] and pixel_size_mm = 0.139
          and (captured_at, created_at) = (select captured_at, created_at from before_reg)
     from public.xray_scans where id = 'aaaaaaaa-0000-0000-0000-000000000006');
insert into public.scan_detections(id, scan_id, component_type_id, x, y, w, h, source, model_version, confidence, status) values
  ('aaaaaaaa-0000-0000-0000-000000000008','aaaaaaaa-0000-0000-0000-000000000006',(select id from ids where k='hdd'),500,300,100,60,'model','test-model',0.42,'needs_review'),
  ('aaaaaaaa-0000-0000-0000-000000000009','aaaaaaaa-0000-0000-0000-000000000006',(select id from ids where k='psu'),600,300,100,100,'model','test-model',0.93,'auto');
insert into r select 'needs_review is not counted, auto is',
  not exists (select 1 from public.inventory_components_identified where component_type_id=(select id from ids where k='hdd'))
  and (select identified = 1 from public.inventory_components_identified where component_type_id=(select id from ids where k='psu'));
insert into r select 'model answer is kept as the prediction',
  (select predicted_component_type_id = component_type_id and reviewed_by is null from public.scan_detections where id='aaaaaaaa-0000-0000-0000-000000000008');

insert into public.component_reference_images(workspace_id, component_type_id, detection_id, embedding, embedding_model) values
  ('11111111-1111-1111-1111-111111111111',(select id from ids where k='motherboard'),
   (select id from public.scan_detections where scan_id='aaaaaaaa-0000-0000-0000-000000000006' and component_type_id=(select id from ids where k='motherboard')),
   '[1,0,0]','test-embed'),
  ('11111111-1111-1111-1111-111111111111',(select id from ids where k='psu'),'aaaaaaaa-0000-0000-0000-000000000009','[0,1,0]','test-embed'),
  ('11111111-1111-1111-1111-111111111111',(select id from ids where k='hdd'),'aaaaaaaa-0000-0000-0000-000000000008','[0,0,1,0]','other-embed');
insert into r select 'nearest reference is the motherboard',
  (select component_type_id from public.match_components('11111111-1111-1111-1111-111111111111','[0.9,0.1,0]','test-embed',
     (select id from ids where k='desktop')) order by distance limit 1) = (select id from ids where k='motherboard');
insert into r select 'matches only compare the same embedding model',
  (select count(*) from public.match_components('11111111-1111-1111-1111-111111111111','[0.9,0.1,0]','test-embed')) = 2;
insert into r select 'matches say which parts the device should have',
  (select bool_and(expected) from public.match_components('11111111-1111-1111-1111-111111111111','[0.9,0.1,0]','test-embed',
     (select id from ids where k='desktop')))
  and not (select bool_or(expected) from public.match_components('11111111-1111-1111-1111-111111111111','[0.9,0.1,0]','test-embed',
     (select id from ids where k='laptop')) where component_type_id=(select id from ids where k='psu'));

-- back to alice: review, stock log
reset role; set local role authenticated;
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}',true);
update public.scan_detections set component_type_id = (select id from ids where k='ssd') where id = 'aaaaaaaa-0000-0000-0000-000000000008';
insert into r select 'correcting a model answer confirms it and keeps the prediction',
  (select status = 'confirmed' and component_type_id = (select id from ids where k='ssd')
          and predicted_component_type_id = (select id from ids where k='hdd') and reviewed_by = '00000000-0000-0000-0000-00000000000a'
     from public.scan_detections where id='aaaaaaaa-0000-0000-0000-000000000008');
do $$ begin
  update public.scan_detections set source = 'human' where id = 'aaaaaaaa-0000-0000-0000-000000000008';
  insert into r values ('people cannot change a detection''s source', false);
exception when insufficient_privilege then insert into r values ('people cannot change a detection''s source', true); end $$;

insert into public.inventory_movements(workspace_id, item_kind, component_type_id, quantity, reason, unit_id) values
  ('11111111-1111-1111-1111-111111111111','component',(select id from ids where k='motherboard'),1,'recovered','aaaaaaaa-0000-0000-0000-000000000004');
insert into public.inventory_movements(workspace_id, item_kind, component_type_id, quantity, reason) values
  ('11111111-1111-1111-1111-111111111111','component',(select id from ids where k='motherboard'),-1,'extracted');
insert into r select 'recovered then extracted: none left in the bins',
  (select recovered = 1 and extracted = 1 and on_hand = 0 from public.inventory_component_stock where component_type_id=(select id from ids where k='motherboard'));

-- parts to cut, per kind of processed device
insert into ids select 'mt', id from public.device_models where code = 'DELL-OPTIPLEX-MT';
insert into public.units(workspace_id, device_model_id, status) values
  ('11111111-1111-1111-1111-111111111111',(select id from ids where k='mt'),'processed');
insert into public.inventory_movements(workspace_id, item_kind, component_type_id, from_device_model_id, quantity, reason) values
  ('11111111-1111-1111-1111-111111111111','component',(select id from ids where k='fan'),(select id from ids where k='mt'),2,'recovered');
insert into r select 'logged parts take the category of the device they came from',
  (select from_device_category_id = (select id from ids where k='desktop') from public.inventory_movements
    where from_device_model_id = (select id from ids where k='mt'));
insert into r select 'parts to cut: a model uses its own parts list',
  (select expected = 2 and cut = 2 from public.inventory_parts_to_cut('11111111-1111-1111-1111-111111111111')
    where device_model_id = (select id from ids where k='mt') and component_type_id = (select id from ids where k='fan'))
  and (select expected = 1 and cut = 0 from public.inventory_parts_to_cut('11111111-1111-1111-1111-111111111111')
    where device_model_id = (select id from ids where k='mt') and component_type_id = (select id from ids where k='optical-drive'));
insert into r select 'parts to cut: no model means the category list',
  (select expected = 1 and cut = 0 from public.inventory_parts_to_cut('11111111-1111-1111-1111-111111111111')
    where device_category_id = (select id from ids where k='desktop') and device_model_id is null
      and component_type_id = (select id from ids where k='motherboard'));
insert into r select 'parts to cut: parts with no source device stand alone',
  (select expected = 0 and cut = 1 from public.inventory_parts_to_cut('11111111-1111-1111-1111-111111111111')
    where device_category_id is null and component_type_id = (select id from ids where k='motherboard'));
do $$ begin
  insert into public.inventory_movements(workspace_id, item_kind, device_category_id, from_device_category_id, quantity, reason)
    values ('11111111-1111-1111-1111-111111111111','device',(select id from ids where k='desktop'),(select id from ids where k='desktop'),1,'adjustment');
  insert into r values ('device rows cannot have a source device', false);
exception when check_violation or insufficient_privilege then insert into r values ('device rows cannot have a source device', true); end $$;
do $$ begin
  insert into public.inventory_movements(workspace_id, item_kind, device_category_id, quantity, reason)
    values ('11111111-1111-1111-1111-111111111111','device',(select id from ids where k='desktop'),100,'received');
  insert into r values ('people cannot log received devices directly', false);
exception when insufficient_privilege then insert into r values ('people cannot log received devices directly', true); end $$;
do $$ begin
  insert into public.inventory_movements(workspace_id, item_kind, component_type_id, quantity, reason)
    values ('11111111-1111-1111-1111-111111111111','component',(select id from ids where k='fan'),1,'processed');
  insert into r values ('components cannot be processed', false);
exception when check_violation or insufficient_privilege then insert into r values ('components cannot be processed', true); end $$;
do $$ begin
  update public.inventory_movements set quantity = 999;
  insert into r values ('log rows cannot be edited', false);
exception when insufficient_privilege then insert into r values ('log rows cannot be edited', true); end $$;
do $$ begin
  delete from public.inventory_movements;
  insert into r values ('log rows cannot be deleted', false);
exception when insufficient_privilege then insert into r values ('log rows cannot be deleted', true); end $$;

do $$ begin
  update public.device_categories set parent_id = (select id from ids where k='desktop') where code = 'COMPUTERS';
  insert into r values ('a category cannot be inside itself', false);
exception when check_violation then insert into r values ('a category cannot be inside itself', true); end $$;
do $$ begin
  update public.intake_batches set workspace_id = '22222222-2222-2222-2222-222222222222' where id = 'aaaaaaaa-0000-0000-0000-000000000001';
  insert into r values ('rows cannot move to another workspace', false);
exception when insufficient_privilege then insert into r values ('rows cannot move to another workspace', true); end $$;
insert into storage.objects(bucket_id, name) values
  ('xray-scans','11111111-1111-1111-1111-111111111111/aaaaaaaa-0000-0000-0000-000000000006/top.tiff');

-- bob, in his own workspace
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-00000000000b","role":"authenticated"}',true);
insert into public.workspaces(id,name) values ('22222222-2222-2222-2222-222222222222','Bob WS');
insert into r select 'bob sees none of alice''s inventory',
  (select count(*) from public.device_categories) = 0 and (select count(*) from public.inventory_movements) = 0
  and (select count(*) from public.inventory_device_stock) = 0 and (select count(*) from public.xray_scans) = 0
  and (select count(*) from public.scan_detections) = 0 and (select count(*) from storage.objects) = 0;
do $$ begin
  insert into public.intake_lines(batch_id, device_category_id, quantity)
    values ('aaaaaaaa-0000-0000-0000-000000000001',(select id from ids where k='desktop'),5);
  insert into r values ('bob cannot add to alice''s batch', false);
exception when insufficient_privilege then insert into r values ('bob cannot add to alice''s batch', true); end $$;
insert into public.intake_batches(id, workspace_id) values ('bbbbbbbb-0000-0000-0000-000000000001','22222222-2222-2222-2222-222222222222');
do $$ begin
  insert into public.intake_lines(batch_id, device_category_id, quantity)
    values ('bbbbbbbb-0000-0000-0000-000000000001',(select id from ids where k='desktop'),5);
  insert into r values ('bob cannot use alice''s categories', false);
exception when foreign_key_violation then insert into r values ('bob cannot use alice''s categories', true); end $$;
do $$ begin
  perform public.inventory_seed_starter_catalog('11111111-1111-1111-1111-111111111111');
  insert into r values ('bob cannot seed alice''s workspace', false);
exception when insufficient_privilege then insert into r values ('bob cannot seed alice''s workspace', true); end $$;

-- bob as a plain member of alice's workspace
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-00000000000a","role":"authenticated"}',true);
insert into public.workspace_members values ('11111111-1111-1111-1111-111111111111','00000000-0000-0000-0000-00000000000b','member');
select set_config('request.jwt.claims','{"sub":"00000000-0000-0000-0000-00000000000b","role":"authenticated"}',true);
insert into r select 'member sees the stock',
  (select on_hand from public.inventory_device_stock where device_category_id=(select id from ids where k='desktop') and device_model_id is null) = 47;
with d as (delete from public.scan_detections where id = 'aaaaaaaa-0000-0000-0000-000000000009' returning 1)
insert into r select 'member cannot delete model answers', (select count(*) from d) = 0;
insert into public.scan_detections(id, scan_id, component_type_id, x, y, w, h) values
  ('bbbbbbbb-0000-0000-0000-000000000002','aaaaaaaa-0000-0000-0000-000000000007',(select id from ids where k='psu'),1,1,5,5);
with d as (delete from public.scan_detections where id = 'bbbbbbbb-0000-0000-0000-000000000002' returning 1)
insert into r select 'member can delete their own box', (select count(*) from d) = 1;
with d as (delete from public.device_categories where code = 'MIXED' returning 1)
insert into r select 'member cannot delete catalog entries', (select count(*) from d) = 0;

-- anon
reset role; set local role anon;
select set_config('request.jwt.claims','{"role":"anon"}',true);
do $$ begin
  perform count(*) from public.inventory_device_stock;
  insert into r values ('anon cannot read stock', false);
exception when insufficient_privilege then insert into r values ('anon cannot read stock', true); end $$;
do $$ begin
  perform count(*) from public.units;
  insert into r values ('anon cannot read units', false);
exception when insufficient_privilege then insert into r values ('anon cannot read units', true); end $$;

reset role;
insert into r select 'realtime publishes units, scans, detections and the log',
  (select count(*) from pg_publication_tables where pubname = 'supabase_realtime'
     and tablename in ('units', 'xray_scans', 'scan_detections', 'inventory_movements')) = 4;
select test, ok from r order by ok, test;
rollback;
