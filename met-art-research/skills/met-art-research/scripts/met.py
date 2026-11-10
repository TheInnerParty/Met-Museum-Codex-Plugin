#!/usr/bin/env python3
"""Local Met collection research. JSON on stdout; progress on stderr."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = "https://collectionapi.metmuseum.org/public/collection"
DATASET = "https://media.githubusercontent.com/media/metmuseum/openaccess/master/MetObjects.csv"
WINDOW = 10000
CSV_FIELDS = {
    "Object ID": "objectID", "Title": "title", "Artist Display Name": "artistDisplayName",
    "Artist Prefix": "artistPrefix", "Artist Suffix": "artistSuffix", "Culture": "culture",
    "Object Date": "objectDate", "Object Begin Date": "objectBeginDate",
    "Object End Date": "objectEndDate", "Medium": "medium", "Department": "department",
    "Classification": "classification", "Object Name": "objectName", "Period": "period",
    "Dynasty": "dynasty", "Country": "country", "City": "city", "Region": "region",
    "Dimensions": "dimensions", "Credit Line": "creditLine", "Object Number": "accessionNumber",
    "Link Resource": "objectURL", "Is Public Domain": "isPublicDomain",
    "Is Highlight": "isHighlight", "Tags": "tags", "Rights and Reproduction": "rightsAndReproduction",
    "Metadata Date": "metadataDate", "Repository": "repository", "Geography Type": "geographyType",
}
SEARCH_FIELDS = ("title", "artistDisplayName", "culture", "medium", "classification",
                 "objectName", "period", "dynasty", "country", "city", "region", "tags")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def absolute(path):
    return Path(path).expanduser().resolve()


def read_json(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".met-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def write_json(path, data):
    atomic_bytes(path, (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode())


def emit(data):
    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def log(message):
    print(message, file=sys.stderr, flush=True)


def check_url(url):
    parsed = urllib.parse.urlparse(url)
    host = parsed.hostname or ""
    allowed = host == "metmuseum.org" or host.endswith(".metmuseum.org")
    allowed = allowed or (host == "raw.githubusercontent.com" and
                          parsed.path.startswith("/metmuseum/openaccess/"))
    allowed = allowed or (host == "media.githubusercontent.com" and
                          parsed.path.startswith("/media/metmuseum/openaccess/"))
    if parsed.scheme != "https" or parsed.username or parsed.password or not allowed:
        raise ValueError("Download URL is outside the Met's HTTPS sources")
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Client:
    def __init__(self, cache, refresh=False):
        self.cache = absolute(cache)
        self.refresh = refresh
        self.opener = urllib.request.build_opener(SafeRedirect())
        self.last_request = 0.0

    def open(self, url):
        check_url(url)
        for attempt in range(4):
            time.sleep(max(0, 0.2 - (time.monotonic() - self.last_request)))
            self.last_request = time.monotonic()
            try:
                return self.opener.open(urllib.request.Request(url, headers={
                    "User-Agent": "MetArtResearch/0.1 (+https://metmuseum.github.io/)",
                    "Accept": "*/*",
                }), timeout=30)
            except urllib.error.HTTPError as e:
                if e.code not in (429, 500, 502, 503, 504) or attempt == 3:
                    raise
                retry = e.headers.get("Retry-After", "")
                delay = min(float(retry), 30) if retry.isdigit() else 2 ** attempt
                e.close()
            except (urllib.error.URLError, TimeoutError):
                if attempt == 3:
                    raise
                delay = 2 ** attempt
            time.sleep(delay)

    def json(self, endpoint, params=None, ttl=86400 * 7):
        url = API + endpoint
        if params:
            url += "?" + urllib.parse.urlencode(params)
        key = hashlib.sha256(url.encode()).hexdigest()
        target = self.cache / "api" / (key + ".json")
        if not self.refresh and target.exists() and time.time() - target.stat().st_mtime < ttl:
            try:
                return read_json(target)
            except (ValueError, OSError):
                pass
        with self.open(url) as response:
            raw = response.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("Unexpectedly large API response")
        data = json.loads(raw)
        write_json(target, data)
        return data

    def record(self, object_id):
        data = dict(self.json(f"/v1/objects/{int(object_id)}"))
        if data.get("objectID") != int(object_id):
            raise ValueError("API returned an unexpected object ID")
        data["_source"] = "api"
        return data


def load_records(session):
    records = {}
    path = Path(session) / "records.jsonl"
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    row = json.loads(line)
                    records[int(row["objectID"])] = row
    return records


def append_record(session, record):
    # Atomic per-record file replacement avoids truncated JSONL after interruption.
    # Scans append through a journal directory, merged by session_records().
    write_json(Path(session) / "scanned" / f"{record['objectID']}.json", record)


def session_records(session):
    records = load_records(session)
    for path in (Path(session) / "scanned").glob("*.json"):
        row = read_json(path)
        records[int(row["objectID"])] = row
    return records


def make_session(args):
    path = absolute(args.output) if args.output else absolute(args.cache_dir) / "searches" / uuid.uuid4().hex[:12]
    path.mkdir(parents=True, exist_ok=False)
    log(f"Search session: {path}")
    return path


def source_blob(record, fields=SEARCH_FIELDS):
    return " ".join(str(record.get(k, "")) for k in fields).casefold()


def matches(record, args):
    if record.get("_error"):
        return False
    blob = source_blob(record)
    if any(s.casefold() not in blob for s in getattr(args, "contains", [])):
        return False
    if any(s.casefold() in blob for s in getattr(args, "exclude", [])):
        return False
    if getattr(args, "public_domain", False) and record.get("isPublicDomain") is not True:
        return False
    if getattr(args, "has_images", False) and not record.get("primaryImage"):
        return False
    return True


def summary(record):
    attribution = " ".join(str(record.get(k) or "") for k in
                           ("artistPrefix", "artistDisplayName", "artistSuffix")).strip()
    result = {"id": record["objectID"], "title": record.get("title", ""),
              "attribution": attribution or record.get("culture") or "Not recorded",
              "date": record.get("objectDate", ""), "medium": record.get("medium", ""),
              "public_domain": record.get("isPublicDomain"),
              "image_available": bool(record.get("primaryImage")) if record.get("_source") == "api" else None,
              "url": record.get("objectURL", ""), "source": record.get("_source", "api")}
    return result


def search_api(args, client, path):
    ids, seen, searches = [], set(), []
    for query in args.queries or [""]:
        params = {"q": query} if query else {}
        for cli, api in (("department", "departmentId"), ("medium", "medium"),
                         ("geo", "geoLocation"), ("date_begin", "dateBegin"), ("date_end", "dateEnd")):
            value = getattr(args, cli)
            if value is not None:
                params[api] = value
        if args.scope != "all":
            params[{"title": "title", "tags": "tags", "artist": "artistOrCulture"}[args.scope]] = "true"
        if args.has_images:
            params["hasImages"] = "true"
        if args.highlights:
            params["isHighlight"] = "true"
        offset, total = 0, None
        cap = min(args.max_ids or WINDOW, WINDOW)
        while offset < cap:
            page_size = min(500, cap - offset)
            data = client.json("/v1.1/search", {**params, "offset": offset, "limit": page_size}, ttl=3600)
            page = data.get("objectIDs") or []
            total = int(data["total"])
            if not page:
                break
            for item in page:
                item = int(item)
                if item not in seen:
                    ids.append(item)
                    seen.add(item)
            offset += len(page)
            if offset >= total:
                break
        searches.append({"query": query, "filters": params, "total": total,
                         "retrieved": offset, "complete": offset >= total,
                         "search_window_limited": total > WINDOW})
        # Checkpoint each completed query; a failed query never appears as complete.
        write_json(path / "candidates.json", {"objectIDs": ids})
        write_json(path / "search.json", {"source": "api", "created": now(), "queries": searches,
                                          "unique_candidates": len(ids), "finished": False})
    return ids, {"source": "api", "queries": searches, "finished": True}


def download_dataset(client):
    path = client.cache / "dataset" / "MetObjects.csv"
    if path.exists() and not client.refresh:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".download-", dir=path.parent)
    log("Downloading the Met Open Access CSV; this can be several hundred MB.")
    try:
        with os.fdopen(fd, "wb") as out, client.open(DATASET) as response:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 2 * 1024 ** 3:
                    raise ValueError("Dataset exceeded 2 GiB")
                out.write(chunk)
        with open(temp, encoding="utf-8-sig", newline="") as f:
            header = next(csv.reader(f))
        if "Object ID" not in header or "Title" not in header:
            raise ValueError("Downloaded file is not the Met dataset")
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return path


def normalize_csv(row):
    record = {dest: row.get(src, "") for src, dest in CSV_FIELDS.items()}
    record["objectID"] = int(record["objectID"])
    for field in ("isPublicDomain", "isHighlight"):
        value = record[field].strip().casefold()
        record[field] = True if value in ("true", "1") else False if value in ("false", "0") else None
    for field in ("objectBeginDate", "objectEndDate"):
        try:
            record[field] = int(record[field])
        except (ValueError, TypeError):
            record[field] = None
    record["_source"] = "csv"
    return record


def search_csv(args, client, path):
    if args.has_images:
        raise ValueError("CSV does not record image availability; use scan --has-images after CSV search")
    if args.department and str(args.department).isdigit():
        raise ValueError("CSV search uses a department name, not an API department ID")
    dataset = absolute(args.csv) if args.csv else download_dataset(client)
    fields = {"all": SEARCH_FIELDS, "title": ("title",), "tags": ("tags",),
              "artist": ("artistDisplayName", "culture")}[args.scope]
    ids, seen, examined = [], set(), 0
    csv.field_size_limit(16 * 1024 * 1024)
    with dataset.open(encoding="utf-8-sig", newline="") as f, (path / "records.jsonl").open("w", encoding="utf-8") as out:
        reader = csv.DictReader(f)
        if not {"Object ID", "Title"}.issubset(reader.fieldnames or []):
            raise ValueError("CSV requires Object ID and Title columns")
        for row in reader:
            examined += 1
            record = normalize_csv(row)
            if not matches(record, args):
                continue
            blob = source_blob(record, fields)
            if args.queries and not any(all(term in blob for term in q.casefold().split()) for q in args.queries):
                continue
            if args.department and args.department.casefold() != record["department"].casefold():
                continue
            if args.medium and not any(v.casefold() in record["medium"].casefold() for v in args.medium.split("|")):
                continue
            if args.geo and not any(v.casefold() in source_blob(record, ("country", "city", "region")) for v in args.geo.split("|")):
                continue
            if args.highlights and record["isHighlight"] is not True:
                continue
            if args.date_begin is not None:
                begin, end = record["objectBeginDate"], record["objectEndDate"]
                if begin is None or end is None or end < args.date_begin or begin > args.date_end:
                    continue
            if record["objectID"] not in seen:
                seen.add(record["objectID"])
                ids.append(record["objectID"])
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
    return ids, {"source": "csv", "dataset": str(dataset), "dataset_file_modified": dataset.stat().st_mtime,
                 "rows_examined": examined, "queries": args.queries, "complete": True,
                 "matching": "Case-insensitive substring terms; AND within each query, OR between queries",
                 "finished": True}


def cmd_search(args, client):
    if (args.date_begin is None) != (args.date_end is None):
        raise ValueError("Supply both --date-begin and --date-end")
    if args.date_begin is not None and args.date_begin > args.date_end:
        raise ValueError("--date-begin must not exceed --date-end")
    if args.source == "api" and (args.public_domain or args.contains or args.exclude):
        raise ValueError("Apply --public-domain/--contains/--exclude during scan, or use --source csv")
    if args.source == "api" and args.department and not str(args.department).isdigit():
        raise ValueError("API search uses a numeric department ID; run departments to list IDs")
    path = make_session(args)
    ids, meta = search_api(args, client, path) if args.source == "api" else search_csv(args, client, path)
    write_json(path / "candidates.json", {"objectIDs": ids})
    meta.update(created=now(), unique_candidates=len(ids))
    meta["arguments"] = {k: v for k, v in vars(args).items() if k not in ("func",)}
    write_json(path / "search.json", meta)
    return {"session": str(path), "candidates": len(ids),
            "coverage": {k: v for k, v in meta.items() if k not in ("arguments",)},
            "next": "scan SESSION to fetch metadata; show SESSION to page through saved records"}


def cmd_scan(args, client):
    path = absolute(args.session)
    ids = read_json(path / "candidates.json")["objectIDs"]
    records = session_records(path)
    pending = [i for i in ids if args.refresh or i not in records or
               (records[i].get("_source") != "api" and not records[i].get("_error")) or
               (args.retry_errors and records[i].get("_error"))]
    batch = pending[:args.max_records] if args.max_records else pending
    errors = []
    for index, object_id in enumerate(batch):
        try:
            record = client.record(object_id)
        except (ValueError, OSError) as e:
            record = {"objectID": object_id, "_error": str(e), "_attempted": now()}
            errors.append(record)
        append_record(path, record)
        records[object_id] = record
        if (index + 1) % 100 == 0:
            log(f"Processed {index + 1}/{len(batch)} records")
    matched = [i for i in ids if i in records and matches(records[i], args)]
    write_json(path / "selection.json", {"objectIDs": matched,
               "filters": {"contains": args.contains, "exclude": args.exclude,
                           "has_images": args.has_images, "public_domain": args.public_domain},
               "created": now()})
    return {"session": str(path), "candidates": len(ids), "processed_this_run": len(batch),
            "api_records_saved": sum(r.get("_source") == "api" for r in records.values()),
            "remaining_to_scan": len(pending) - len(batch), "matching_saved_records": len(matched),
            "failed_records": sum(bool(r.get("_error")) for r in records.values()),
            "errors_this_run": errors[:5], "selection": str(path / "selection.json"),
            "next": "show SESSION --selection; repeat scan with the same filters to continue"}


def cmd_show(args, client):
    path = absolute(args.session)
    ids = read_json(path / ("selection.json" if args.selection else "candidates.json"))["objectIDs"]
    records = session_records(path)
    available = [records[i] for i in ids if i in records and matches(records[i], args)]
    if args.ids:
        wanted = set(args.ids)
        available = [r for r in available if r["objectID"] in wanted]
    page = available[args.offset:args.offset + args.limit]
    if args.fields:
        fields = list(dict.fromkeys(["objectID"] + args.fields.split(",")))
        result = [{k: r.get(k) for k in fields} for r in page]
    else:
        result = [summary(r) for r in page]
    return {"matching_saved_records": len(available), "candidate_ids": len(ids),
            "offset": args.offset, "returned": len(result),
            "next_offset": args.offset + len(page) if args.offset + len(page) < len(available) else None,
            "records": result}


def selected_ids(args):
    ids = list(args.ids)
    if args.session:
        name = "selection.json" if args.selection else "candidates.json"
        candidates = read_json(absolute(args.session) / name)["objectIDs"]
        ids.extend(candidates[args.offset:args.offset + args.limit])
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise ValueError("Supply artwork IDs or --session with a nonempty page")
    return ids


def image_extension(data):
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("Response is not a supported JPEG, PNG, or WebP image")


def download_image(client, url, base):
    check_url(url)
    sidecar = Path(str(base) + ".json")
    if sidecar.exists() and not client.refresh:
        saved = read_json(sidecar)
        path = Path(saved["path"])
        # Do not trust arbitrary paths in a modified sidecar.
        if path.parent == base.parent and path.stem == base.name and path.exists() and saved.get("url") == url:
            if hashlib.sha256(path.read_bytes()).hexdigest() == saved.get("sha256"):
                return path
    with client.open(url) as response:
        data = response.read(60 * 1024 * 1024 + 1)
    if len(data) > 60 * 1024 * 1024:
        raise ValueError("Image exceeds 60 MiB")
    path = Path(str(base) + image_extension(data))
    if path.exists():
        if not sidecar.exists() or read_json(sidecar).get("url") != url:
            raise ValueError(f"Refusing to replace an unrelated file: {path}")
    atomic_bytes(path, data)
    write_json(sidecar, {"path": str(path), "url": url, "sha256": hashlib.sha256(data).hexdigest(), "saved": now()})
    return path


def collect_images(args, client):
    output = absolute(args.output_dir) if args.output_dir else client.cache / "images"
    output.mkdir(parents=True, exist_ok=True)
    items, errors = [], []
    for object_id in selected_ids(args):
        try:
            record = client.record(object_id)
            primary = record.get("primaryImageSmall") if args.size == "preview" else record.get("primaryImage")
            primary = primary or record.get("primaryImage")
            urls = [("primary", primary)]
            if args.additional:
                urls.extend((f"additional-{i + 1}", url) for i, url in enumerate(record.get("additionalImages") or []))
            for label, url in urls:
                if not url:
                    errors.append({"id": object_id, "view": label, "error": "Image unavailable"})
                    continue
                try:
                    # Additional views are supplied as originals by the API.
                    size = args.size if label == "primary" else "original"
                    path = download_image(client, url, output / f"{object_id}-{label}-{size}")
                    items.append({**summary(record), "path": str(path), "image_url": url,
                                  "view": label, "requested_size": size,
                                  "rights": record.get("rightsAndReproduction", ""),
                                  "credit": record.get("creditLine", ""),
                                  "accession_number": record.get("accessionNumber", "")})
                except (ValueError, OSError) as e:
                    errors.append({"id": object_id, "view": label, "error": str(e)})
        except (ValueError, OSError) as e:
            errors.append({"id": object_id, "error": str(e)})
    manifest = output / f"manifest-{uuid.uuid4().hex[:12]}.json"
    write_json(manifest, {"created": now(), "images": items, "errors": errors})
    return manifest, items, errors


def cmd_images(args, client):
    manifest, items, errors = collect_images(args, client)
    return {"manifest": str(manifest), "downloaded_or_cached": len(items), "failed": len(errors),
            "images": items[:args.report_limit], "errors": errors[:5],
            "omitted_from_response": max(0, len(items) - args.report_limit),
            "next": "Open returned local paths with an image-viewing tool; downloading is not inspection"}


def cmd_contact_sheet(args, client):
    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError as e:
        raise ValueError("Contact sheets need Pillow. Install the plugin requirements in a virtual environment.") from e
    args.size, args.additional = "preview", False
    manifest, items, errors = collect_images(args, client)
    output = manifest.parent / ("contact-sheets-" + uuid.uuid4().hex[:12])
    output.mkdir()
    sheets, mapping = [], []
    tile_w, tile_h = 280, 250
    per_sheet = args.columns * args.rows
    for start in range(0, len(items), per_sheet):
        page = items[start:start + per_sheet]
        columns = min(args.columns, len(page))
        rows = (len(page) + columns - 1) // columns
        canvas = Image.new("RGB", (columns * tile_w, rows * tile_h), "#f4f1ea")
        draw = ImageDraw.Draw(canvas)
        for index, item in enumerate(page):
            number = start + index + 1
            x, y = (index % columns) * tile_w, (index // columns) * tile_h
            try:
                with Image.open(item["path"]) as image:
                    thumb = ImageOps.contain(ImageOps.exif_transpose(image).convert("RGB"), (tile_w - 16, tile_h - 40))
                    canvas.paste(thumb, (x + (tile_w - thumb.width) // 2, y + 6 + (tile_h - 40 - thumb.height) // 2))
                mapping.append({"number": number, "sheet": len(sheets) + 1, **item})
            except (OSError, ValueError) as e:
                errors.append({"id": item["id"], "error": str(e)})
                draw.text((x + 8, y + 90), "Unable to decode image", fill="black")
            draw.text((x + 10, y + tile_h - 24), f"{number} | Met {item['id']}", fill="black")
        path = output / f"sheet-{len(sheets) + 1:03d}.jpg"
        canvas.save(path, quality=90)
        sheets.append(str(path))
    mapping_path = output / "mapping.json"
    write_json(mapping_path, {"created": now(), "sheets": sheets, "items": mapping, "errors": errors,
                              "image_manifest": str(manifest)})
    return {"sheets": sheets, "mapping": str(mapping_path), "thumbnails": len(mapping),
            "failed": len(errors), "errors": errors[:5],
            "next": "Open sheet paths with an image-viewing tool. Map numbers to IDs using mapping.json."}


def nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return number


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def add_filters(parser):
    parser.add_argument("--contains", action="append", default=[], help="Require substring in catalog fields; repeat for AND")
    parser.add_argument("--exclude", action="append", default=[], help="Exclude substring in catalog fields")
    parser.add_argument("--public-domain", action="store_true")
    parser.add_argument("--has-images", action="store_true")


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--cache-dir", default=os.environ.get("MET_CACHE_DIR", "~/.cache/met-art-research"))
    root.add_argument("--refresh", action="store_true", help="Refresh cached API records, images, or CSV")
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("search", help="Save candidates from paginated API search or streamed CSV")
    p.add_argument("queries", nargs="*")
    p.add_argument("--source", choices=("api", "csv"), default="api")
    p.add_argument("--csv", help="Existing Met-format CSV; implies --source csv")
    p.add_argument("--output", help="New search directory (must not already exist)")
    p.add_argument("--max-ids", type=nonnegative, default=0, help="API IDs per query; 0 means the full reachable window")
    p.add_argument("--scope", choices=("all", "title", "tags", "artist"), default="all")
    p.add_argument("--department")
    p.add_argument("--medium")
    p.add_argument("--geo")
    p.add_argument("--date-begin", type=int)
    p.add_argument("--date-end", type=int)
    p.add_argument("--highlights", action="store_true")
    add_filters(p)
    p.set_defaults(func=cmd_search)
    p = sub.add_parser("scan", help="Resume fetching candidate records; filters write selection.json")
    p.add_argument("session")
    p.add_argument("--max-records", type=nonnegative, default=500, help="New fetches this run; 0 means all remaining")
    p.add_argument("--retry-errors", action="store_true")
    add_filters(p)
    p.set_defaults(func=cmd_scan)
    p = sub.add_parser("show", help="Page through saved metadata without network requests")
    p.add_argument("session")
    p.add_argument("--selection", action="store_true")
    p.add_argument("--ids", nargs="+", type=positive)
    p.add_argument("--offset", type=nonnegative, default=0)
    p.add_argument("--limit", type=positive, default=8)
    p.add_argument("--fields", help="Comma-separated original API field names")
    add_filters(p)
    p.set_defaults(func=cmd_show)
    for name, function in (("images", cmd_images), ("contact-sheet", cmd_contact_sheet)):
        p = sub.add_parser(name)
        p.add_argument("ids", nargs="*", type=positive)
        p.add_argument("--session")
        p.add_argument("--selection", action="store_true")
        p.add_argument("--offset", type=nonnegative, default=0)
        p.add_argument("--limit", type=positive, default=24)
        p.add_argument("--output-dir")
        if name == "images":
            p.add_argument("--size", choices=("preview", "original"), default="preview")
            p.add_argument("--additional", action="store_true")
            p.add_argument("--report-limit", type=nonnegative, default=12)
        else:
            p.add_argument("--columns", type=positive, choices=range(1, 7), default=4)
            p.add_argument("--rows", type=positive, choices=range(1, 7), default=6)
        p.set_defaults(func=function)
    p = sub.add_parser("departments", help="List current department IDs")
    p.set_defaults(func=lambda args, client: client.json("/v1/departments"))
    return root


def main(argv=None):
    args = parser().parse_args(argv)
    if getattr(args, "csv", None):
        args.source = "csv"
    try:
        result = args.func(args, Client(args.cache_dir, args.refresh))
        emit(result)
        return 0
    except (ValueError, OSError, csv.Error, KeyError) as e:
        emit({"error": str(e), "command": args.command})
        return 1
    except KeyboardInterrupt:
        emit({"error": "Interrupted; completed scans remain saved", "command": args.command})
        return 130


if __name__ == "__main__":
    sys.exit(main())
