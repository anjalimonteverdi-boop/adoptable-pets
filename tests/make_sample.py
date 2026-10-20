#!/usr/bin/env python3
"""Build made-up RescueGroups API responses for offline testing.

Writes tests/sample_day1.json and tests/sample_day2.json. Day 2 drops a few
animals (to test "likely adopted") and adds a few (to test "new today").
The shape follows the RescueGroups v5 JSON:API format: data[] animals with
relationships to orgs and pictures, plus included[] orgs and pictures.
"""

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
random.seed(7)

ORGS = [
    ("101", "Sample City Animal Shelter", "Shelter", "San Francisco"),
    ("102", "Sample Humane Society", "Shelter", "Oakland"),
    ("103", "Sample County Animal Services", "Shelter", "San Rafael"),
    ("201", "Sample Rescue Group", "Rescue", "Berkeley"),   # excluded by default
]
DOG_NAMES = ["Biscuit", "Luna", "Max", "Pepper", "Rocky", "Daisy", "Bear", "Olive",
             "Tank", "Hazel", "Ziggy", "Maple", "Copper", "Juniper", "Duke", "Nala"]
CAT_NAMES = ["Mochi", "Whiskers", "Cleo", "Tofu", "Salem", "Pumpkin", "Ash", "Kiwi",
             "Miso", "Shadow", "Ginger", "Bean"]
DOG_BREEDS = ["Labrador Retriever Mix", "Pit Bull Terrier", "Chihuahua", "German Shepherd",
              "Australian Cattle Dog Mix", "Husky"]
CAT_BREEDS = ["Domestic Short Hair", "Domestic Medium Hair", "Siamese Mix", "Tabby"]


def animal(aid, name, species):
    org = random.choice(ORGS)
    pic_id = f"p{aid}"
    return {
        "type": "animals",
        "id": aid,
        "attributes": {
            "name": name,
            "ageGroup": random.choice(["Baby", "Young", "Adult", "Senior"]),
            "sex": random.choice(["Male", "Female"]),
            "sizeGroup": random.choice(["Small", "Medium", "Large"]),
            "breedString": random.choice(DOG_BREEDS if species == "dogs" else CAT_BREEDS),
            "pictureThumbnailUrl": f"https://placehold.co/100x100?text={name}",
            "url": f"https://example.org/animals/{aid}",
            "distance": round(random.uniform(0.5, 49.5), 1),
        },
        "relationships": {
            "orgs": {"data": [{"type": "orgs", "id": org[0]}]},
            "pictures": {"data": [{"type": "pictures", "id": pic_id}]},
        },
    }, org, {
        "type": "pictures", "id": pic_id,
        "attributes": {"order": 1,
                       "large": {"url": f"https://placehold.co/500x500?text={name}"},
                       "small": {"url": f"https://placehold.co/100x100?text={name}"}},
    }


def pages_for(items, per_page):
    pages = []
    chunks = [items[i:i + per_page] for i in range(0, len(items), per_page)] or [[]]
    for n, chunk in enumerate(chunks, 1):
        data, included, seen = [], [], set()
        for a, org, pic in chunk:
            data.append(a)
            if org[0] not in seen:
                seen.add(org[0])
                included.append({"type": "orgs", "id": org[0], "attributes": {
                    "name": org[1], "type": org[2], "city": org[3], "state": "CA",
                    "url": f"https://example.org/org/{org[0]}"}})
            included.append(pic)
        pages.append({"meta": {"count": len(items), "pages": len(chunks), "pageReturned": n},
                      "data": data, "included": included})
    return pages


dogs = [animal(f"d{i}", n, "dogs") for i, n in enumerate(DOG_NAMES)]
cats = [animal(f"c{i}", n, "cats") for i, n in enumerate(CAT_NAMES)]

day1 = {"bay-area": {"dogs": pages_for(dogs[:13], 5), "cats": pages_for(cats[:10], 5)}}
# Day 2: d0, d1, c0 leave; d13-d15 and c10-c11 arrive.
day2 = {"bay-area": {"dogs": pages_for(dogs[2:], 5), "cats": pages_for(cats[1:], 5)}}

(HERE / "sample_day1.json").write_text(json.dumps(day1, indent=1))
(HERE / "sample_day2.json").write_text(json.dumps(day2, indent=1))
print("wrote sample_day1.json and sample_day2.json")


# ---- Shelter-website samples (the no-key backup) --------------------------
# Same shape as the real WordPress feeds checked on 2026-10-20.

def wp_item(pid, name, classes, site):
    return {"id": pid, "date": "2026-10-20T10:14:10",
            "link": f"https://example.org/{site}/{pid}",
            "title": {"rendered": name},
            "class_list": [f"post-{pid}", "status-publish", "hentry", *classes],
            "yoast_head_json": {"title": name,
                                "og_image": [{"url": f"https://placehold.co/500x500?text={pid}"}]}}


bh = [wp_item(1, "Ahi", ["pet_species-cat", "pet_status-available"], "bh"),
      wp_item(2, "Cody &#038; Chloe", ["pet_species-dog", "pet_status-available"], "bh"),
      wp_item(3, "Thimble", ["pet_species-cat", "pet_status-available"], "bh")]
hssv = [wp_item(10, "Spring Roll", ["type-kitten", "breed-domestic-short-hair"], "hssv"),
        wp_item(11, "Pierre", ["type-dog"], "hssv"),
        wp_item(12, "Thumper", ["type-rabbit"], "hssv")]          # not a dog or cat
pin = [wp_item(20, "Bonita", ["category-dogs", "dog-dogs", "dog-puppies", "cats-palo-alto"], "pin"),
       wp_item(21, "Pancho", ["category-cats", "cats-palo-alto"], "pin")]

sites1 = {"sites": {"berkeley-humane": bh, "hssv": hssv, "pets-in-need": pin}}
# Day 2: Ahi adopted, new dog at HSSV, Pets In Need's website is down.
sites2 = {"sites": {"berkeley-humane": bh[1:], "hssv": hssv + [wp_item(13, "Mango", ["type-puppy"], "hssv")],
                    "pets-in-need": "error"}}
(HERE / "sample_sites_day1.json").write_text(json.dumps(sites1, indent=1))
(HERE / "sample_sites_day2.json").write_text(json.dumps(sites2, indent=1))
print("wrote sample_sites_day1.json and sample_sites_day2.json")
