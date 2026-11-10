"""Offline behavior tests; no requests to the Met are made here."""
import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "skills/met-art-research/scripts/met.py"
spec = importlib.util.spec_from_file_location("met", SCRIPT)
met = importlib.util.module_from_spec(spec)
spec.loader.exec_module(met)


def record(i, image=True):
    return {"objectID": i, "title": "Birds and flowers", "artistPrefix": "Attributed to",
            "artistDisplayName": "Example artist", "objectDate": "ca. 1800",
            "medium": "Ink on paper", "isPublicDomain": True, "_source": "api",
            "primaryImage": f"https://images.metmuseum.org/{i}.jpg" if image else "",
            "primaryImageSmall": f"https://images.metmuseum.org/small/{i}.jpg" if image else "",
            "objectURL": f"https://www.metmuseum.org/art/collection/search/{i}"}


class FakeClient:
    def __init__(self, cache):
        self.cache = Path(cache)
        self.refresh = False
        self.calls = []
        self.fail = set()

    def record(self, i):
        self.calls.append(i)
        if i in self.fail:
            raise OSError("temporarily unavailable")
        return record(i, image=i != 2)


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.client = FakeClient(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def args(self, *words):
        return met.parser().parse_args(["--cache-dir", str(self.root), *map(str, words)])

    def session(self, ids):
        p = self.root / "session"
        p.mkdir()
        met.write_json(p / "candidates.json", {"objectIDs": ids})
        return p

    def test_large_api_search_window_and_deduplication(self):
        calls = []
        def fetch(endpoint, params, ttl):
            calls.append(params)
            offset, limit = params["offset"], params["limit"]
            return {"total": 15000, "objectIDs": list(range(offset + 1, offset + limit + 1))}
        self.client.json = fetch
        args = self.args("search", "birds", "flowers")
        result = met.cmd_search(args, self.client)
        self.assertEqual(result["candidates"], 10000)
        self.assertEqual(len(calls), 40)
        self.assertTrue(all(c["offset"] + c["limit"] <= 10000 for c in calls))
        self.assertTrue(all(q["search_window_limited"] and not q["complete"] for q in result["coverage"]["queries"]))
        self.assertLess(len(json.dumps(result)), 2000)

    def test_api_empty_and_partial_final_page(self):
        self.client.json = lambda endpoint, params, ttl: {"total": 0, "objectIDs": None}
        result = met.cmd_search(self.args("search", "nothing"), self.client)
        self.assertEqual(result["candidates"], 0)
        self.assertTrue(result["coverage"]["queries"][0]["complete"])

    def test_api_partial_final_page(self):
        self.client.json = lambda endpoint, params, ttl: {
            "total": 503, "objectIDs": list(range(params["offset"] + 1, min(503, params["offset"] + params["limit"]) + 1))}
        result = met.cmd_search(self.args("search", "birds"), self.client)
        self.assertEqual(result["candidates"], 503)
        self.assertTrue(result["coverage"]["queries"][0]["complete"])

    def test_scan_resumes_and_show_pages_without_repeating_records(self):
        p = self.session([1, 2, 3, 4, 5])
        args = self.args("scan", p, "--max-records", 2, "--has-images")
        first = met.cmd_scan(args, self.client)
        second = met.cmd_scan(args, self.client)
        self.assertEqual(first["remaining_to_scan"], 3)
        self.assertEqual(second["remaining_to_scan"], 1)
        self.assertEqual(self.client.calls, [1, 2, 3, 4])
        shown = met.cmd_show(self.args("show", p, "--selection", "--limit", 2), self.client)
        self.assertEqual([r["id"] for r in shown["records"]], [1, 3])
        self.assertEqual(shown["next_offset"], 2)
        self.assertEqual(shown["records"][0]["attribution"], "Attributed to Example artist")

    def test_failed_scan_requires_explicit_retry(self):
        p = self.session([1, 2])
        self.client.fail = {2}
        met.cmd_scan(self.args("scan", p), self.client)
        again = met.cmd_scan(self.args("scan", p), self.client)
        self.assertEqual(again["processed_this_run"], 0)
        self.client.fail.clear()
        retry = met.cmd_scan(self.args("scan", p, "--retry-errors"), self.client)
        self.assertEqual(retry["processed_this_run"], 1)
        self.assertEqual(retry["failed_records"], 0)

    def test_filters_can_be_changed_without_refetching(self):
        p = self.session([1, 2, 3])
        met.cmd_scan(self.args("scan", p), self.client)
        self.client.calls.clear()
        selection = met.cmd_scan(self.args("scan", p, "--exclude", "flowers"), self.client)
        self.assertEqual(selection["matching_saved_records"], 0)
        self.assertEqual(self.client.calls, [])

    def test_csv_streams_15000_rows_bce_filters_and_unicode(self):
        path = self.root / "MetObjects.csv"
        fields = ["Object ID", "Title", "Is Public Domain", "Object Begin Date", "Object End Date"]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for i in range(1, 15001):
                writer.writerow({"Object ID": i, "Title": "Égyptian lotus" if i % 2 else "Textile",
                                 "Is Public Domain": "True", "Object Begin Date": -300, "Object End Date": -200})
        args = self.args("search", "lotus", "--source", "csv", "--csv", path,
                         "--date-begin", -250, "--date-end", -100, "--public-domain")
        result = met.cmd_search(args, self.client)
        self.assertEqual(result["coverage"]["rows_examined"], 15000)
        self.assertEqual(result["candidates"], 7500)
        page = met.cmd_show(self.args("show", result["session"]), self.client)
        self.assertEqual(len(page["records"]), 8)
        self.assertIsNone(page["records"][0]["image_available"])
        self.assertEqual(self.client.calls, [])

    def test_csv_image_availability_is_not_guessed(self):
        args = self.args("search", "--source", "csv", "--has-images")
        with self.assertRaisesRegex(ValueError, "does not record image"):
            met.cmd_search(args, self.client)

    def test_csv_unknown_boolean_is_not_false(self):
        row = met.normalize_csv({"Object ID": "1", "Is Public Domain": ""})
        self.assertIsNone(row["isPublicDomain"])

    def test_official_csv_accession_and_rights_columns(self):
        row = met.normalize_csv({"Object ID": "1", "Object Number": "1979.486.1",
                                 "Rights and Reproduction": "Credit example"})
        self.assertEqual(row["accessionNumber"], "1979.486.1")
        self.assertEqual(row["rightsAndReproduction"], "Credit example")
        self.assertEqual(met.check_url(met.DATASET), met.DATASET)

    def test_invalid_date_pair_and_existing_search_not_overwritten(self):
        with self.assertRaisesRegex(ValueError, "both"):
            met.cmd_search(self.args("search", "--date-begin", 1700), self.client)
        with self.assertRaises(FileExistsError):
            met.cmd_search(self.args("search", "--output", self.root), self.client)

    def test_untrusted_image_url_is_rejected(self):
        for url in ("http://images.metmuseum.org/a.jpg", "https://metmuseum.org.evil.test/a", "file:///tmp/a",
                    "https://raw.githubusercontent.com/other/repo/main/a", "https://user@images.metmuseum.org/a"):
            with self.assertRaises(ValueError):
                met.check_url(url)

    def test_image_cache_exact_destination_and_missing_image(self):
        self.client.open = lambda url: io.BytesIO(b"\xff\xd8\xffsample")
        args = self.args("images", 1, 2, "--output-dir", self.root / "chosen directory", "--size", "original")
        first = met.cmd_images(args, self.client)
        self.assertEqual(first["downloaded_or_cached"], 1)
        self.assertEqual(first["failed"], 1)
        path = Path(first["images"][0]["path"])
        self.assertEqual(path.name, "1-primary-original.jpg")
        self.assertEqual(path.parent, (self.root / "chosen directory").resolve())
        self.client.open = lambda url: self.fail("Image should have been cached")
        second = met.cmd_images(args, self.client)
        self.assertEqual(second["downloaded_or_cached"], 1)

    def test_image_rejects_html_and_preserves_unrelated_file(self):
        base = self.root / "image"
        self.client.open = lambda url: io.BytesIO(b"<html>blocked</html>")
        with self.assertRaisesRegex(ValueError, "not a supported"):
            met.download_image(self.client, "https://images.metmuseum.org/a.jpg", base)
        (self.root / "image.jpg").write_bytes(b"existing")
        self.client.open = lambda url: io.BytesIO(b"\xff\xd8\xffnew")
        with self.assertRaisesRegex(ValueError, "unrelated"):
            met.download_image(self.client, "https://images.metmuseum.org/a.jpg", base)
        self.assertEqual((self.root / "image.jpg").read_bytes(), b"existing")

    def test_contact_sheet_mapping_multiple_sheets(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is optional; install requirements to test contact sheets")
        buf = io.BytesIO()
        Image.new("RGB", (100, 200), "red").save(buf, format="JPEG")
        self.client.open = lambda url: io.BytesIO(buf.getvalue())
        args = self.args("contact-sheet", 1, 3, 4, "--columns", 2, "--rows", 1,
                         "--output-dir", self.root / "sheets")
        result = met.cmd_contact_sheet(args, self.client)
        self.assertEqual(len(result["sheets"]), 2)
        mapping = met.read_json(result["mapping"])
        self.assertEqual([r["id"] for r in mapping["items"]], [1, 3, 4])
        self.assertEqual([r["number"] for r in mapping["items"]], [1, 2, 3])
        self.assertEqual([r["sheet"] for r in mapping["items"]], [1, 1, 2])
        with Image.open(result["sheets"][0]) as image:
            self.assertEqual(image.size, (560, 250))

    def test_session_image_paging_and_explicit_ids_deduplicate(self):
        p = self.session([1, 2, 3, 4])
        args = self.args("images", 3, "--session", p, "--offset", 1, "--limit", 2)
        self.assertEqual(met.selected_ids(args), [3, 2])

    def test_http_cache_refresh(self):
        client = met.Client(self.root)
        calls = []
        def open_json(url):
            calls.append(url)
            return io.BytesIO(b'{"total":0,"objectIDs":null}')
        client.open = open_json
        client.json("/v1.1/search", {"q": "a & b"})
        client.json("/v1.1/search", {"q": "a & b"})
        self.assertEqual(len(calls), 1)
        self.assertIn("a+%26+b", calls[0])
        client.refresh = True
        client.json("/v1.1/search", {"q": "a & b"})
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
