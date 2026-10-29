"""Check a built site before it goes live: python -I validate.py [_site]

Follows the same URLs NuvioTV builds (CatalogRepositoryImpl, MetaRepositoryImpl, StreamRepositoryImpl on dev:
ids and extras go through URLEncoder, so "ukx:abc" is asked for as "ukx%3Aabc.json"; GitHub Pages decodes that
back to the file "ukx:abc.json"). Exits 1 on the first broken rule it finds.
"""
import json
import os
import re
import sys
import urllib.parse

MANIFEST_ID = "com.barticom94.ukextras"
CATALOGS = [
    ("series", "ukx.netflix-top10-shows", "Netflix UK Top 10 Shows"),
    ("movie", "ukx.netflix-top10-films", "Netflix UK Top 10 Films"),
    ("movie", "ukx.netflix-popular", "Netflix Most Popular Films"),
    ("tv", "ukx.free", "Free UK Channels"),
]
GENRES = ["News", "Entertainment", "Movies", "Kids", "Sport", "Documentary", "Music", "Lifestyle"]
ADULT = re.compile(r"erotic|xxx|porn|playboy|hustler|red ?light|naughty|after dark|18\+", re.I)


def java_encode(s):  # java.net.URLEncoder.encode(s, "UTF-8").replace("+", "%20")
    return urllib.parse.quote(s, safe="*").replace("~", "%7E")


def load(site, url_path):
    """Read the file GitHub Pages would serve for this request path."""
    rel = urllib.parse.unquote(url_path)
    if os.name == "nt":  # local Windows builds swap ":" in file names (NTFS)
        head, tail = os.path.split(rel)
        rel = os.path.join(head, tail.replace(":", "%3A"))
    with open(os.path.join(site, rel), encoding="utf-8") as f:
        return json.load(f)


def main(site):
    errors = []
    fail = errors.append

    m = load(site, "manifest.json")
    if m.get("id") != MANIFEST_ID or m.get("name") != "UK Extras":
        fail("manifest id or name")
    got = [(c["type"], c["id"], c["name"]) for c in m["catalogs"]]
    if got != CATALOGS:
        fail(f"catalogues differ from the agreed ids: {got}")
    if any(c.get("showInHome") is not False for c in m["catalogs"]):
        fail("every catalogue needs showInHome: false")
    free = next(c for c in m["catalogs"] if c["id"] == "ukx.free")
    if free.get("extra") != [{"name": "genre", "isRequired": False, "options": GENRES}]:
        fail("ukx.free genre extra")
    for res in m["resources"][1:]:
        if res.get("idPrefixes") != ["ukx:"] or res.get("types") != ["tv"]:
            fail(f"{res.get('name')} must be limited to tv + ukx:")
    if re.search("[–—]", json.dumps(m, ensure_ascii=False)):
        fail("en or em dash in the manifest")

    counts = {}
    for ctype, cid, _ in CATALOGS:
        metas = load(site, f"catalog/{ctype}/{cid}.json")["metas"]
        counts[cid] = len(metas)
        if len({x["id"] for x in metas}) != len(metas):
            fail(f"{cid}: duplicate ids")
        for x in metas:
            if not (x.get("id") and x.get("type") and x.get("name") and x.get("poster")):
                fail(f"{cid}: incomplete item {x.get('id')}")
            if ADULT.search(x.get("name", "")):
                fail(f"{cid}: adult name {x['name']}")
        if cid.startswith("ukx.netflix"):
            if len(metas) < 5 or not all(re.fullmatch(r"tt\d+", x["id"]) and x["type"] in ("movie", "series") for x in metas):
                fail(f"{cid}: needs 5+ IMDb items")
            continue
        # Free channels: every tile opens (meta) and plays (stream) from this add-on.
        if len(metas) < 100:
            fail(f"{cid}: only {len(metas)} channels")
        ids = set()
        for x in metas:
            ids.add(x["id"])
            if not x["id"].startswith("ukx:") or x["type"] != "tv":
                fail(f"{x['id']}: not a ukx: tv id")
                continue
            try:
                meta = load(site, f"meta/tv/{java_encode(x['id'])}.json")["meta"]
                streams = load(site, f"stream/tv/{java_encode(x['id'])}.json")["streams"]
            except (OSError, ValueError, KeyError) as e:
                fail(f"{x['id']}: {type(e).__name__} {e}")
                continue
            if meta["id"] != x["id"] or meta["name"] != x["name"]:
                fail(f"{x['id']}: meta does not match the tile")
            if not streams or not all(s["url"].startswith("https://") for s in streams):
                fail(f"{x['id']}: no https stream")
            if not all((s.get("behaviorHints", {}).get("filename") or s["url"]).endswith(".m3u8") for s in streams):
                fail(f"{x['id']}: a stream Nuvio can't tell is HLS (no .m3u8 url or filename hint)")
        seen = set()
        for g in GENRES:
            part = load(site, f"catalog/tv/{cid}/{java_encode('genre')}={java_encode(g)}.json")["metas"]
            counts[f"{cid} {g}"] = len(part)
            if any(p["id"] not in ids or p["genres"] != [g] for p in part):
                fail(f"genre {g}: item outside the full list or with another genre")
            seen |= {p["id"] for p in part}
        if seen != ids:
            fail("genre files do not add up to the full list")

    size = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(site) for f in fs)
    print(json.dumps(counts, indent=1))
    print(f"site size {size / 1e6:.1f} MB")
    for e in errors[:30]:
        print("FAIL", e)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "_site"))
