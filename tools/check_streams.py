"""Silent stream check, run by hand from a UK line: python -I tools/check_streams.py [site_dir] [sample_size]

Downloads only playlists (master + first media playlist), never segments, so nothing plays.
Tests every copy of a random sample of channels, and every copy of the channels found on more than one service,
then prints how each service did. Nothing is written to disk.
"""
import concurrent.futures as cf
import json
import os
import random
import re
import sys
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Linux; Android 12; Google TV Streamer) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.geturl(), r.read(500_000).decode("utf-8", "replace")


def check(url):
    try:
        final, body = get(url)
        if not body.lstrip().startswith("#EXTM3U"):
            return {"ok": False, "why": "not a playlist"}
        heights = [int(h) for h in re.findall(r"RESOLUTION=\d+x(\d+)", body)]
        media = body
        if "#EXT-X-STREAM-INF" in body:
            lines = body.splitlines()
            i = next(i for i, l in enumerate(lines) if l.startswith("#EXT-X-STREAM-INF"))
            nxt = next(l for l in lines[i + 1:] if l.strip() and not l.startswith("#"))
            media = get(urllib.parse.urljoin(final, nxt.strip()))[1]
        if "SAMPLE-AES" in media or "com.widevine" in media.lower():
            return {"ok": False, "why": "DRM"}
        if "#EXTINF" not in media:
            return {"ok": False, "why": "no segments"}
        return {"ok": True, "height": max(heights, default=0), "host": urllib.parse.urlsplit(final).netloc}
    except Exception as e:
        return {"ok": False, "why": f"{type(e).__name__} {getattr(e, 'code', '')}".strip()}


def main():
    site = sys.argv[1] if len(sys.argv) > 1 else "_site"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    metas = json.load(open(os.path.join(site, "catalog", "tv", "ukx.free.json"), encoding="utf-8"))["metas"]
    fname = lambda i: (i.replace(":", "%3A") if os.name == "nt" else i) + ".json"
    streams = {m["id"]: json.load(open(os.path.join(site, "stream", "tv", fname(m["id"])), encoding="utf-8"))["streams"] for m in metas}
    random.seed(29)
    pick = set(random.sample([m["id"] for m in metas], n)) | {i for i, s in streams.items() if len(s) > 1}
    jobs = [(i, s) for i in sorted(pick) for s in streams[i]]
    with cf.ThreadPoolExecutor(3) as pool:  # Plex answers bursts with HTTP 429
        results = list(pool.map(lambda j: (j[0], j[1]["name"], check(j[1]["url"])), jobs))
    by_service = {}
    for _, svc, r in results:
        b = by_service.setdefault(svc, {"ok": 0, "bad": 0, "heights": [], "why": {}})
        if r["ok"]:
            b["ok"] += 1
            b["heights"].append(r["height"])
        else:
            b["bad"] += 1
            b["why"][r["why"]] = b["why"].get(r["why"], 0) + 1
    print(f"checked {len(results)} playlists across {len(pick)} channels")
    for svc, b in by_service.items():
        hs = sorted(b["heights"])
        median = hs[len(hs) // 2] if hs else 0
        print(f"  {svc:16} ok {b['ok']:3}  failed {b['bad']:3}  median top height {median}p  failures {b['why']}")
    # Duplicates: which copy is better when a channel is on several services?
    res = {}
    for i, svc, r in results:
        res.setdefault(i, {})[svc] = r
    wins = {}
    for i, rs in res.items():
        if len(rs) < 2:
            continue
        good = {s: r["height"] for s, r in rs.items() if r["ok"]}
        if good:
            best = max(good.values())
            for s, h in good.items():
                if h == best:
                    wins[s] = wins.get(s, 0) + 1
    print(f"  duplicates: copies that play at the best height found -> {wins}")
    failed = [(i, svc, r["why"]) for i, svc, r in results if not r["ok"]]
    for f in failed[:40]:
        print("  failed:", *f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
