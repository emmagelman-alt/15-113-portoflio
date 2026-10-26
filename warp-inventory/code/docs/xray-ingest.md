# X-ray ingest API (`xray-ingest`)

> **Status: contract only.** The tables exist (`supabase/migrations/20261023180000_inventory.sql`), but the Edge Function isn't built yet. Build the X-ray side against this page; the function will match it. Raise anything that doesn't fit the machine before it's built.

Base URL: `https://<project-ref>.supabase.co/functions/v1/xray-ingest`

## How it fits together
- **Unit:** what's on the tray, usually one device, sometimes several of a kind (a tray of phones). It carries a printed label with its code (`U-000123`, or your own format). An operator starts a unit in Warp, or the X-ray PC creates one from a label it reads.
- **Scan:** one X-ray image (one view) of a unit. Upload the original as the X-ray writes it (16-bit TIFF, DICOM, PNG) and, if you can, an 8-bit preview that browsers can show.
- After the upload, the scan is queued. The analysis worker finds components and saves them as detections, and people review them in Warp → Inventory.
- Lazarus fetches a unit's scans and detections by unit ID or label code to plan its cuts.

## Auth
Same as `lazarus-ingest` (Warp's Lazarus upload API, not included in this copy): a device token from **Members → Devices**, sent as `Authorization: Bearer lzr_<64 hex>`. Make a separate device for each X-ray PC (e.g. "X-ray station 1"). Every device in the workspace can read units and scans, so Lazarus can read what the X-ray uploaded. A device can only change scans it uploaded.

## Errors
Same shape as `lazarus-ingest`: `{"error": {"code": "<code>", "message": "<human readable>"}}`, with the same `400` / `401` / `404` / `405` / `413` / `500` codes, plus:

| HTTP | code | when |
|---|---|---|
| 409 | `not_uploaded` | `complete` was called before the original file reached storage |
| 409 | `unit_closed` | changing a unit that is already processed or void |

## Endpoints

### `GET /ping`
Checks the token. → `200 {"ok": true, "device_id": "<uuid>"}`

### `POST /units`: create or find a unit (idempotent by `code`)
```json
{
  "code": "U-000123",            // optional label code, 1-64 of [A-Za-z0-9._-]; omit to get a new U-###### code
  "device_category": "DESKTOP",  // optional catalog code (Warp → Inventory → Catalog)
  "device_model_id": null,       // optional uuid; sets the category too
  "device_count": 1,             // optional, default 1 (a tray of 12 phones = 12)
  "notes": null                  // optional
}
```
→ `201 {"unit_id": "<uuid>", "code": "U-000123", "created": true}`, or `200` with `"created": false` when the code exists. For an existing unit only the fields you send change, and only while it is open.

### `POST /scans`: register one scan and get upload URLs (idempotent by `external_scan_id`)
```json
{
  "external_scan_id": "XR1-20261023-0042-top", // required, 1-200 chars, unique per device; re-sending returns the same scan
  "unit_code": "U-000123",          // or "unit_id"; optional. An unknown code creates the unit. Omit to assign it in Warp later
  "view": "top",                    // optional <= 40 chars: top, side, ...
  "captured_at": "2026-10-23T18:00:00Z", // optional ISO 8601 (default: now)
  "pixel_size_mm": 0.139,           // optional, at the bed plane, if calibrated
  "metadata": { "kv": 160, "ma": 0.5, "exposure_ms": 800, "detector": "...", "software": "..." }, // optional <= 256 KB
  "original": {                     // required
    "filename": "top.tiff", "content_type": "image/tiff", "size_bytes": 33554432,
    "width": 4096, "height": 4096, "bit_depth": 16
  },
  "preview": {                      // optional 8-bit PNG/JPEG, same aspect ratio; the worker makes one if missing
    "filename": "top_preview.png", "content_type": "image/png", "size_bytes": 2400000
  }
}
```
→ `201`
```json
{
  "scan_id": "<uuid>", "unit_id": "<uuid or null>", "status": "uploading",
  "uploads": {
    "original": { "method": "PUT", "url": "https://…/storage/v1/object/upload/sign/xray-scans/<workspace_id>/<scan_id>/top.tiff?token=…",
                  "headers": { "Content-Type": "image/tiff", "x-upsert": "true" }, "expires_in": 7200 },
    "preview":  { "method": "PUT", "url": "…", "headers": { "Content-Type": "image/png", "x-upsert": "true" }, "expires_in": 7200 }
  }
}
```
Then `PUT` each file's raw bytes to its `url` with its `headers`. Limits: original ≤ 100 MB, preview ≤ 25 MB, URLs valid for 2 hours. Re-sending the same `external_scan_id` returns the same `scan_id` with fresh URLs, and uploads overwrite.

### `POST /scans/{scan_id}/complete`: confirm the upload and queue analysis
```json
{
  "registered": true,              // optional: the image is registered to the Lazarus bed
  "bed_transform": [0.139, 0, 12.5, 0, 0.139, -40.25, 0, 0, 1], // optional 3x3 row-major, image px -> bed mm
  "pixel_size_mm": 0.139           // optional
}
```
→ `200 {"scan_id": "<uuid>", "status": "queued"}`. Returns `409 not_uploaded` if the original isn't in storage yet.

### `GET /units/{unit_id or code}/xray`: everything Lazarus needs for one unit
`?detections=counted` (default: the model's confident answers plus people's boxes) or `?detections=all` (adds ones waiting for review and rejected ones).

→ `200`
```json
{
  "unit": { "unit_id": "<uuid>", "code": "U-000123", "device_category": "DESKTOP", "device_model": null,
            "device_count": 1, "status": "open" },
  "scans": [{
    "scan_id": "<uuid>", "view": "top", "captured_at": "2026-10-23T18:00:00Z", "status": "analyzed",
    "width": 4096, "height": 4096, "bit_depth": 16, "pixel_size_mm": 0.139,
    "registered": true, "bed_transform": [0.139, 0, 12.5, 0, 0.139, -40.25, 0, 0, 1],
    "original_url": "<signed, 1 hour>", "preview_url": "<signed, 1 hour>",
    "detections": [{
      "detection_id": "<uuid>", "component_type": "MOTHERBOARD", "component_id": null, "component_name": null,
      "box": { "x": 812, "y": 640, "w": 2210, "h": 1830 },
      "polygon": null,                         // [[x, y], …] in image px when the model gives a mask
      "bed_polygon_mm": [[125.4, 48.7], …],    // box or polygon in bed mm; only when registered
      "source": "model", "confidence": 0.93, "status": "auto"
    }]
  }]
}
```

## Coordinates
- **Image pixels:** origin at the top-left of the *original* image (not the preview), x to the right, y down.
- **`bed_transform`:** a 3×3 homography, row-major `[h11, h12, h13, h21, h22, h23, h31, h32, h33]`. It maps `[x, y, 1]` in image pixels to `[X, Y, W]`, and the bed position in mm is `(X/W, Y/W)`. It uses the same bed frame Lazarus registers its stereo scans to, via the fiducial markers on the bed.
- **Registration needs markers the X-ray can see.** Printed markers don't show on an X-ray. Put metal markers on the tray at known bed positions, ideally beside the printed fiducials, so both machines see them.
- **An X-ray has no depth.** Lazarus still takes height and top Z from its own stereo scan.

## X-ray side: what to build
1. **Get images off the machine.** Find how it exports: a folder, vendor software or a DICOM node, and in what format and bit depth.
2. **Uploader on the X-ray PC.** Watch the export, read the unit's label (a barcode scanner at the station, or a filename convention), then call `POST /scans`, `PUT` the bytes and `POST …/complete`. Retry `500`s with backoff. Re-sending is safe.
3. **Preview.** An 8-bit PNG windowed so the internals are visible. Optional: the worker makes one if it's missing.
4. **Pixel size.** Calibrate millimetres per pixel at the bed plane.
5. **Registration.** Add metal markers to the tray and compute `bed_transform`. Until then, send `registered: false`. Inventory counts still work, but Lazarus can't use the positions.
6. **Settings.** Send kV, mA, exposure, filter, detector and software version in `metadata`. They matter when the model is trained.

## Python sketch
```python
import requests, os
F = "https://<project-ref>.supabase.co/functions/v1/xray-ingest"
H = {"Authorization": f"Bearer {os.environ['XRAY_DEVICE_TOKEN']}"}

def upload(path, unit_code, view, scan_id):
    size = os.path.getsize(path)
    r = requests.post(f"{F}/scans", headers=H, json={
        "external_scan_id": scan_id, "unit_code": unit_code, "view": view,
        "original": {"filename": os.path.basename(path), "content_type": "image/tiff", "size_bytes": size, "bit_depth": 16},
    }, timeout=30)
    r.raise_for_status()
    s = r.json()
    up = s["uploads"]["original"]
    with open(path, "rb") as f:
        requests.put(up["url"], headers=up["headers"], data=f, timeout=600).raise_for_status()
    requests.post(f"{F}/scans/{s['scan_id']}/complete", headers=H, json={}, timeout=30).raise_for_status()
    return s["scan_id"]
```

## Data model
- `units`: one per tray load, unique `code` per workspace. `lazarus_runs.unit_id` links a Lazarus run to it.
- `xray_scans`: one per image, unique `(device_id, external_scan_id)`. Status: `uploading` → `queued` → `analyzing` → `analyzed` / `failed`.
- `scan_detections`: boxes in image pixels. `source` is `human` or `model`. `status` is one of:
  - `auto`: the model was sure enough, so it counts.
  - `needs_review`: waiting for a person.
  - `confirmed`: a person drew or approved it.
  - `rejected`
- Files live in the private `xray-scans` bucket at `<workspace_id>/<scan_id>/<file>`. Workspace members can read them. The function hands out signed upload URLs.
- The analysis worker (service role) takes queued scans with `claim_xray_scans()` and matches crops with `match_components()` (pgvector).

Warp's tests for these tables are in `supabase/tests/inventory_sanity.sql`.
