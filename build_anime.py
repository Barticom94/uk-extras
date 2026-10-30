"""Anime by genre and by decade: MyAnimeList's own genres, themes and demographics (via Tenrai), most members first.

python -I build_anime.py [out_dir] [cache_dir]   writes out_dir/anime/ (default public/, committed). cache_dir, never
inside the repo, keeps the downloads and reuses them next time, for working on the build without crawling again.

out_dir/anime/index.json lists the genres (A to Z, the picker's order), the decades and "all", each with its slug,
count and pages; out_dir/anime/<slug>/<n>.json holds items 50n to 50n+49 of that list as {"metas": [...]}.

One pass over Tenrai's SFW anime with 1,000+ MAL members, one request a second (half its public limit; tenrai.org/terms
allows caching and transforming for private use). Ids come from Fribb's anime-lists: the IMDb id with the right type
where there is one, else kitsu:<id>, else mal:<id>. Seasons that share an IMDb id are one tile, which keeps the best
ranked season's name, poster and year. Only these tiles and the lists are written: no scores, members or synopses.
"""
import collections
import datetime as dt
import http.client
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
TENRAI = "https://api.tenrai.org/v1/anime?sfw=true&min_members=1000&order_by=members&sort=desc&limit=100&page={page}"
FRIBB = "https://raw.githubusercontent.com/Fribb/anime-lists/master/anime-list-full.json"
PAGE = 50
# MAL's 18 genres, its themes and demographics, A to Z as AIOMetadata sorts its MAL genre picker. The public picker
# leaves Ecchi out (its titles are SFW here, but the household keeps the word out of public screens).
GENRES = [
    "Action", "Adult Cast", "Adventure", "Anthropomorphic", "Avant Garde", "Award Winning", "Boys Love", "CGDCT",
    "Childcare", "Combat Sports", "Comedy", "Crossdressing", "Delinquents", "Detective", "Drama", "Ecchi", "Educational",
    "Fantasy", "Gag Humor", "Girls Love", "Gore", "Gourmet", "Harem", "High Stakes Game", "Historical", "Horror",
    "Idols (Female)", "Idols (Male)", "Isekai", "Iyashikei", "Josei", "Kids", "Love Polygon", "Love Status Quo",
    "Magical Sex Shift", "Mahou Shoujo", "Martial Arts", "Mecha", "Medical", "Military", "Music", "Mystery", "Mythology",
    "Organized Crime", "Otaku Culture", "Parody", "Performing Arts", "Pets", "Psychological", "Racing", "Reincarnation",
    "Reverse Harem", "Romance", "Samurai", "School", "Sci-Fi", "Seinen", "Shoujo", "Shounen", "Showbiz", "Slice of Life",
    "Space", "Sports", "Strategy Game", "Super Power", "Supernatural", "Survival", "Suspense", "Team Sports",
    "Time Travel", "Urban Fantasy", "Vampire", "Video Game", "Villainess", "Visual Arts", "Workplace",
]
DECADES = [f"{d}s" for d in range(1960, 2030, 10)]  # before 1960 too little has 1,000+ members
ADULT_GENRE_IDS = {12, 49}  # MAL's two adult genres: Tenrai's SFW filter drops them; so does this, to be sure
SKIP_TYPES = {"Music", "CM", "PV"}  # clips and adverts, not shows
# Words the household keeps out of public text (validate.py here, check.py in the collections repo). A few SFW titles
# have one in their name (xxxHOLiC): those are left out.
PUBLIC_WORDS = re.compile(r"hentai|erotic|ecchi|xxx|porn|nsfw|naughty|playboy|hustler|red ?light|after dark|18\+",
                          re.I)  # not "adult": "Stairway to Adulthood" is fine
MIN_TITLES = 12000  # MAL entries crawled: 12,951 on 30 Oct 2026. Fewer means Tenrai answered short; keep last week's
MIN_TT = 4500  # tiles with an IMDb id: 5,108 on 30 Oct 2026. Fewer means Fribb's file changed shape


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")  # "Idols (Female)" -> "idols-female"


def get(url, cache_file=None):
    if cache_file and os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": "uk-extras anime lists (github.com/Barticom94/uk-extras)"})
    for wait in (5, 15, 45, None):
        time.sleep(1)  # never more than one request a second
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            break
        except urllib.error.HTTPError as e:
            if wait is None or (e.code != 429 and e.code < 500):
                raise
            if e.code == 429:  # over Tenrai's limit: wait as long as it says
                after = e.headers.get("Retry-After", "")
                wait = max(wait, int(after) if after.isdigit() else 60)
        except (OSError, http.client.HTTPException):
            if wait is None:
                raise
        time.sleep(wait)
    if cache_file:
        with open(cache_file, "wb") as f:
            f.write(body)
    return body


def crawl(cache):
    """(every item on every page, the total Tenrai counted on page 1)."""
    items, page, last, total = [], 1, 1, 0
    while page <= last:
        d = json.loads(get(TENRAI.format(page=page), cache and os.path.join(cache, f"tenrai-{page:03}.json")))
        if page == 1:
            last, total = d["pagination"]["last_visible_page"], d["pagination"]["items"]["total"]
        items += d["data"]
        page += 1
    return items, total


def tile_id(item, row, tt_rows):
    """(id, type) for a MAL entry and its Fribb row (or None). The IMDb id's type is its TMDB key's (movie or tv); with
    no TMDB id, MOVIE is a film and the rest are series. A film filed under its show's TMDB tv id is still a film when
    its IMDb id is its own (on no other row): as a series it would be a dead tile. So is a one-off, a one-episode OVA,
    ONA or special with its own IMDb id: IMDb has those as TV movies, specials or videos (DBZ's History of Trunks)."""
    row = row or {}
    fmt = row.get("type") or (item.get("type") or "").upper().replace("TV SPECIAL", "SPECIAL")  # Fribb's, else MAL's
    movie = fmt == "MOVIE"
    one_off = fmt in ("OVA", "ONA", "SPECIAL") and item.get("episodes") == 1
    tmdb = row.get("themoviedb_id") or {}
    tts = [t for t in row.get("imdb_id") or [] if re.fullmatch(r"tt\d+", str(t))]  # some rows hold [""]
    if tts:
        tt = tts[0]  # a few rows list several; the first is the main one
        if "movie" in tmdb:
            movie = True
        elif "tv" in tmdb:
            movie = (movie or one_off) and tt_rows[tt] == 1
        else:
            movie = movie or (one_off and tt_rows[tt] == 1)
        return tt, "movie" if movie else "series"
    return (f"kitsu:{row['kitsu_id']}" if row.get("kitsu_id") else f"mal:{item['mal_id']}"), "movie" if movie else "series"


def build_lists(items, fribb):
    """(tiles by id, {slug: [ids]}, dropped counts, unique MAL entries). Each list walks the entries most members first
    and takes a tile the first time it comes up, so a show keeps its best rank and a later season can still put it in a
    later decade or another genre."""
    rows = {}
    for r in fribb:
        rows.setdefault(r.get("mal_id"), r)
    tt_rows = collections.Counter(tt for r in fribb for tt in set(r.get("imdb_id") or []))
    entries, seen, dropped = [], set(), collections.Counter()
    for it in items:
        if it["mal_id"] in seen:
            continue  # the order shifts a little while the pages are read
        seen.add(it["mal_id"])
        tid, kind = tile_id(it, rows.get(it["mal_id"]), tt_rows)
        tags = [g for k in ("genres", "explicit_genres", "themes", "demographics") for g in it.get(k) or []]
        poster = (it.get("images") or {}).get("jpg") or {}
        poster = poster.get("large_image_url") or poster.get("image_url")
        if any(g["mal_id"] in ADULT_GENRE_IDS for g in tags) or (it.get("rating") or "").startswith("Rx"):
            dropped["adult"] += 1
        elif it.get("type") in SKIP_TYPES:
            dropped["music, CM, PV"] += 1
        elif it.get("status") == "Not yet aired":
            dropped["not yet aired"] += 1
        elif not poster:
            dropped["no poster"] += 1
        elif PUBLIC_WORDS.search(it.get("title_english") or it["title"]):
            dropped["word in the name"] += 1
        elif it.get("type") in ("Special", "TV Special") and not tid.startswith("tt"):
            dropped["special, no IMDb id"] += 1  # recaps and extras beside the show; AIOMetadata's MAL lists skip them too
        else:
            entries.append((it, {g["name"] for g in tags}, poster, tid, kind))
    entries.sort(key=lambda e: -(e[0].get("members") or 0))  # stable: ties keep Tenrai's order

    tiles, lists = {}, {s: {} for s in ["all"] + [slug(g) for g in GENRES] + DECADES}  # dicts as ordered sets
    for it, names, poster, tid, kind in entries:
        year = (((it.get("aired") or {}).get("prop") or {}).get("from") or {}).get("year") or it.get("year")
        if tid not in tiles:
            tile = {"id": tid, "type": kind, "name": it.get("title_english") or it["title"], "poster": poster,
                    "releaseInfo": str(year) if year else None,
                    "genres": [g["name"] for g in it.get("genres") or [] if g["name"] != "Ecchi"]}  # see GENRES
            tiles[tid] = {k: v for k, v in tile.items() if v}
        for s in ["all"] + [slug(g) for g in GENRES if g in names] + ([f"{year // 10 * 10}s"] if year else []):
            if s in lists:
                lists[s].setdefault(tid)
    return tiles, {s: list(ids) for s, ids in lists.items()}, dropped, len(seen)


def pages(ids):
    return [ids[n:n + PAGE] for n in range(0, len(ids), PAGE)]


def make_index(lists):
    entry = lambda name, s: {"name": name, "slug": s, "count": len(lists[s]), "pages": len(pages(lists[s]))}
    return {"pageSize": PAGE, "all": entry("All anime", "all"), "genres": [entry(g, slug(g)) for g in GENRES],
            "decades": [entry(d, d) for d in DECADES]}


def problems(lists, unique, total, previous, tt):
    """Reasons to keep last week's lists: a crawl that came back short, IMDb ids gone, or a list that emptied or halved."""
    out = []
    if unique < max(MIN_TITLES, 0.99 * total):
        out.append(f"crawled {unique} MAL entries, Tenrai counted {total} (need 99% and {MIN_TITLES}+)")
    if tt < MIN_TT:
        out.append(f"{tt} tiles with an IMDb id (need {MIN_TT}+): has Fribb's file changed?")
    before = {x["slug"]: x["count"] for x in [previous["all"]] + previous["genres"] + previous["decades"]} if previous else {}
    if before and len(lists["all"]) < 0.9 * before["all"]:
        out.append(f"all: {len(lists['all'])} tiles, {before['all']} last time")
    for s, ids in lists.items():
        if len(ids) < (20 if s in DECADES else 1):
            out.append(f"{s}: only {len(ids)}")
        elif len(ids) < before.get(s, 0) / 2:
            out.append(f"{s}: {len(ids)}, under half of {before[s]} last time")
    return out


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def main(out_dir, cache=None):
    start = time.time()
    if cache:
        os.makedirs(cache, exist_ok=True)
    fribb = json.loads(get(FRIBB, cache and os.path.join(cache, "anime-list-full.json")))
    items, total = crawl(cache)
    tiles, lists, dropped, unique = build_lists(items, fribb)
    final = os.path.join(out_dir, "anime")
    previous = None
    if os.path.exists(os.path.join(final, "index.json")):
        with open(os.path.join(final, "index.json"), encoding="utf-8") as f:
            previous = json.load(f)
    tt = sum(t.startswith("tt") for t in tiles)
    print(f"{unique} MAL entries ({total} counted), dropped {dict(dropped)}; {len(tiles)} tiles, {tt} IMDb "
          f"({tt / max(len(tiles), 1):.0%}), {sum(t.startswith('kitsu:') for t in tiles)} kitsu, "
          f"{sum(t.startswith('mal:') for t in tiles)} mal; {time.time() - start:.0f} s")
    print(" ".join(f"{s} {len(ids)}" for s, ids in lists.items()))
    bad = problems(lists, unique, total, previous, tt)
    if bad:
        print("keeping the last lists:", *bad, sep="\n  ", file=sys.stderr)
        return 1

    new = final + ".new"  # a list that got shorter must lose its last pages, so the folder is replaced whole
    shutil.rmtree(new, ignore_errors=True)
    for s, ids in lists.items():
        for n, part in enumerate(pages(ids)):
            write(os.path.join(new, s, f"{n}.json"), {"metas": [tiles[i] for i in part]})
    write(os.path.join(new, "index.json"), make_index(lists))
    shutil.rmtree(final, ignore_errors=True)
    os.replace(new, final)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "public"), sys.argv[2] if len(sys.argv) > 2 else None))
