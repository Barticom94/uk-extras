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
print("ok")
