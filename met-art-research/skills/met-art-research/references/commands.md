# Command reference

Replace `/plugin/skills/met-art-research/scripts/met.py` with the actual absolute
script path. Global options `--cache-dir` and `--refresh` go **before** the command.
Every command has `--help`. Searches create a new directory, never overwrite one.
Use the Python interpreter selected during [runtime setup](runtime.md).

```sh
python3 /plugin/skills/met-art-research/scripts/met.py search "botanical" "flowers" --has-images --output /tmp/met-botanical
python3 /plugin/skills/met-art-research/scripts/met.py scan /tmp/met-botanical --max-records 500 --public-domain --has-images
python3 /plugin/skills/met-art-research/scripts/met.py show /tmp/met-botanical --selection --limit 8 --offset 0
python3 /plugin/skills/met-art-research/scripts/met.py contact-sheet --session /tmp/met-botanical --selection --limit 24 --output-dir /tmp/met-references
python3 /plugin/skills/met-art-research/scripts/met.py images 436535 45734 --size original --output-dir /tmp/met-references
```

## Search

`search [QUERIES ...]`: unions multiple queries, deduplicating artwork IDs.
The API source supports `--scope all|title|tags|artist`, `--department ID`,
`--medium 'Silk|Textiles'`, `--geo 'France|Japan'`, `--date-begin YEAR`,
`--date-end YEAR`, `--has-images`, `--highlights`, and `--max-ids N` per query.
Dates must be supplied as a pair, including negative years for BCE.
Run `departments` to obtain current numeric IDs. Without queries, filter-only API
searches are supported. Output records coverage separately for each query.
`--max-ids 0` means all reachable IDs (at most 10,000 per query).

`search --source csv [QUERIES ...]` downloads and caches the official CSV, then
streams every row. `--csv PATH` uses an existing file and implies CSV mode.
Each query requires all its whitespace-separated terms; queries are combined with OR.
Matching is case-insensitive substring matching in the selected fields, not the API's
search semantics. The default fields are title, artist, culture, medium, classification,
object name, period, dynasty, country, city, region, and tags. `--geo` matches country,
city, and region. CSV department filtering uses a full department name, not a number.
CSV date filtering uses overlap with the requested date range. Unknown dates fail
that filter. `--public-domain`, `--contains`, and `--exclude` work directly in CSV
mode. `--has-images` is rejected because the CSV has no image URLs; scan instead.
`--max-ids` applies only to API search; CSV always examines all rows.

## Scan and browse

`scan SESSION [--max-records N] [--retry-errors]` saves one API record per artwork
and resumes automatically. Default 500 new requests; 0 processes all remaining.
The command writes `selection.json` from all currently saved matching records,
including CSV records if present. `--has-images` only admits API-verified images.
Filters are reapplied on every invocation; repeat the same flags when continuing.
Failed records are retained and retried only with `--retry-errors` or `--refresh`.
Run one scan at a time per session.

`show SESSION [--selection] [--offset N] [--limit N] [--ids ID ...]` reads saved
records without network access. Default limit 8. `--contains TERM` (repeatable AND),
`--exclude TERM` (repeatable), `--public-domain`, and `--has-images` further filter.
`--fields title,dimensions,artistPrefix,artistDisplayName,artistSuffix,creditLine,objectURL`
returns only specified catalog fields plus object ID. Use returned `next_offset`
with the same filters to continue. CSV `image_available: null` means not yet checked.

## Images and contact sheets

`images ID ... [--size preview|original] [--additional] [--output-dir PATH]` downloads
images and returns their absolute paths and metadata. Preview is the default;
additional views are supplied as originals. A missing preview falls back to the
primary original. Each image has a source/checksum sidecar; unchanged images are reused.
An existing unrelated destination file is never overwritten. Complete details and
per-image errors are saved to a unique `manifest-*.json`. Stdout lists at most 12
images by default; change `--report-limit` or read the manifest selectively.

Instead of IDs, use `--session SESSION [--selection] --offset N --limit N` to select
a candidate page (default 24). Explicit IDs and a session page are combined and
deduplicated. Image commands fetch API records regardless of whether a session was scanned.

`contact-sheet ID ... [--output-dir PATH] [--columns 4] [--rows 6]` accepts the same
session paging flags. It downloads previews and writes JPEG sheets plus `mapping.json`
in a unique subdirectory. Each tile shows a number and Met object ID; the mapping
retains titles, image paths, source links, rights, and credits. It preserves image
aspect ratios and orientation. A malformed image is marked on the sheet and reported
as an error. Use the host's image-viewing tool to inspect the returned sheets.

## Storage, refresh, and output

Default cache: `~/.cache/met-art-research`, configurable via `MET_CACHE_DIR` or
`--cache-dir`. API JSON is cached for seven days; search responses for one hour.
The CSV persists until an explicit refresh. `--refresh` bypasses caches; on scan,
it also re-fetches previously saved records, bounded by `--max-records`.
Session paths are self-contained except for API caches. Images remain wherever
`--output-dir` points, or in the cache's `images` directory by default.

JSON summaries go to stdout; progress goes to stderr. Fatal command errors exit 1;
interruption exits 130. Batches continue after per-artwork errors and report failure
counts even if every item failed; inspect those counts, not just the exit status.

Sources: https://metmuseum.github.io/ and https://github.com/metmuseum/openaccess
