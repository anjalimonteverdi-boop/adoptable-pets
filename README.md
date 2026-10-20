# Adoptable Dogs & Cats

A free public web page of every adoptable dog and cat in shelters near you,
updated automatically every morning.

- Data comes from [RescueGroups.org](https://rescuegroups.org) once you have a
  free API key (Petfinder shut down its public API in December 2025).
- **No key yet? It still works.** Without a key it reads the adoptable dogs
  and cats straight from the websites of three Bay Area shelters: Berkeley
  Humane, Humane Society Silicon Valley and Pets In Need. See
  "Without a RescueGroups key" below.
- A small script runs daily on GitHub Actions at about 6am Pacific.
- The page is hosted free on GitHub Pages. Share the link with anyone.

## What the page does

- Shows every adoptable dog and cat from shelters within 50 miles of San Francisco.
- Filters for dogs/cats, age, sex, size and shelter, plus a search box.
- Sorts by newest or closest.
- "New today" badges on animals that appeared since the last update.
- A "Recently left, likely adopted" list for the last 14 days.
- Any filtered view has its own link (the **Copy link** button).
- Works on phones.
- Every animal links to its listing on the shelter's own site, which has the
  official status. Photos load from the shelter, nothing is copied.

## Setup (about 20 minutes, no coding)

### 1. Request a RescueGroups API key (do this first)

Fill in the request form at <https://manage.rescuegroups.org/public_api_signup>
(linked from <https://rescuegroups.org/services/adoptable-pet-data-api/>) to
request a free API key. Say it's for a free, non-commercial public page listing adoptable
shelter animals in your area. They review requests by hand, so it can take a
few days. Keep the key private.

### 2. Make a GitHub account and a repository

1. Sign up at <https://github.com/signup> (free).
2. Click **+** (top right) > **New repository**.
3. Name it something like `adoptable-pets`. Choose **Public** (free GitHub
   Pages needs a public repository). Click **Create repository**.

### 3. Upload the files

1. On the new repository's page, click **uploading an existing file**.
2. Drag in `config.json`, `README.md`, and the `docs`, `scripts` and `tests`
   folders. Click **Commit changes**.
3. The workflow file lives in a hidden folder, which drag-and-drop often skips,
   so add it by hand: click **Add file > Create new file**, type the name
   `.github/workflows/daily.yml` (the slashes create the folders), paste in the
   contents of `.github/workflows/daily.yml` from this project, and click
   **Commit changes**.

### 4. Add your API key (skip this until the key arrives)

**Settings > Secrets and variables > Actions > New repository secret.**
Name: `RESCUEGROUPS_API_KEY`. Secret: paste your key. Click **Add secret**.

Without a key, the page uses the shelter websites instead, so you can do
steps 5 and 6 now and add the key whenever it comes. The next run after you
add it switches to RescueGroups by itself.

### 5. Turn on the website

**Settings > Pages.** Under "Build and deployment", set Source to
**Deploy from a branch**, Branch to **main** and folder to **/docs**. Click
**Save**. The page address appears at the top of that screen after a minute,
something like `https://yourname.github.io/adoptable-pets/`.

### 6. Run it the first time

**Actions** tab > **Daily shelter update** > **Run workflow** > **Run workflow**.
When it shows a green check (a minute or two), open your page address. After
that it runs by itself every morning.

On the first day there are no "New today" badges yet, since there is nothing
to compare against. They start on day two.

## Changing things

Everything is in `config.json`. Edit it on GitHub by opening the file and
clicking the pencil icon.

| Setting | What it does |
|---|---|
| `site_title` | The heading on the page. |
| `areas` | Each area is a ZIP code and a radius in miles. |
| `species` | `["dogs", "cats"]`. Remove one to show only the other. |
| `include_rescues` | `false` shows shelters only. `true` also shows rescue groups (many foster-based rescues list on RescueGroups, so this adds a lot of animals). |
| `keep_adopted_days` | How long animals stay in the "Recently left" list. |

To add another area anywhere in the US, add an entry to `areas`. An area
picker appears on the page once there's more than one:

```json
"areas": [
  {"id": "bay-area", "name": "San Francisco Bay Area", "postal_code": "94103", "miles": 50},
  {"id": "austin",   "name": "Austin",                 "postal_code": "78701", "miles": 40}
]
```

The `id` must be lowercase letters, numbers and dashes. Keep each radius
reasonable (under about 100 miles) so each update stays quick.

## Without a RescueGroups key

Some shelters publish their adoptable animals as a public data feed on their
own website. Without a key, the daily update reads these:

| Shelter | Where |
|---|---|
| Berkeley Humane | Berkeley |
| Humane Society Silicon Valley | Milpitas |
| Pets In Need | Palo Alto |

These were picked because their feeds are public and their `robots.txt`
files allow it. The update reads each one once a day and waits between
requests. Other big shelters (SF SPCA, SF Animal Care & Control, Oakland
Animal Services, Marin Humane, Peninsula Humane, East Bay SPCA) don't publish
a feed like this, or block automated access, so they only appear with a
RescueGroups key.

What's different in this mode:
- Only these three shelters appear, not every shelter in the area.
- The websites don't share sex, size or breed, so those filters are hidden.
  Age only says "Baby" for puppies and kittens.
- If one shelter's website is down, its animals from the last good run stay
  up, and the others update as usual.
- When a shelter redesigns its website the feed can change or disappear. If
  a shelter's animals stop updating, the Actions run log says which one
  failed.

The shelters are listed under `shelter_sites` in `config.json`. To stop
using one, delete its entry.

## Good to know

- **With a key, only shelters that publish to RescueGroups appear.** After the first run,
  open the shelter menu on the page and check that the shelters you care
  about are there. If one is missing, it may only list on its own site or on
  Petfinder, and you can ask it to start sharing to RescueGroups too.
- **"Likely adopted" is a guess.** An animal that disappears from the listings
  was usually adopted, but it could also have been moved to a foster home,
  transferred or put on hold.
- **If an update fails**, the previous day's listings stay up. GitHub emails
  you when a run fails. Common causes: the API key secret is missing or
  mistyped, or RescueGroups was down (it will try again the next morning).
- **"Permission denied" when saving the update:** go to **Settings > Actions >
  General > Workflow permissions**, choose **Read and write permissions**, and
  save.
- **GitHub pauses scheduled runs** in repositories with no activity for 60
  days. The daily update commits keep it active, but if it ever stops, the
  Actions tab will show a button to turn it back on.

## Files

| File | Purpose |
|---|---|
| `config.json` | Area, radius, species and options. |
| `scripts/update.py` | Downloads today's listings and writes `docs/data/`. Standard-library Python, nothing to install. |
| `scripts/shelter_sites.py` | Reads shelter websites when there's no RescueGroups key. |
| `docs/index.html` | The public page. |
| `docs/data/` | Filled in by the daily run. `<area>.json` is what the page reads; `<area>.state.json` remembers first-seen dates. |
| `.github/workflows/daily.yml` | The daily schedule. |
| `tests/` | Offline test with made-up data: `python tests/test_update.py`. |
