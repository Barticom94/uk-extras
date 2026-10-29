"""Free UK channels: build the ukx.free and uks.<section> catalogues, metas, streams and the hourly now and next files
(live/) from i.mjh.nz (Samsung TV Plus, Pluto TV, Plex).

python -I build_channels.py [out_dir]   (default _site). Copies public/ (manifest + Netflix rows) into out_dir first.
Standard library only. Runs hourly in GitHub Actions; nothing it downloads is committed.
"""
import datetime as dt
import gzip
import io
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
GENRES = ["News", "Entertainment", "Movies", "Kids", "Sport", "Documentary", "Music", "Lifestyle"]
# The uks.<section> catalogue (Sky's guide sections, as the household add-on names them) for each genre.
SECTIONS = {"Entertainment": "entertainment", "Movies": "films", "Sport": "sport", "News": "news",
            "Documentary": "documentaries", "Kids": "kids", "Music": "music", "Lifestyle": "lifestyle"}
LIVE_HOURS = 48  # live/<section>/<UTC hour>.json for this many hours ahead, as far as the guides reach

# Order = which copy plays first when a channel is on more than one service (see README: tested from a UK line).
SERVICES = [
    ("SamsungTVPlus", "Samsung TV Plus", "https://jmp2.uk/stvp-{id}"),
    ("PlutoTV", "Pluto TV", "https://jmp2.uk/plu-{id}.m3u8"),
    ("Plex", "Plex", "https://jmp2.uk/plex-{id}.m3u8"),
]
KEEP_SUFFIX = {"tennis"}  # Tennis Channel and Tennis TV are different channels, so "channel"/"tv" stays on these
CHANNELS_URL = "https://i.mjh.nz/{svc}/.channels.json.gz"
EPG_URL = "https://i.mjh.nz/{svc}/gb.xml.gz"

GROUP_GENRE = {
    # Samsung TV Plus
    "Entertainment": "Entertainment", "Documentaries": "Documentary", "Sport": "Sport", "Reality": "Entertainment",
    "Movies": "Movies", "Music & Ambient": "Music", "Kids": "Kids", "TV Series": "Entertainment", "Crime": "Documentary",
    "Nature": "Documentary", "News": "News", "Food & Travel": "Lifestyle",
    # Pluto TV ("Halloween" and "New on Pluto TV" are mixed bags, so they fall through to the name rules)
    "True Crime": "Documentary", "Sports": "Sport", "Real Life Adventure": "Entertainment", "Sci-Fi & Fantasy": "Entertainment",
    "Crime Drama": "Entertainment", "Comedy": "Entertainment", "Paranormal": "Entertainment", "Living": "Lifestyle",
    "Bingeable Drama": "Entertainment", "Classic TV": "Entertainment", "Music": "Music",
}
# Plex has no groups, so its channels (and the mixed Pluto groups) are sorted by name. First match wins.
NAME_GENRE = [
    ("News", r"\bnews|bloomberg|\bcnn|euronews|reuters|france 24|al jazeera|\bdw\b|cnbc|usa today|yahoo finance|weather"),
    ("Kids", r"kids(?! in the hall)|junior|toon|baby|pocoyo|teletubbies|lego|barbie|pok[eé]mon|smurf|masha|wiggles|^arthur|sonic|beyblade|yu-gi-oh"
             r"|inazuma|strawberry shortcake|ryan and friends|^pop( up)?$|tiny pop|watch it kid|pocket\.watch|brat tv|h2o"
             r"|camp spoopy|123go|eddie's wonderland|preston|raccoons|totally turtles|mona the vampire|animated"),
    ("Sport", r"sport|football|golf|tennis|racing|racer|wrestling|fight|boxing|mma|ufc|pfl|motor|nfl|nhra|monster jam|rugby"
              r"|fifa|cricket|poker|darts|snooker|billiard|bowling|cornhole|pickle|surf|slopes|powder|bassmaster|fish"
              r"|strongman|glory|tna|xfc|combatv|swac|pac-12|speedvision|fuel tv|inter 24/7|man city|hard knocks|unbeaten"
              r"|ringside|dazn|crouch podcast|rally"),
    ("Movies", r"movie(?! music)|film|cinema|flix|western|hollywood|screen classics|thriller|horror|slasher|creature|curzon"
               r"|icons unearthed|^sony one|trailers|scream|maverick black|bollywood|nolly"),
    ("Music", r"music|vevo|hits|xite|trace|vibes|karaoke|rock|jazz|hot country|classica|concert|k-pop|kpop|hip-hop|soul"
              r"|that's [0-9]|y2k|easy listening|def jam|stingray|qello|veeps|qwest|pop adult|flashback|remember the"
              r"|nothin' but|alternative"),
    ("Lifestyle", r"food|kitchen|cook|chef|menu|travel|voyage|journy|home|house|garden|living|style|fashion|craft|design"
                  r"|antique|deal masters|flipping|pets|pet collective|dog whisperer|martha|\bspa\b|zen|carwow|\bcars\b"
                  r"|fifth gear|powernation|nomad|escape to the country|million dollar|hoarders"),
    ("Documentary", r"doc|history|nature|wild|planet|earth|science|crime|curiosity|animal|space|cosmic|marvels|mayday"
                    r"|survived|\bwar\b|ice road|alive|mythbusters|investigation|detectives|evil|homicide|first 48|murder"
                    r"|unsolved|magellan|factual|startalk|pbs|conspiracy|alien"),
]
BRAND_TAG = re.compile(r"\s*[:\-]?\s*'?powered by banijay'?", re.I)  # "Pointless UK: 'Powered by Banijay'" -> "Pointless UK"
# Public add-on: never list adult channels. Also drop channels aimed at other countries' languages.
ADULT = re.compile(r"erotic|xxx|porn|playboy|hustler|red ?light|naughty|after dark|18\+", re.I)
OTHER_LANGUAGE = re.compile(
    r"español|escándalos|novelisima|pelimex|en alerta|deportes|conflicto|ideas en|éxitos|brazuca|latina|movieitaly"
    r"|deutsch|français|italiano|portuguese|pitufo|tv5monde|lucha plus|billboard espa", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "uk-extras-build (github.com/Barticom94/uk-extras)"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def key_of(name):
    """Name used to merge the same channel across services: 'The Wicked Tuna Channel' == 'Wicked Tuna', 'HauntTV' == 'Haunt TV'."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ")
    s = re.sub(r"\bby (lionsgate|mech\+|stingray)\b|\bon plex\b|\bhd\b", " ", s)
    s = re.sub(r"[^a-z0-9+]+", "", s).replace("+", "plus")  # Tennis+ and Bloomberg TV+ are channels of their own
    s = re.sub(r"^the", "", s)
    stem = re.sub(r"(channel|tv)$", "", s)
    return s if stem in KEEP_SUFFIX else stem


def genre_of(name, group):
    g = GROUP_GENRE.get(group or "")
    if g:
        return g
    for genre, pattern in NAME_GENRE:
        if re.search(pattern, name, re.I):
            return genre
    return "Entertainment"


def uk_time(ts):
    """HH:MM in UK time. Stdlib only (Windows has no tz database): BST runs from the last Sunday of March to the last Sunday of October, 01:00 UTC."""
    t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)

    def last_sunday(month):
        d = dt.datetime(t.year, month, 31, 1, tzinfo=dt.timezone.utc)
        return d - dt.timedelta(days=(d.weekday() + 1) % 7)

    if last_sunday(3) <= t < last_sunday(10):
        t += dt.timedelta(hours=1)
    return t.strftime("%H:%M")


def load_service(svc):
    data = json.loads(gzip.decompress(fetch(CHANNELS_URL.format(svc=svc))))
    if svc == "Plex":
        chans = {k: v for k, v in data["channels"].items() if "gb" in v.get("regions", [])}
    else:
        chans = data["regions"]["gb"]["channels"]
    return chans


def load_epg(svc, wanted, now):
    """{channel_id: [(start, stop, title), ...]} for programmes that have not ended yet, sorted."""
    out = {}
    raw = gzip.decompress(fetch(EPG_URL.format(svc=svc)))
    for _, el in ET.iterparse(io.BytesIO(raw)):
        if el.tag != "programme":
            continue
        cid = el.get("channel")
        if cid in wanted:
            stop = dt.datetime.strptime(el.get("stop"), "%Y%m%d%H%M%S %z").timestamp()
            if stop > now:
                start = dt.datetime.strptime(el.get("start"), "%Y%m%d%H%M%S %z").timestamp()
                out.setdefault(cid, []).append((start, stop, (el.findtext("title") or "").strip()))
        el.clear()
    for progs in out.values():
        progs.sort()
    return out


def now_next(progs, now):
    """(now, next) as (start, stop, title), either None, like the household add-on's nowNext. Back-to-back slots with
    the same title count as one (news channels repeat theirs hourly)."""
    i = next((k for k, p in enumerate(progs) if p[1] > now), None)
    if i is None:
        return None, None
    j = i
    while j + 1 < len(progs) and progs[j + 1][2] == progs[i][2] and progs[j + 1][0] == progs[j][1]:
        j += 1
    first = (progs[i][0], progs[j][1], progs[i][2])
    after = progs[j + 1] if j + 1 < len(progs) else None
    return (first, after) if progs[i][0] <= now else (None, first)


def guide_text(progs, now):
    """{releaseInfo, description} worded like the household add-on's other channels, or {} with nothing to show.
    releaseInfo is the line Nuvio shows under the name in grids and rows; description shows on focus and the detail page."""
    cur, nxt = (p if p and p[2] else None for p in now_next(progs, now))
    if not (cur or nxt):
        return {}
    line = [cur and f"Now: {cur[2]} till {uk_time(cur[1])}", nxt and f"Next: {uk_time(nxt[0])} {nxt[2]}"]
    full = [cur and f"Now: {cur[2]} ({uk_time(cur[0])} to {uk_time(cur[1])})",
            nxt and f"Next: {nxt[2]} ({uk_time(nxt[0])} to {uk_time(nxt[1])})"]
    return {"releaseInfo": " · ".join(filter(None, line)), "description": "\n".join(filter(None, full))}


def segments(progs, start, end):
    """The text for the hour [start, end): [[from, releaseInfo, description], ...] with a new entry each time it changes,
    [from] alone when there is nothing to show. The household add-on uses the last entry that has started."""
    out = []
    for t in sorted({start} | {x for p in progs for x in p[:2] if start < x < end}):
        g = guide_text(progs, t)
        seg = [int(t), g["releaseInfo"], g["description"]] if g else [int(t)]
        if not out or out[-1][1:] != seg[1:]:
            out.append(seg)
    return out


def file_name(item_id):
    # Pages serves "ukx:abc.json" for Nuvio's "ukx%3Aabc.json". NTFS can't hold ":" so local Windows runs swap it.
    return item_id.replace(":", "%3A") if os.name == "nt" else item_id


def tile_json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def build(out_dir, now=None):
    now = now or dt.datetime.now(dt.timezone.utc).timestamp()
    merged, dropped = {}, {"drm": 0, "adult": 0, "language": 0}
    for rank, (svc, label, template) in enumerate(SERVICES):
        chans = load_service(svc)
        epg = load_epg(svc, set(chans), now)
        for cid, c in chans.items():
            name = BRAND_TAG.sub("", c.get("name") or "").strip()
            if not name:
                continue
            if c.get("license_url"):
                dropped["drm"] += 1  # Widevine: Nuvio can't play DRM
                continue
            if ADULT.search(name) or ADULT.search(c.get("group") or ""):
                dropped["adult"] += 1
                continue
            if OTHER_LANGUAGE.search(name):
                dropped["language"] += 1
                continue
            ps = c.get("programs") or []  # fallback guide: start times only, so each show ends when the next starts
            progs = epg.get(cid) or [(a[0], b[0], a[1]) for a, b in zip(ps, ps[1:]) if b[0] > now]
            copy = {
                "service": label, "url": template.format(id=cid), "name": name, "logo": c.get("logo"),
                "art": c.get("art"), "description": (c.get("description") or "").strip(),
                "genre": genre_of(name, c.get("group")), "progs": progs,
                # Samsung's and Pluto's channel numbers are their own curated order (Sky News, CNN, GB News...)
                "order": (rank, c.get("chno") or 10**6, name.lower()),
            }
            ch = merged.setdefault(key_of(name), [])
            if all(x["service"] != label for x in ch):
                ch.append(copy)  # one copy per service: Plex lists some channels twice under different ids

    if os.path.isdir(os.path.join(ROOT, "public")):
        shutil.copytree(os.path.join(ROOT, "public"), out_dir, dirs_exist_ok=True)
    metas, previews, guides = [], [], {}
    for key, copies in merged.items():
        first = copies[0]
        # Keep a mixed-case name if the first copy shouts ("MOVIESPHERE" vs "Moviesphere").
        name = next((c["name"] for c in copies if not c["name"].isupper()), first["name"])
        # The guide that reaches furthest: copies of one channel run the same programmes, and Samsung's guide is the shortest.
        progs = max((c["progs"] for c in copies), key=lambda ps: ps[-1][1] if ps else 0)
        about = next((c["description"] for c in copies if c["description"]), "")
        meta = {
            "id": f"ukx:{key}", "type": "tv", "name": name,
            "poster": first["logo"], "posterShape": "square", "logo": first["logo"],
            "background": next((c["art"] for c in copies if c["art"]), None),
            # No now and next in the files here: they only change with a build, and GitHub's schedule hasn't run for
            # this repo yet, so build-time text would show finished programmes for hours. It is in live/ instead.
            "description": about,
            "genres": [first["genre"]],
            "behaviorHints": {"isLive": True},
        }
        meta = {k: v for k, v in meta.items() if v not in (None, "")}
        metas.append(meta)
        guides[meta["id"]] = progs
        # The tile is the name and logo; the blurb is on the detail page.
        previews.append((GENRES.index(first["genre"]), first["order"],
                         {k: meta[k] for k in ("id", "type", "name", "poster", "posterShape", "genres") if k in meta}))
        # Nuvio picks HLS from the file name (behaviorHints.filename, then the URL). jmp2.uk/stvp-<id> has no
        # extension, so without the hint ExoPlayer first tries it as a plain file and only recovers via its fallback.
        streams = [{"name": c["service"], "title": c["name"], "url": c["url"]}
                   | ({} if c["url"].endswith(".m3u8") else {"behaviorHints": {"filename": c["url"].rsplit("/", 1)[1] + ".m3u8"}})
                   for c in copies]
        write(os.path.join(out_dir, "meta", "tv", file_name(meta["id"]) + ".json"), {"meta": meta})
        write(os.path.join(out_dir, "stream", "tv", file_name(meta["id"]) + ".json"), {"streams": streams})

    previews = [p for *_, p in sorted(previews, key=lambda p: p[:2])]
    write(os.path.join(out_dir, "catalog", "tv", "ukx.free.json"), {"metas": previews})
    hour = int(now // 3600 * 3600)
    for g in GENRES:
        tiles = [m for m in previews if m["genres"][0] == g]
        write(os.path.join(out_dir, "catalog", "tv", "ukx.free", f"genre={g}.json"), {"metas": tiles})
        # The same tiles as Sky's guide section: what the Pages install shows in Live TV folders.
        write(os.path.join(out_dir, "catalog", "tv", f"uks.{SECTIONS[g]}.json"), {"metas": tiles})
        # For the household add-on, which puts these after its own channels: live/<section>/<UTC hour>.json for every
        # hour ahead, one row per tile, [id, [from, tile JSON], ...], each tile JSON with the now and next from `from`.
        # It pastes the entry that has started into its response as it is (no clock maths, no tile objects), and the
        # text stays right after this build for as long as each guide reaches, build or no build.
        # names.json, the tiles alone, is what it shows once the hours run out.
        write(os.path.join(out_dir, "live", SECTIONS[g], "names.json"), [[m["id"], [0, tile_json(m)]] for m in tiles])
        for h in range(hour, hour + (LIVE_HOURS + 1) * 3600, 3600):
            rows = [[m["id"]] + [[x[0], tile_json(m | ({"releaseInfo": x[1], "description": x[2]} if len(x) > 1 else {}))]
                                 for x in segments(guides[m["id"]], h, h + 3600)] for m in tiles]
            name = dt.datetime.fromtimestamp(h, dt.timezone.utc).strftime("%Y%m%d%H") + ".json"
            write(os.path.join(out_dir, "live", SECTIONS[g], name), rows)
    counts = {g: sum(m["genres"][0] == g for m in metas) for g in GENRES}
    multi = sum(len(c) > 1 for c in merged.values())
    print(f"free channels: {len(metas)} ({multi} on more than one service); dropped {dropped}; by genre {counts}")
    return metas


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "_site"))
