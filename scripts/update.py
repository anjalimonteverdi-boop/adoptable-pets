#!/usr/bin/env python3
"""Daily update: fetch adoptable dogs and cats and write the JSON files the
public page reads.

Where the animals come from:
  - With a RESCUEGROUPS_API_KEY: RescueGroups.org, every shelter in the area.
  - Without one: the shelters listed under "shelter_sites" in config.json,
    read from their own websites (see scripts/shelter_sites.py).

Usage:
  RESCUEGROUPS_API_KEY=... python scripts/update.py
  python scripts/update.py                                  # no key: shelter websites
  python scripts/update.py --sample tests/sample_day1.json  # offline test
  python scripts/update.py --today 2026-10-06               # override the date (testing)

Only standard-library Python is used, so nothing needs installing.
Nothing in docs/data is touched unless every area downloads successfully,
so a failed run leaves yesterday's listings in place.
"""

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import shelter_sites

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
DATA_DIR = ROOT / "docs" / "data"

API_BASE = "https://api.rescuegroups.org/v5/public/animals/search/available"
PAGE_LIMIT = 250          # RescueGroups maximum per page
MAX_PAGES = 40            # safety stop: 10,000 animals per species per area
SPECIES_LABEL = {"dogs": "Dog", "cats": "Cat"}


# --------------------------------------------------------------------------
# Download
# --------------------------------------------------------------------------

def api_post(url, body, api_key, attempts=3):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/vnd.api+json",
            "Authorization": api_key,
            "User-Agent": "shelter-agent (github actions)",
        },
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                sys.exit("RescueGroups rejected the API key (HTTP %d). Check the "
                         "RESCUEGROUPS_API_KEY secret." % e.code)
            if attempt == attempts:
                raise
        except urllib.error.URLError:
            if attempt == attempts:
                raise
        time.sleep(5 * attempt)


def fetch_species(area, species, api_key):
    """Yield raw API pages for one species in one area."""
    body = {
        "data": {
            "filterRadius": {"postalcode": area["postal_code"], "miles": area["miles"]},
        }
    }
    page = 1
    while page <= MAX_PAGES:
        url = (f"{API_BASE}/{species}/?limit={PAGE_LIMIT}&page={page}"
               "&include=orgs,pictures")
        result = api_post(url, body, api_key)
        yield result
        pages = (result.get("meta") or {}).get("pages") or 1
        if page >= pages:
            break
        page += 1


# --------------------------------------------------------------------------
# Parse
# --------------------------------------------------------------------------

def picture_url(pic_attrs):
    for size in ("large", "original", "small"):
        v = pic_attrs.get(size)
        if isinstance(v, dict) and v.get("url"):
            return v["url"]
        if isinstance(v, str) and v:
            return v
    return None


def is_shelter(org_type):
    return (org_type or "").strip().lower().startswith("shelter")


def parse_pages(pages, species, include_rescues):
    """Turn raw API pages into a list of simple animal records."""
    animals = []
    for result in pages:
        included = result.get("included") or []
        orgs = {i["id"]: i.get("attributes") or {} for i in included if i.get("type") == "orgs"}
        pics = {i["id"]: i.get("attributes") or {} for i in included if i.get("type") == "pictures"}

        for item in result.get("data") or []:
            a = item.get("attributes") or {}
            rel = item.get("relationships") or {}

            org_ids = [o["id"] for o in ((rel.get("orgs") or {}).get("data") or [])]
            org = orgs.get(org_ids[0], {}) if org_ids else {}
            if not include_rescues and not is_shelter(org.get("type")):
                continue

            photo = None
            pic_refs = (rel.get("pictures") or {}).get("data") or []
            pic_list = sorted(
                (pics[p["id"]] for p in pic_refs if p["id"] in pics),
                key=lambda p: p.get("order") or 0,
            )
            if pic_list:
                photo = picture_url(pic_list[0])
            photo = photo or a.get("pictureThumbnailUrl")

            animals.append({
                "id": str(item.get("id")),
                "name": (a.get("name") or "Unnamed").strip(),
                "species": SPECIES_LABEL[species],
                "breed": a.get("breedString") or a.get("breedPrimary") or "",
                "age": a.get("ageGroup") or "",
                "sex": a.get("sex") or "",
                "size": a.get("sizeGroup") or "",
                "photo": photo,
                "url": a.get("url") or org.get("url") or "",
                "distance": a.get("distance"),
                "org": {
                    "id": org_ids[0] if org_ids else "",
                    "name": org.get("name") or "Unknown shelter",
                    "type": org.get("type") or "",
                    "city": org.get("city") or "",
                    "state": org.get("state") or "",
                    "url": org.get("url") or "",
                },
            })
    return animals


# --------------------------------------------------------------------------
# Track new and likely-adopted animals
# --------------------------------------------------------------------------

def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def merge_with_history(area_id, animals, today, keep_days, source):
    """Add first_seen dates, and work out who left since the last run."""
    state_path = DATA_DIR / f"{area_id}.state.json"
    state = load_json(state_path, {"first_seen": {}, "last_listing": {}, "gone": []})
    if state.get("source", source) != source:
        # Switched data source (e.g. the RescueGroups key arrived): the animal
        # IDs all change, so start the history over instead of calling every
        # animal adopted.
        state = {"first_seen": {}, "last_listing": {}, "gone": []}
    first_seen = state.get("first_seen", {})
    previous = state.get("last_listing", {})

    current_ids = set()
    for an in animals:
        current_ids.add(an["id"])
        an["first_seen"] = first_seen.setdefault(an["id"], today)
        an["new"] = an["first_seen"] == today and bool(previous)

    # Animals listed last run but not today: probably adopted.
    gone = [g for g in state.get("gone", []) if g["id"] not in current_ids]
    gone_today = []
    for aid, summary in previous.items():
        if aid not in current_ids:
            rec = dict(summary, id=aid, left_on=today)
            gone_today.append(rec)
    gone = gone_today + [g for g in gone if g["id"] not in {r["id"] for r in gone_today}]
    cutoff = (dt.date.fromisoformat(today) - dt.timedelta(days=keep_days)).isoformat()
    gone = [g for g in gone if g["left_on"] >= cutoff]

    # Forget first_seen for animals gone longer than the window, keep file small.
    keep_ids = current_ids | {g["id"] for g in gone}
    first_seen = {k: v for k, v in first_seen.items() if k in keep_ids}

    new_state = {
        "source": source,
        "first_seen": first_seen,
        "last_listing": {
            an["id"]: {k: an[k] for k in ("name", "species", "breed", "photo", "url")}
                       | {"org": an["org"]["name"]}
            for an in animals
        },
        "gone": gone,
    }
    summary = {
        "new_today": sum(1 for an in animals if an["new"]),
        "left_since_last_run": len(gone_today),
        "first_run": not previous,
    }
    return animals, gone, new_state, summary


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def fetch_from_sites(area, sites, config, sample=None):
    """Read every configured shelter website for this area.

    If one site fails, keep that shelter's animals from the last good run so a
    hiccup on one website doesn't mark all its animals as adopted.
    """
    wanted = {SPECIES_LABEL[s] for s in config.get("species", ["dogs", "cats"])}
    previous = load_json(DATA_DIR / f"{area['id']}.json", {}).get("animals", [])
    animals, failed = [], []
    for site in sites:
        if site.get("area", area["id"]) != area["id"]:
            continue
        try:
            if sample is not None:
                items = sample["sites"].get(site["id"])
                if items == "error":
                    raise RuntimeError("simulated failure")
            else:
                items = shelter_sites.fetch_site(site)
            found = shelter_sites.parse_site(site, items or [], area)
            if not found:
                raise RuntimeError("no dogs or cats found")
            animals += found
            print(f"  {site['name']}: {len(found)} dogs and cats")
        except Exception as e:  # keep going with the other shelters
            failed.append(site["name"])
            kept = [an for an in previous if an["org"]["id"] == site["id"]]
            for an in kept:
                for k in ("first_seen", "new"):
                    an.pop(k, None)
            animals += kept
            print(f"  {site['name']}: FAILED ({e}); kept {len(kept)} from last run",
                  file=sys.stderr)
    if failed and len(failed) == len(sites):
        sys.exit("Every shelter website failed. Leaving yesterday's listings up.")
    return [an for an in animals if an["species"] in wanted]


def write_json(path, obj):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, ensure_ascii=False))
    tmp.replace(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", help="read a saved API response instead of calling the API")
    ap.add_argument("--today", help="override today's date (YYYY-MM-DD), for testing")
    args = ap.parse_args()

    config = json.loads(CONFIG_PATH.read_text())
    today = args.today or dt.datetime.now(dt.timezone.utc).astimezone(
        dt.timezone(dt.timedelta(hours=-8))).date().isoformat()

    api_key = os.environ.get("RESCUEGROUPS_API_KEY", "").strip()
    sample = json.loads(Path(args.sample).read_text()) if args.sample else None
    use_rescuegroups = bool(api_key) if sample is None else "sites" not in sample
    sites = config.get("shelter_sites", [])
    if not use_rescuegroups and not sites:
        sys.exit("No RESCUEGROUPS_API_KEY and no shelter_sites in config.json, so "
                 "there is nowhere to get animals from.")

    # Download everything first; only write files once all of it succeeded.
    results = []
    for area in config["areas"]:
        if use_rescuegroups:
            source = "RescueGroups.org"
            animals = []
            for species in config.get("species", ["dogs", "cats"]):
                if sample is not None:
                    pages = sample.get(area["id"], {}).get(species, [])
                else:
                    pages = list(fetch_species(area, species, api_key))
                animals += parse_pages(pages, species, config.get("include_rescues", False))
        else:
            source = "shelter websites"
            animals = fetch_from_sites(area, sites, config, sample)

        # The same animal can come back twice across pages; keep one.
        animals = list({an["id"]: an for an in animals}.values())
        if not animals:
            sys.exit(f"No animals came back for {area['name']}. Leaving yesterday's "
                     "listings up. Check config.json.")
        results.append((area, animals, source))

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    area_index = []
    for area, animals, source in results:
        animals, gone, state, summary = merge_with_history(
            area["id"], animals, today, config.get("keep_adopted_days", 14), source)
        animals.sort(key=lambda an: (an["first_seen"], an["name"]), reverse=True)
        write_json(DATA_DIR / f"{area['id']}.json", {
            "area": area,
            "updated": today,
            "generated_at": generated_at,
            "source": source,
            "summary": summary,
            "animals": animals,
            "recently_left": gone,
        })
        write_json(DATA_DIR / f"{area['id']}.state.json", state)
        area_index.append({"id": area["id"], "name": area["name"], "count": len(animals)})
        print(f"{area['name']}: {len(animals)} animals, {summary['new_today']} new, "
              f"{summary['left_since_last_run']} left since last run")

    write_json(DATA_DIR / "areas.json", {
        "site_title": config.get("site_title", "Adoptable Dogs & Cats"),
        "updated": today,
        "areas": area_index,
    })


if __name__ == "__main__":
    main()
