"""Contract test pinning scripts/update-index.py's index format to scripts/enrich-index.py's.

Which labels live under the top-level ApplicationMetadata block is one rule with two
independent implementations, mirroring the label-filter split in test_label_policy.py:

- scripts/update-index.py (vendored into application repos, must stay a single
  standard-library-only file, so it cannot import enrich-index.py) *writes* the format:
  it pulls APP_LEVEL_LABELS off each image and records them once under ApplicationMetadata,
  keyed by app-id/flatpak-arch.
- scripts/enrich-index.py (used by check-metadata.yml against the live remote) *reads* it:
  it must never write those labels back onto an image, or it would undo the move.

The two copies are not merged for the same single-file reason. This file asserts they
agree on the shape of the format, so a change to one that silently diverges from the other
fails here instead of as an asymmetric publish/audit mismatch:

- publisher moves the labels where the auditor does not expect them (or the auditor looks
  where the publisher does not write): an entry publishes cleanly but audits wrong, and
  republishing can never clear it
- the label *set* drifts -- one copy treats an app-level label the other does not

See tuna-os/flatpak-index#149.
"""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


update_index = _load("update_index", "update-index.py")
enrich_index = _load("enrich_index", "enrich-index.py")


def _image_entry(labels):
    return {
        "Digest": "sha256:" + "0" * 64,
        "MediaType": "application/vnd.oci.image.manifest.v1+json",
        "OS": "linux",
        "Architecture": "amd64",
        "Tags": ["latest"],
        "Labels": labels,
    }


class AppLevelLabelsFormatContractTests(unittest.TestCase):
    def test_both_copies_declare_the_same_app_level_labels(self):
        """The two declarations name the same app-level labels, independent of order."""
        self.assertEqual(
            set(update_index.APP_LEVEL_LABELS),
            set(enrich_index.APP_LEVEL_LABELS),
        )

    def test_publisher_moves_every_auditor_app_level_label_off_the_image(self):
        """Every label the auditor (enrich-index.py) treats as app-level must be moved off
        the image by the publisher (update-index.py), or enrich reads it back from the
        registry and re-attaches it -- undoing the move and re-introducing the old,
        per-image format."""
        labels = {
            "org.flatpak.ref": "app/com.example.One/x86_64/master",
            "org.flatpak.metadata": "[Application]\nname=com.example.One\n",
            "org.flatpak.body": "Name: com.example.One\n",
            "org.flatpak.commit-metadata.xa.metadata": "base64data",
            "org.flatpak.commit": "sha256:still-on-image",
        }
        index = {"Registry": "https://ghcr.io", "Results": []}
        update_index.merge_entry(index, "tuna-os/one", _image_entry(labels))

        image = index["Results"][0]["Images"][0]
        for name in enrich_index.APP_LEVEL_LABELS:
            self.assertNotIn(
                name,
                image["Labels"],
                f"{name}: the auditor treats it as app-level but the publisher left it "
                "on the image, so enrich will restore it and re-introduce the old format",
            )

        stored = index.get("ApplicationMetadata", {})
        self.assertEqual(
            set(stored),
            {"com.example.One/x86_64"},
            "app-level labels must be recorded once under ApplicationMetadata, keyed "
            "by app-id/flatpak-arch, not repeated on the image",
        )
        for name in enrich_index.APP_LEVEL_LABELS:
            self.assertEqual(
                stored["com.example.One/x86_64"][name],
                labels[name],
                f"{name}: ApplicationMetadata value does not match what was published",
            )

    def test_publisher_app_level_labels_are_all_auditor_app_level_labels(self):
        """Nothing the publisher treats as app-level is invisible to the auditor: a label
        the publisher moves to ApplicationMetadata but the auditor does not list would never
        be recognised as app-level on audit, so it would silently land on the image."""
        for name in update_index.APP_LEVEL_LABELS:
            self.assertIn(
                name,
                enrich_index.APP_LEVEL_LABELS,
                f"{name}: the publisher treats it as app-level but the auditor does not",
            )


if __name__ == "__main__":
    unittest.main()
