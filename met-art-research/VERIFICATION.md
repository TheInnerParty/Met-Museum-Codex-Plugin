# Verification — November 10, 2026

## Automated checks

17 offline tests passed on Python 3.15.2 with Pillow 13.0.0. Coverage includes:

- API pagination, empty results, final partial pages, the 10,000-ID boundary,
  and deduplication across queries.
- Resuming scans, explicit error retries, and filtering without refetching.
- Streaming a 15,000-row CSV fixture with Unicode, BCE date ranges, public-domain
  filtering, and correct official accession/rights column names.
- Exact download destinations containing spaces, cached image reuse, missing
  images, HTML masquerading as an image, and unrelated-file preservation.
- Contact-sheet pagination and artwork-number mappings.
- API cache reuse and explicit refresh.

## Live checks

- `search sunflowers --max-ids 3` reported **178 total matches** and retrieved
  the first **3 IDs**, as requested by the test limit. Scanning fetched those
  3 records. The search correctly reported `complete: false`. Omitting
  `--max-ids` retrieves all matches within the API's 10,000-result search window.
- Downloaded the official GitHub LFS-backed collection CSV and streamed all
  **503,207 rows** for `lotus` with the public-domain filter, saving **382 matches**.
  Counts reflect the dataset retrieved on the verification date.
- Preview downloads and a contact sheet for IDs 436535, 437329, and 45734 succeeded.
  Opened the generated sheet and visually verified three intact, correctly labeled
  thumbnails with preserved aspect ratios.
- An original image of 436535 downloaded to an explicitly chosen directory
  containing spaces, with its absolute path and catalog/rights manifest.
- ID 437133 had no image in its returned API record; the batch reported that
  per-artwork failure and continued successfully for an available image.

## Limits of verification

Other supported Python versions and automatic skill invocation in a new Codex
chat were not tested.

## Local installation

Installed version 0.1.0 through `codex plugin add` and confirmed that Codex lists
it as installed and enabled. Verified that the installed skill matches the source
and generated a contact sheet successfully using the installed script.

## Version 0.1.1 documentation check

Generated and visually checked a six-artwork contact sheet from a `Cats` title
search. All six records provided images and were marked public domain. Updated
the README commands and image credits to match this example.
