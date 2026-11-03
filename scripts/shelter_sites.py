"""Read adoptable dogs and cats straight from shelters' own websites.

This is the no-key backup for when there is no RescueGroups API key. It only
uses shelters whose websites publish their listings as public WordPress JSON
(the /wp-json/ feed every WordPress site has) and whose robots.txt allows it.
It makes one request per page of 100 animals, once a day, and waits between
requests to the same site.

Each shelter is one entry under "shelter_sites" in config.json:

  {
    "id": "berkeley-humane",                 # short name, letters and dashes
    "name": "Berkeley Humane",               # shown on the page
    "city": "Berkeley",
    "lat": 37.8597, "lon": -122.2918,       # used for "closest first"
    "feed": "https://berkeleyhumane.org/wp-json/wp/v2/adoptable_pets",
    "params": {"pet_status": "128"},         # extra filters for the feed
    "species_classes": {                     # how the site tags dogs and cats
      "Dog": ["pet_species-dog"],
      "Cat": ["pet_species-cat"]
    },
    "baby_classes": ["type-puppy"],          # optional: tags meaning puppy/kitten
    "delay_seconds": 2                       # wait between requests
  }
"""

import html
import json
import math
import re
import time
import urllib.parse
import urllib.request

PER_PAGE = 100
MAX_PAGES = 20
USER_AGENT = ("AdoptablePetsPage/1.0 (free non-commercial page of adoptable "
              "shelter animals; runs once a day)")
FIELDS = "id,date,link,title,class_list,yoast_head_json,featured_media"


def get_json(url, attempts=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/json"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                total_pages = resp.headers.get("X-WP-TotalPages")
                return json.load(resp), int(total_pages) if total_pages else None
        except Exception:
            if attempt == attempts:
                raise
            time.sleep(10 * attempt)


def fetch_site(site):
    """Return the raw list of posts from one shelter's feed."""
    items = []
    page = 1
    while page <= MAX_PAGES:
        params = {"per_page": PER_PAGE, "page": page, "_fields": FIELDS}
        params.update(site.get("params", {}))
        url = site["feed"] + "?" + urllib.parse.urlencode(params)
        batch, total_pages = get_json(url)
        items += batch
        if len(batch) < PER_PAGE or (total_pages and page >= total_pages):
            break
        page += 1
        time.sleep(site.get("delay_seconds", 2))
    add_missing_photos(site, items)
    return items


def add_missing_photos(site, items):
    """Some posts have a photo but no social-preview image; look those up."""
    need = {it["featured_media"]: it for it in items
            if not photo_of(it) and it.get("featured_media")}
    if not need:
        return
    media_url = site["feed"].split("/wp-json/")[0] + "/wp-json/wp/v2/media"
    ids = list(need)
    for i in range(0, len(ids), PER_PAGE):
        time.sleep(site.get("delay_seconds", 2))
        chunk = ids[i:i + PER_PAGE]
        params = {"include": ",".join(map(str, chunk)), "per_page": PER_PAGE,
                  "_fields": "id,source_url"}
        try:
            media, _ = get_json(media_url + "?" + urllib.parse.urlencode(params))
        except Exception:
            return  # photos are nice to have; never fail the run over them
        for m in media:
            if m.get("id") in need and m.get("source_url"):
                need[m["id"]]["photo_url"] = m["source_url"]


def url_works(url, site):
    """True if the photo URL actually serves an image (some social-preview images
    point at files the shelter later removed)."""
    time.sleep(site.get("delay_seconds", 2))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 206) and resp.headers.get_content_type().startswith("image/")
    except Exception:
        return False


_pages = {}  # pages already read during this run, so photos and facts share one request


def fetch_page(url, site):
    if url not in _pages:
        time.sleep(site.get("delay_seconds", 2))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=60) as resp:
                _pages[url] = resp.read().decode("utf-8", "replace")
        except Exception:
            _pages[url] = None
    return _pages[url]


PAGE_IMAGE = re.compile(r"""https://[^"'\s>]+/wp-content/uploads/[^"'\s>]+?\.(?:jpe?g|png|webp)(?:\?[^"'\s>]*)?""", re.I)


NOT_A_PET = re.compile(r"logo|icon|tiktok|facebook|instagram|twitter|youtube|badge|sprite|round|banner", re.I)


def page_photos(url, site):
    """Photos shown on the animal's own page, in page order.

    Social-preview tags are skipped (some shelters leave them pointing at photos
    they've since replaced), and so are logos and icons. If the site config has
    "photo_name_pattern", only file names matching it count.
    """
    page = fetch_page(url, site)
    if not page:
        return []
    page = re.sub(r"<meta[^>]*>", "", html.unescape(page))
    pattern = site.get("photo_name_pattern")
    found, names = [], set()
    for m in PAGE_IMAGE.finditer(page):
        cand = m.group(0)
        name = cand.split("?")[0].rsplit("/", 1)[-1]
        if name in names or NOT_A_PET.search(name) or (pattern and not re.fullmatch(pattern, name)):
            continue
        names.add(name)
        found.append(cand)
    return found


PHOTO_CHECK = 3  # bump to re-check every photo on the next run


def check_photos(site, animals, previous):
    """Make sure each animal's photo is one that still loads.

    For shelters marked "photo_from_page", the first photo on the animal's own
    page is used every day (their listing photos go stale when they swap
    pictures). Otherwise each new photo is checked once, and replaced from the
    animal's page only if it doesn't load.
    """
    seen = {an["id"]: an for an in previous if an.get("photo_checked") == PHOTO_CHECK}
    fixed = 0
    for an in animals:
        source = an["photo"]
        if site.get("photo_from_page") and an.get("url"):
            photos = page_photos(an["url"], site)
            if photos:
                if photos[0] != source:
                    fixed += 1
                an["photo"] = photos[0]
            an["photo_source"], an["photo_checked"] = source, PHOTO_CHECK
            continue
        before = seen.get(an["id"])
        if before and before.get("photo_source") == source:
            an["photo"] = before["photo"]
            an["photo_source"], an["photo_checked"] = source, PHOTO_CHECK
            continue
        if not source or not url_works(source, site):
            base = source.split("?")[0].rsplit("/", 1)[-1] if source else None
            for cand in (page_photos(an["url"], site) if an.get("url") else [])[:3]:
                if cand.split("?")[0].rsplit("/", 1)[-1] != base and url_works(cand, site):
                    an["photo"] = cand
                    fixed += 1
                    break
        an["photo_source"], an["photo_checked"] = source, PHOTO_CHECK
    return fixed


FACTS_CHECK = 1  # bump to re-read every animal's age and sex on the next run
UNIT = r"(?:years?|yrs?|months?|mos?|weeks?|wks?)"
AGE_RE = re.compile(r"\bAge\b\W{0,6}((?:\d+(?:\.\d+)?\s*" + UNIT + r"\b[\s,&and]*){1,3})", re.I)
SEX_RE = re.compile(r"\b(?:Sex|Gender)\b\W{0,6}(Male|Female)\b", re.I)


def age_months(text):
    """'2 Years 3 Months' -> 27, '8Wks' -> 2. None if there's no number with a unit."""
    total, found = 0.0, False
    for num, unit in re.findall(r"(\d+(?:\.\d+)?)\s*(" + UNIT + r")\b", text, re.I):
        found = True
        u = unit.lower()
        total += float(num) * (12 if u.startswith("y") else 1 if u.startswith("m") else 12 / 52)
    return round(total, 1) if found else None


def age_group(months, species):
    """The age groups shown in the filter."""
    if months < 12:
        return "Baby"
    if months < 36:
        return "Young"
    if months < 96:
        return "Adult"
    return "Senior"


def nice_age(months):
    if months < 2:
        return f"{max(1, round(months * 52 / 12))} weeks"
    if months < 12:
        return f"{round(months)} months"
    years = int(months // 12)
    return f"{years} year" + ("s" if years != 1 else "")


def page_facts(page):
    """Age and sex as written on an animal's page."""
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page))))
    facts = {}
    m = AGE_RE.search(text)
    months = age_months(m.group(1)) if m else None
    if months is not None and months < 360:
        facts["age_months"] = months
    m = SEX_RE.search(text)
    if m:
        facts["sex"] = m.group(1).capitalize()
    return facts


def add_facts(site, animals, previous):
    """Fill in age group, exact age and sex from each animal's own page.

    The feeds don't carry them. Each animal's page is read once and the answer kept,
    so later runs only read pages for new animals. Returns how many pages were read.
    """
    seen = {an["id"]: an for an in previous if an.get("facts_checked") == FACTS_CHECK}
    read = 0
    for an in animals:
        before = seen.get(an["id"])
        if before:
            facts = {k: before[k] for k in ("age_months", "sex") if before.get(k) not in (None, "")}
        else:
            page = fetch_page(an["url"], site) if an.get("url") else None
            read += 1
            facts = page_facts(page) if page else {}
        if "age_months" in facts:
            an["age_months"] = facts["age_months"]
            an["age"] = age_group(facts["age_months"], an["species"])
            an["age_text"] = nice_age(facts["age_months"])
        if facts.get("sex"):
            an["sex"] = facts["sex"]
        an["facts_checked"] = FACTS_CHECK
    _pages.clear()
    return read


def miles_between(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def photo_of(item):
    if item.get("photo_url"):
        return item["photo_url"]
    images = (item.get("yoast_head_json") or {}).get("og_image") or []
    for img in images:
        if isinstance(img, dict) and img.get("url"):
            return img["url"]
    return None


def parse_site(site, items, area):
    """Turn one shelter's posts into the same records RescueGroups produces."""
    distance = None
    if all(k in area for k in ("lat", "lon")) and all(k in site for k in ("lat", "lon")):
        distance = round(miles_between(area["lat"], area["lon"], site["lat"], site["lon"]), 1)

    animals = []
    for item in items:
        classes = set(item.get("class_list") or [])
        species = next((sp for sp, tags in site["species_classes"].items()
                        if classes & set(tags)), None)
        if species not in ("Dog", "Cat"):
            continue
        title = (item.get("title") or {}).get("rendered") or "Unnamed"
        is_baby = bool(classes & set(site.get("baby_classes", [])))
        animals.append({
            "id": f"{site['id']}-{item['id']}",
            "name": html.unescape(title).strip(),
            "species": species,
            "breed": "",
            "age": "Baby" if is_baby else "",
            "sex": "",
            "size": "",
            "photo": photo_of(item),
            "url": item.get("link") or "",
            "distance": distance,
            "org": {
                "id": site["id"],
                "name": site["name"],
                "type": "Shelter",
                "city": site.get("city", ""),
                "state": site.get("state", "CA"),
                "url": site["feed"].split("/wp-json/")[0],
                "lat": site.get("lat"),
                "lon": site.get("lon"),
            },
        })
    return animals
