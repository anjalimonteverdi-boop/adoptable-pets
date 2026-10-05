#!/usr/bin/env python3
"""End-to-end test of scripts/update.py against made-up data.

Copies the project to a temp folder, runs two simulated days, and checks
shelters-only filtering, paging, new-today badges and likely-adopted tracking.
Run: python tests/test_update.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(proj, *args, ok=True):
    r = subprocess.run([sys.executable, "scripts/update.py", *args], cwd=proj,
                       capture_output=True, text=True, env={"PATH": "/usr/bin:/bin"})
    assert (r.returncode == 0) == ok, r.stdout + r.stderr
    return r


def main():
    subprocess.run([sys.executable, str(ROOT / "tests/make_sample.py")], check=True)
    with tempfile.TemporaryDirectory() as tmp:
        proj = Path(tmp) / "p"
        shutil.copytree(ROOT, proj, ignore=shutil.ignore_patterns("data"))
        (proj / "docs/data").mkdir()
        data = proj / "docs/data/bay-area.json"

        # No key and no sample: clear error, nothing written.
        r = run(proj, ok=False)
        assert "RESCUEGROUPS_API_KEY" in r.stderr
        assert not data.exists()

        # Day 1.
        run(proj, "--sample", "tests/sample_day1.json", "--today", "2026-10-06")
        d1 = json.loads(data.read_text())
        orgs = {a["org"]["name"] for a in d1["animals"]}
        assert "Sample Rescue Group" not in orgs, "rescues should be excluded by default"
        assert all(a["org"]["type"] == "Shelter" for a in d1["animals"])
        assert d1["summary"]["first_run"] is True
        assert not any(a["new"] for a in d1["animals"]), "no new badges on the first run"
        assert all(a["photo"].startswith("https://placehold.co/500") for a in d1["animals"])
        ids1 = {a["id"] for a in d1["animals"]}

        # Day 2.
        run(proj, "--sample", "tests/sample_day2.json", "--today", "2026-10-07")
        d2 = json.loads(data.read_text())
        ids2 = {a["id"] for a in d2["animals"]}
        new = {a["id"] for a in d2["animals"] if a["new"]}
        left = {g["id"] for g in d2["recently_left"]}
        assert new == ids2 - ids1, (new, ids2 - ids1)
        assert left == ids1 - ids2, (left, ids1 - ids2)
        assert d2["summary"]["new_today"] == len(new)
        assert d2["summary"]["left_since_last_run"] == len(left)
        kept = [a for a in d2["animals"] if a["id"] in ids1]
        assert all(a["first_seen"] == "2026-10-06" for a in kept)

        # Day 30 with the same listing: old departures age out after 14 days.
        run(proj, "--sample", "tests/sample_day2.json", "--today", "2026-11-05")
        d3 = json.loads(data.read_text())
        assert d3["recently_left"] == [] and d3["summary"]["new_today"] == 0

        # A failed run (empty response) leaves the previous file alone.
        before = data.read_text()
        (proj / "tests/empty.json").write_text('{"bay-area": {"dogs": [], "cats": []}}')
        run(proj, "--sample", "tests/empty.json", "--today", "2026-11-06", ok=False)
        assert data.read_text() == before

        # Rescues included when switched on.
        cfg = json.loads((proj / "config.json").read_text())
        cfg["include_rescues"] = True
        (proj / "config.json").write_text(json.dumps(cfg))
        run(proj, "--sample", "tests/sample_day2.json", "--today", "2026-11-07")
        d4 = json.loads(data.read_text())
        assert "Sample Rescue Group" in {a["org"]["name"] for a in d4["animals"]}

        idx = json.loads((proj / "docs/data/areas.json").read_text())
        assert idx["areas"][0]["id"] == "bay-area"

    print(f"All checks passed. Day 1: {len(ids1)} shelter animals. "
          f"Day 2: {len(new)} new, {len(left)} likely adopted.")


if __name__ == "__main__":
    main()
