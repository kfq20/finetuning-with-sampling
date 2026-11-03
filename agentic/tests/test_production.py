import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from http.client import IncompleteRead

from append_rewrite.terminus.production import safe_artifacts, tree, dump
from append_rewrite.terminus.suffix_score import (
    NativeFullStreamClient,
    ResilientFullStreamClient,
)


class ProductionSafety(unittest.TestCase):
    def test_artifact_scope(self):
        for paths in ([], ["/tests/"], ["/app/../secret"]):
            with self.assertRaises(ValueError):
                safe_artifacts(paths)
        self.assertEqual(safe_artifacts(["/app/output/"]), ["/app/output/"])

    def test_mode_identity_and_atomic_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            f = root / "code"
            f.write_text("same bytes")
            f.chmod(0o644)
            before = tree(root)
            f.chmod(0o755)
            self.assertNotEqual(before, tree(root))
            dump(root / "receipt.json", {"complete": True})
            self.assertEqual(
                json.loads((root / "receipt.json").read_text()), {"complete": True}
            )
            self.assertFalse(list(root.glob("*.tmp")))

    def test_only_failed_scores_retry(self):
        client = object.__new__(ResilientFullStreamClient)
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(
                NativeFullStreamClient,
                "score",
                side_effect=[IncompleteRead(b"partial"), {"mean_logprob": -1}],
            ) as score,
            patch("time.sleep"),
        ):
            result = client.score(None, journal=Path(d) / "score")
            self.assertEqual(score.call_count, 2)
            self.assertEqual(result["score_transport_attempts"], 2)
            self.assertFalse(result["generation_retried"])
        for status in (401, 403, 429):
            with (
                tempfile.TemporaryDirectory() as d,
                patch.object(
                    NativeFullStreamClient,
                    "score",
                    side_effect=HTTPError("https://example", status, "error", {}, None),
                ) as score,
            ):
                with self.assertRaises(HTTPError):
                    client.score(None, journal=Path(d) / "score")
                self.assertEqual(score.call_count, 1)

    def test_validation_failure_never_retry(self):
        with (
            tempfile.TemporaryDirectory() as d,
            patch.object(
                NativeFullStreamClient,
                "score",
                side_effect=ValueError("wrong token ids"),
            ) as score,
        ):
            with self.assertRaises(ValueError):
                object.__new__(ResilientFullStreamClient).score(
                    None, journal=Path(d) / "score"
                )
            self.assertEqual(score.call_count, 1)
