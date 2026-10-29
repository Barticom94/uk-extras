"""Netflix rows from Netflix's own Top 10 files: UK Top 10 Films, UK Top 10 Shows and Most Popular Films.

python -I build_netflix.py   writes public/catalog/{movie,series}/ukx.netflix-*.json and netflix_matches.txt (both committed; tiny).

Titles are matched to IMDb ids with IMDb's own search suggestions (no key): same title, same kind, released,
and the most popular of those right now. A Netflix chart title is trending on IMDb that week, which settles
names like Within, Wicked or Unforgettable that have several films or shows behind them.
netflix_overrides.json pins the rest by hand.
"""
import datetime as dt
import http.client
import json
import os
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
WEEKLY = "https://www.netflix.com/tudum/top10/data/all-weeks-countries.tsv"
POPULAR = "https://www.netflix.com/tudum/top10/data/most-popular.tsv"
SUGGEST = "https://v2.sg.media-imdb.com/suggestion/{first}/{q}.json"
POSTER = "https://images.metahub.space/poster/medium/{id}/img"
KINDS = {"movie": {"movie", "tvMovie", "tvSpecial", "video"}, "series": {"tvSeries", "tvMiniSeries", "tvSpecial"}}
POPULAR_FROM = 2018  # Netflix's all-time list starts with Bird Box (2018); an older film of the same name is never the one


def fetch(url, tries=3):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (uk-extras weekly build)"})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except (OSError, http.client.HTTPException):  # the 33 MB file sometimes stops short
            if attempt == tries - 1:
                raise
            time.sleep(10)


def tsv(url):
    rows = fetch(url).decode("utf-8-sig").splitlines()
    head = rows[0].split("\t")
    return [dict(zip(head, r.split("\t"))) for r in rows[1:] if r]


def norm(title):
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def suggest(title):
    q = title.lower()
    first = q[0] if q[:1].isascii() and q[:1].isalnum() else "x"
    return json.loads(fetch(SUGGEST.format(first=first, q=urllib.parse.quote(q, safe="")))).get("d", [])


def match(kind, title, overrides, min_year=None):
    """(preview or None, how)."""
    pinned = {k.lower(): v for k, v in overrides.get(kind, {}).items()}
    hits = suggest(title)
    if title.lower() in pinned:
        tid = pinned[title.lower()]
        if not tid:
            return None, "left out by override"
        hit = next((h for h in hits if h.get("id") == tid), {"id": tid, "l": title})
        return preview(hit, kind), "override"
    this_year = dt.date.today().year
    cands = [h for h in hits
             if str(h.get("id", "")).startswith("tt") and norm(h.get("l", "")) == norm(title)
             and h.get("qid") in KINDS[kind] and h.get("y") and h["y"] <= this_year
             and (min_year is None or h["y"] >= min_year)]
    if not cands:
        return None, "NO MATCH on IMDb: add an override"
    cands.sort(key=lambda h: h.get("rank", 10**9))
    how = f"{cands[0]['y']}, IMDb rank {cands[0].get('rank', '?')}"
    if len(cands) > 1:
        how += f" (beat {cands[1]['id']} {cands[1]['y']}, rank {cands[1].get('rank', '?')})"
    return preview(cands[0], kind), how


def preview(hit, kind):
    qid = hit.get("qid")
    out = {
        "id": hit["id"],
        "type": "series" if qid in ("tvSeries", "tvMiniSeries") else ("movie" if qid else kind),
        "name": hit.get("l"),
        "poster": POSTER.format(id=hit["id"]),
        "posterShape": "poster",
        "releaseInfo": str(hit["y"]) if hit.get("y") else None,
    }
    return {k: v for k, v in out.items() if v}


def weekly_rows(rows, overrides, report):
    gb = [r for r in rows if r["country_iso2"] == "GB"]
    week = max(r["week"] for r in gb)
    out = {"Films": [], "TV": []}
    for r in sorted((r for r in gb if r["week"] == week), key=lambda r: int(r["weekly_rank"])):
        kind = "movie" if r["category"] == "Films" else "series"
        item, how = match(kind, r["show_title"], overrides)
        report.append(f"{week} {r['category']:5} {r['weekly_rank']:>2} {r['show_title'][:42]:42} {item['id'] if item else '-':11} {how}")
        if item:
            out[r["category"]].append(item)
    return week, out


def popular_rows(rows, overrides, report):
    films = sorted((r for r in rows if r["category"].startswith("Films")), key=lambda r: -int(r["views_first_91_days"]))
    out = []
    for r in films:
        item, how = match("movie", r["show_title"], overrides, min_year=POPULAR_FROM)
        report.append(f"popular {r['category'][6:]:13} {r['show_title'][:42]:42} {item['id'] if item else '-':11} {how}")
        if item:
            out.append(item)
    return out


def write(rel, metas):
    path = os.path.join(ROOT, "public", rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"metas": metas}, f, ensure_ascii=False, indent=1)
        f.write("\n")


def main():
    with open(os.path.join(ROOT, "netflix_overrides.json"), encoding="utf-8") as f:
        overrides = json.load(f)
    report = []
    week, top = weekly_rows(tsv(WEEKLY), overrides, report)
    popular = popular_rows(tsv(POPULAR), overrides, report)
    summary = f"week {week}: {len(top['Films'])} films, {len(top['TV'])} shows, {len(popular)} most popular films"
    print("\n".join(report + [summary]))
    if len(top["Films"]) < 5 or len(top["TV"]) < 5 or len(popular) < 10:
        print("too few matches, keeping the last files", file=sys.stderr)
        return 1
    write("catalog/movie/ukx.netflix-top10-films.json", top["Films"])
    write("catalog/series/ukx.netflix-top10-shows.json", top["TV"])
    write("catalog/movie/ukx.netflix-popular.json", popular)
    with open(os.path.join(ROOT, "netflix_matches.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("# How each Netflix title was matched. Wrong or missing? Add it to netflix_overrides.json.\n")
        f.write("\n".join(report + [summary]) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
