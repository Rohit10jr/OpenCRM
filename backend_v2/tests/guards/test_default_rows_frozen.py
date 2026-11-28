"""`configuration/data/default_rows.json` is frozen for `configuration/0012_default_rows`
(specs/CONFIGURATION.md §10.2; temp A-78 finding 6).

The migration reads the live file. A changed value would reach fresh installs only, and
a renamed key would break 0012 on a fresh install. The hash is of the parsed content in
a canonical dump, so a checkout's line endings do not change it.
"""

import hashlib
import json
from pathlib import Path

from django.conf import settings

FROZEN_SHA256 = "a94e8cc764923dc9be38bd09d6a913d0cb71277fae56f6f7c2b0774770d09350"
DATA_FILE = Path(settings.BASE_DIR) / "configuration" / "data" / "default_rows.json"


def _canonical_hash() -> str:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_the_default_rows_file_is_unchanged():
    assert _canonical_hash() == FROZEN_SHA256, (
        "configuration/data/default_rows.json changed. Its keys and shape are frozen for "
        "configuration/0012_default_rows, and a changed default needs a follow-up data "
        "migration that updates only the rows still equal to the old value (frozen as a "
        "literal there): docs/AS_BUILT.md §2, 'Adding a default row'. Then update "
        "FROZEN_SHA256 in this test, in the same commit as that migration."
    )
