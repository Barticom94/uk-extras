"""Offline checks for the fiddly bits: python -I test_build.py"""
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I leaves the script folder off the path

from build_channels import genre_of, key_of, now_next, uk_time
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

t = utc(2026, 10, 29, 11, 20)
progs = [(utc(2026, 10, 29, 11), utc(2026, 10, 29, 11, 30), "Sky News at 11"), (utc(2026, 10, 29, 11, 30), utc(2026, 10, 29, 12), "Sky News Today")]
assert now_next(progs, t) == ["Now: 11:00 Sky News at 11", "Next: 11:30 Sky News Today"]
assert now_next([], t) == []

assert norm("TYSON") == norm("Tyson") and norm("The Widower: 'Til Death Do Us Part") == "the widower til death do us part"
print("ok")
