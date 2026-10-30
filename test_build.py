"""Offline checks for the fiddly bits: python -I test_build.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I leaves the script folder off the path

from build_channels import genre_of, guide_text, iptv, key_of, segments, uk_time
from build_netflix import norm

utc = lambda *a: dt.datetime(*a, tzinfo=dt.timezone.utc).timestamp()
assert uk_time(utc(2026, 10, 25, 0, 59)) == "01:59"  # still BST
assert uk_time(utc(2026, 10, 25, 1, 0)) == "01:00"   # GMT from 01:00 UTC on the last Sunday of October
assert uk_time(utc(2027, 3, 28, 0, 59)) == "00:59"
assert uk_time(utc(2027, 3, 28, 1, 0)) == "02:00"    # BST from 01:00 UTC on the last Sunday of March

assert key_of("HauntTV") == key_of("Haunt TV")
assert key_of("The Wicked Tuna Channel") == key_of("Wicked Tuna")
assert key_of("Masha & the Bear") == key_of("Masha and the Bear")
assert key_of("I Survived…") == key_of("I Survived...") == key_of("I Survived")
assert key_of("Pluto TV Kids") != key_of("Kids")
assert len({key_of("Tennis Channel"), key_of("Tennis TV"), key_of("Tennis+")}) == 3  # three different channels
assert key_of("Bloomberg TV") != key_of("Bloomberg TV+")
assert key_of("Ghost Hunters Channel") == key_of("Ghost Hunters") and key_of("Journy TV") == key_of("Journy")

assert genre_of("Sky News", "News") == "News"
assert genre_of("Sony One | Action Hits", None) == "Movies"
assert genre_of("Movie Music by Stingray", None) == "Music"
assert genre_of("The Kids in the Hall", None) == "Entertainment"
assert genre_of("Pluto TV Slasher Movies", "Halloween") == "Movies"
assert genre_of("Judge Judy", None) == "Entertainment"

# Now and next, worded as the household add-on words its other channels (its own test has the same cases).
t0 = utc(2026, 10, 29, 21)
ev = [(t0, t0 + 1800, "Newsnight"), (t0 + 1800, t0 + 5400, "The Film"), (t0 + 5400, t0 + 7200, "Late News")]
assert guide_text(ev, t0 + 1799) == {"releaseInfo": "Now: Newsnight till 21:30 · Next: 21:30 The Film",
                                     "description": "Now: Newsnight (21:00 to 21:30)\nNext: The Film (21:30 to 22:30)"}
assert guide_text(ev, t0 + 1800)["releaseInfo"] == "Now: The Film till 22:30 · Next: 22:30 Late News"
assert guide_text(ev, t0 + 5460)["releaseInfo"] == "Now: Late News till 23:00"
assert guide_text(ev, t0 - 600)["releaseInfo"] == "Next: 21:00 Newsnight"
assert guide_text(ev, t0 + 7200) == {} and guide_text([], t0) == {}
mid = utc(2026, 10, 29, 23, 30)
late = [(mid, mid + 3600, "Late Film"), (mid + 3600, mid + 5400, "News at Night")]
assert guide_text(late, mid + 1740)["releaseInfo"] == "Now: Late Film till 00:30 · Next: 00:30 News at Night"
filler = [(t0, t0 + 1800, "Sky News"), (t0 + 1800, t0 + 3600, "Sky News"), (t0 + 3600, t0 + 7200, "Film")]
assert guide_text(filler, t0 + 60)["releaseInfo"] == "Now: Sky News till 22:00 · Next: 22:00 Film"
assert guide_text([(t0, t0 + 1800, ""), (t0 + 1800, t0 + 3600, "B")], t0)["releaseInfo"] == "Next: 21:30 B"

# Hourly entries: the text at the hour, then one per change; [from] alone once the guide has run out.
h = utc(2026, 10, 29, 22)
segs = segments(ev, h, h + 3600)
assert [x[0] for x in segs] == [h, t0 + 5400], segs
assert segs[0][1] == "Now: The Film till 22:30 · Next: 22:30 Late News" and segs[1][1] == "Now: Late News till 23:00"
assert segments(ev, h + 1800, h + 5400) == [[int(h + 1800), "Now: Late News till 23:00", "Now: Late News (22:30 to 23:00)"], [int(t0 + 7200)]]
assert segments(ev, h + 3600, h + 7200) == [[int(h + 3600)]], "after the guide: nothing to show"
assert {x[1] for x in segments(filler, t0, t0 + 3600)} == {"Now: Sky News till 22:00 · Next: 22:00 Film"}, "one slot"

assert norm("TYSON") == norm("Tyson") and norm("The Widower: 'Til Death Do Us Part") == "the widower til death do us part"

# iptv/: the household add-on's section order and numbers, one line pair per tile, XML that parses whatever the
# guides hold, programmes that haven't ended and start within 48 hours.
import tempfile
import xml.etree.ElementTree as ET

tiles = [{"id": "ukx:news1", "name": "News\nOne", "poster": 'https://x/a"b\n.png', "genres": ["News"]},
         {"id": "ukx:ent1", "name": "Tom & Jerry", "genres": ["Entertainment"]}]
progs = {"ukx:news1": [(t0 - 7200, t0 - 3600, "Gone"), (t0, t0 + 1800, "A <b> & \x07c", "Desc & more", "https://x/i.png?a=1&b=2"),
                       (t0 + 49 * 3600, t0 + 50 * 3600, "Too far")],
         "ukx:ent1": [(t0, t0 + 600, "Fallback guide")]}  # titles only, as when a service has no XMLTV guide
with tempfile.TemporaryDirectory() as out:
    assert iptv(out, tiles, {"ukx:news1": "https://jmp2.uk/stvp-N\r\n", "ukx:ent1": "https://jmp2.uk/plu-E.m3u8"}, progs, t0 - 60) == 2
    read = lambda n: open(os.path.join(out, "iptv", n), encoding="utf-8").read()
    assert read("free.m3u").split("\n") == [
        '#EXTINF:-1 tvg-id="ukx:ent1" tvg-chno="1001" tvg-logo="" group-title="Entertainment",Tom & Jerry', "https://jmp2.uk/plu-E.m3u8",
        '#EXTINF:-1 tvg-id="ukx:news1" tvg-chno="4001" tvg-logo="https://x/a%22b.png" group-title="News",News One', "https://jmp2.uk/stvp-N",
        ""], read("free.m3u")
    tv = ET.fromstring(f"<tv>{read('channels.xml')}{read('programmes.xml')}</tv>")
    assert [c.findtext("display-name") for c in tv.iter("channel")] == ["Tom & Jerry", "News One"]
    got = [(p.get("channel"), p.findtext("title"), p.findtext("desc"), (p.find("icon") is not None) and p.find("icon").get("src"))
           for p in tv.iter("programme")]
    assert got == [("ukx:ent1", "Fallback guide", None, False), ("ukx:news1", "A <b> & c", "Desc & more", "https://x/i.png?a=1&b=2")], got
    assert next(tv.iter("programme")).get("start") == "20261029210000 +0000"

# Anime: MAL entry -> id and type from Fribb's rows, merged seasons, list order, decades, pages and the sanity gate.
import collections
from build_anime import DECADES, GENRES, build_lists, make_index, pages, problems, slug, tile_id

fribb = [{"mal_id": 1, "type": "TV", "imdb_id": ["tt1"], "themoviedb_id": {"tv": 10}},
         {"mal_id": 2, "type": "TV", "imdb_id": ["tt1"], "themoviedb_id": {"tv": 10}},     # season 2: same show
         {"mal_id": 3, "type": "MOVIE", "imdb_id": ["tt3"], "themoviedb_id": {"tv": 10}},  # film with its own tt
         {"mal_id": 4, "type": "MOVIE", "imdb_id": ["tt1"], "themoviedb_id": {"tv": 10}},  # film filed as the show
         {"mal_id": 5, "type": "MOVIE", "imdb_id": ["tt5", "tt55"]},
         {"mal_id": 6, "type": "OVA", "imdb_id": ["tt6"], "themoviedb_id": {"movie": [60]}},
         {"mal_id": 7, "type": "OVA", "imdb_id": [""], "kitsu_id": 77},  # Fribb has a few empty ids
         {"mal_id": 20, "type": "SPECIAL", "imdb_id": ["tt20"], "themoviedb_id": {"tv": 10}},  # TV special, own tt
         {"mal_id": 21, "type": "SPECIAL", "imdb_id": ["tt1"], "themoviedb_id": {"tv": 10}},   # special filed as the show
         {"mal_id": 22, "imdb_id": ["tt22"]}]  # no type, no TMDB id: MAL's type counts
rows = {r["mal_id"]: r for r in fribb}
tt_rows = collections.Counter(tt for r in fribb for tt in r.get("imdb_id") or [])
ids = {m: tile_id({"mal_id": m, "type": "TV"}, rows.get(m), tt_rows) for m in (1, 2, 3, 4, 5, 6, 7, 8)}
assert ids == {1: ("tt1", "series"), 2: ("tt1", "series"), 3: ("tt3", "movie"), 4: ("tt1", "series"),
               5: ("tt5", "movie"), 6: ("tt6", "movie"), 7: ("kitsu:77", "series"), 8: ("mal:8", "series")}, ids
assert tile_id({"mal_id": 9, "type": "Movie"}, None, tt_rows) == ("mal:9", "movie")
one = lambda mal, eps, kind="Special": tile_id({"mal_id": mal, "type": kind, "episodes": eps}, rows.get(mal), tt_rows)
assert one(20, 1) == ("tt20", "movie") and one(20, 3) == ("tt20", "series"), "a one-off is a film, a run of specials isn't"
assert one(21, 1) == ("tt1", "series") and one(22, 1, "TV Special") == ("tt22", "movie") and one(22, 1, "TV") == ("tt22", "series")


def anime(mal, members, aired=2010, kind="TV", genres=(), themes=(), **more):
    tags = lambda names: [{"mal_id": 12 if n == "adult" else 0, "name": n} for n in names]
    return {"mal_id": mal, "members": members, "type": kind, "status": "Finished Airing", "title": f"T{mal}",
            "images": {"jpg": {"large_image_url": f"https://x/{mal}l.jpg"}}, "aired": {"prop": {"from": {"year": aired}}},
            "genres": tags(genres), "themes": tags(themes)} | more


items = [anime(2, 500, 2012, genres=["Action"], title_english="Show Season 2"),  # out of order, as a crawl can be
         anime(1, 900, 2009, genres=["Action", "Ecchi"], themes=["School"], title_english="Show"),
         anime(1, 900, 2009), anime(3, 800, 2015, "Movie", genres=["Romance"]), anime(8, 700, kind="Music"),
         anime(9, 650, status="Not yet aired"), anime(10, 600, genres=["adult"]),
         anime(11, 550, None, year=1995), anime(12, 540, 1950), anime(13, 530, title_english="xxxHOLiC"),
         anime(14, 520, kind="Special"), anime(20, 510, 1985, "TV Special", episodes=1)]  # a recap; a TV special
tiles, lists, dropped, unique = build_lists(items, fribb)
assert tiles["tt1"] == {"id": "tt1", "type": "series", "name": "Show", "poster": "https://x/1l.jpg", "releaseInfo": "2009",
                        "genres": ["Action"]}, tiles["tt1"]
assert tiles["tt3"]["type"] == "movie" and tiles["tt3"]["name"] == "T3" and set(tiles) == {"tt1", "tt3", "mal:11", "mal:12", "tt20"}
assert lists["all"] == ["tt1", "tt3", "mal:11", "mal:12", "tt20"] and lists["action"] == ["tt1"] == lists["ecchi"] == lists["school"]
assert lists["2000s"] == ["tt1"] and lists["2010s"] == ["tt3", "tt1"], "season 2 puts the show in the 2010s at its own rank"
assert lists["1990s"] == ["mal:11"] and not any("mal:12" in lists[d] for d in DECADES)
assert dropped == {"music, CM, PV": 1, "not yet aired": 1, "adult": 1, "word in the name": 1, "special, no IMDb id": 1}
assert unique == 11 and tiles["tt20"]["type"] == "movie" and lists["1980s"] == ["tt20"]

assert [len(p) for p in pages(list(range(120)))] == [50, 50, 20] and len(pages(list(range(100)))) == 2 and pages([]) == []
assert slug("Idols (Female)") == "idols-female" and slug("Sci-Fi") == "sci-fi" and len({slug(g) for g in GENRES}) == len(GENRES) == 76
ok = {s: list(range(30)) for s in ["all"] + [slug(g) for g in GENRES] + DECADES}
assert make_index(ok)["genres"][0] == {"name": "Action", "slug": "action", "count": 30, "pages": 1}
assert problems(ok, 13000, 12951, None, 5000) == [] and problems(ok, 12900, 13100, None, 5000) != []  # under 99%
assert problems(ok, 11000, 11000, None, 5000) != [] and problems(ok | {"1960s": [1]}, 13000, 13000, None, 5000) == ["1960s: only 1"]
assert problems(ok, 13000, 13000, make_index(ok | {"action": list(range(100))}), 5000) == ["action: 30, under half of 100 last time"]
assert problems(ok, 13000, 13000, None, 0) != [], "Fribb loaded but mapped nothing: keep last week's IMDb ids"
print("ok")
