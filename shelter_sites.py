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
import time
import urllib.parse
import urllib.request

PER_PAGE = 100
MAX_PAGES = 20
USER_AGENT = ("AdoptablePetsPage/1.0 (free non-commercial page of adoptable "
              "shelter animals; runs once a day)")
FIELDS = "id,date,link,title,class_list,yoast_head_json"


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
    return items


def miles_between(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def photo_of(item):
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
            },
        })
    return animals
