# UK Extras

A small static Stremio add-on for Nuvio, served from GitHub Pages:

    https://barticom94.github.io/uk-extras/manifest.json

| Catalogue | Type | Id | Rebuilt |
|---|---|---|---|
| Netflix UK Top 10 Shows | series | `ukx.netflix-top10-shows` | weekly |
| Netflix UK Top 10 Films | movie | `ukx.netflix-top10-films` | weekly |
| Netflix Most Popular Films | movie | `ukx.netflix-popular` | weekly |
| Free UK Channels | tv | `ukx.free` (genre: News, Entertainment, Movies, Kids, Sport, Documentary, Music, Lifestyle) | hourly |
| Entertainment, Films, Sport, News, Documentaries, Kids, Music, Lifestyle | tv | `uks.entertainment`, `uks.films`, `uks.sport`, `uks.news`, `uks.documentaries`, `uks.kids`, `uks.music`, `uks.lifestyle` | hourly |

Every catalogue has `showInHome: false`: they are meant for collection folders, not the home screen.
Netflix items are IMDb ids, so your metadata and stream add-ons open and play them. Free channels use `ukx:` ids,
and this add-on serves their meta and streams.

The `uks.*` catalogues are the free channels by section (each is the matching genre: Movies is Films, Documentary is
Documentaries), so the shared collection's Live TV folders work with this add-on alone. A household add-on with this
add-on's id serves the same catalogue ids with more channels in them; a profile has one or the other.

## Free channels

`build_channels.py` reads the GB channel lists and guides from [i.mjh.nz](https://i.mjh.nz/) for Samsung TV Plus,
Pluto TV and Plex (`<service>/.channels.json.gz` and `<service>/gb.xml.gz`). It:

- merges a channel that is on more than one service and keeps every copy as a stream, best first:
  Samsung TV Plus, then Pluto TV, then Plex (tested from a UK line on 29 Oct 2026: Samsung 119 of 120 and Pluto 76 of 77
  playlists answered; Plex answered too but rate-limits bursts with HTTP 429);
- drops channels that need DRM (Nuvio can't play them), adult channels and channels for other languages' markets;
- writes what's on now and next (UK time) into `live/<section>/<UTC hour>.json` only, for this hour and the 48 after:
  one row per channel, `[id, [from, tile JSON], ...]`, each tile with the now and next from `from` (seconds) as
  `releaseInfo` (`Now: X till 18:00 · Next: 18:00 Y`, the line Nuvio shows under a tile's name) and `description`
  (`Now: X (17:00 to 18:00)`), plus `live/<section>/names.json` with the tiles alone. A reader that picks the entry
  that has started shows the right now and next between builds, for as long as each guide reaches: on 29 Oct Samsung
  TV Plus's guide reached about 6 hours ahead, Pluto TV's about 14, Plex's up to 60. The household add-on reads these;
- keeps now and next out of the catalogues and metas here (names, logos and blurbs only): Pages serves them as they
  were built, and with no hourly build (see below) they would show programmes that finished hours ago. So this
  add-on on its own has no now and next; `validate.py` fails a build that puts it back;
- sorts each genre in Samsung's and Pluto's own channel order, then Plex alphabetically;
- writes the pieces an IPTV playlist and guide need into `iptv/`: `free.m3u` (an `#EXTINF` line and its stream for
  every tile, `tvg-id` = the `ukx:` id, in the household's section order and numbered by section, Entertainment from
  1001, Films from 2001 and so on, so a channel coming or going renumbers only its own section; no `#EXTM3U`
  header), and `channels.xml` and `programmes.xml` (XMLTV `<channel>` and `<programme>` elements, every programme
  that hasn't ended, up to 48 hours ahead, with each guide's synopsis and picture, no `<tv>` around them). The
  household's TiviMate playlist and guide (a Worker of their own, apart from the Nuvio add-ons) splice these in
  after their own channels. Added in a1d34d8, which went out under the Netflix rename's commit message.

Streams go through Matt Huisman's `jmp2.uk` redirects, the same ones his playlists use.

## Netflix rows

`build_netflix.py` reads Netflix's own files (`all-weeks-countries.tsv` for the GB rows, `most-popular.tsv`)
and matches each title on IMDb's search suggestions: same title, same kind, already released, and the most popular
of those on IMDb that week. `netflix_matches.txt` shows how each title was matched.
If one is wrong or missing, add it to `netflix_overrides.json` (`null` leaves a title out).

## Anime lists

`build_anime.py` builds anime by genre and by decade from MyAnimeList via [Tenrai](https://tenrai.org) (a
Jikan-style MAL API), with ids from [Fribb/anime-lists](https://github.com/Fribb/anime-lists). The household add-on
serves them as catalogues; this add-on's manifest doesn't list them yet. It:

- reads Tenrai's SFW anime with 1,000+ MAL members once a week, most members first (`sfw=true&min_members=1000`,
  about 130 pages of 100), one request a second (half Tenrai's public limit) as
  `uk-extras anime lists (github.com/Barticom94/uk-extras)`. A 429 waits for its `Retry-After`; a 5xx or timeout is
  tried again after 5, 15 and 45 s, then the run fails. Tenrai's terms (tenrai.org/terms, 4 July 2026) allow caching
  and transforming its answers for private use, so only tiles and lists are kept here: no scores, members or synopses;
- leaves out music videos, adverts and promos (MAL types Music, CM, PV), titles not aired yet, MAL's adult genres and
  Rx rating (Tenrai's SFW filter drops them already) and the few titles whose names hold a word the household keeps
  out of public text, and MAL specials (Special, TV Special) with no IMDb id: recaps and extras that would sit beside
  the show (AIOMetadata's MAL lists leave out every special). The SFW filter also drops MAL's R+ rating: 1,071 titles
  with 1,000+ members on 30 Oct 2026, Akira, Monster, Perfect Blue and Code Geass's first season among them;
- gives each title Fribb's IMDb id where there is one, typed by its TMDB id (movie or tv; with none, a MOVIE is a film
  and the rest are series; a MOVIE, or a one-episode OVA, ONA or special, is a film when the IMDb id is its own), else
  `kitsu:<id>`, else `mal:<id>`. Seasons that share an IMDb id are one tile, with the name, poster and year of the
  season that has most members;
- puts a title in a genre when MAL gives it that genre, theme or demographic (76 of them, A to Z), and in the decade
  it started airing (1960s to 2020s). `all` holds every tile. Each list runs in MAL members order and holds a tile
  once, at its best season's place, so a later season can put a show in a later decade too;
- writes `public/anime/index.json` (`pageSize` 50, then `all`, `genres` and `decades`, each with `name`, `slug`,
  `count` and `pages`) and `public/anime/<slug>/<n>.json`: items 50n to 50n+49 of that list as `{"metas": [...]}`,
  each with `id`, `type`, `name`, `poster` (MAL's large picture), `releaseInfo` (the year) and MAL's `genres`;
- keeps last week's lists (exits 1, writes nothing) after a short crawl: under 12,000 entries or 99% of Tenrai's own
  count, under 4,500 tiles with an IMDb id (Fribb's file changed), an empty list, a decade under 20, all under 90% of
  last week's or a list under half of last week's.

`anime.yml` runs it when dispatched (GitHub's schedule doesn't fire here, see below), commits `public/anime` if it
changed and starts `free-channels.yml`, which deploys it with the rest. Dispatch it apart from `netflix.yml`: both push
to `main`. The first crawl, from a home line on 30 Oct 2026, took 151 s: 12,951 entries, which these rules make 8,473
tiles, 60% with an IMDb id (970 of the top 1,000).

## Run it locally

    python -I build_netflix.py          # writes public/catalog/... and netflix_matches.txt
    python -I build_anime.py out cache  # one Tenrai crawl into out/anime/ (default public/); cache/ keeps the downloads
    python -I build_channels.py _site   # copies public/ into _site and adds the free channels
    python -I validate.py _site         # follows Nuvio's URLs: every tile has its meta and streams
    python -I test_build.py             # offline checks: UK time, merging, genres
    python -I tools/check_streams.py _site 30   # silent playlist check, from a UK line only

On Windows the `:` in `ukx:` file names is written as `%3A` (NTFS can't hold `:`). GitHub Pages runs on Linux and
decodes Nuvio's `ukx%3Aabc.json` back to `ukx:abc.json`.

## The hourly schedule

GitHub has not run `free-channels.yml` on its schedule yet. Checked 29 Oct 16:31 UTC: the repo was created 12:04,
both workflows are `active` on the default branch `main`, Actions are enabled with all actions allowed, the
`github-pages` environment allows `main`, and push and manual runs all succeeded, yet no `schedule` run exists for
`7 * * * *` (13:07, 14:07) or `17 * * * *` (15:17 and 16:17, set at 14:44). The same account's schedules do run in two
other repos (a weekly one up to 90 minutes late; a daily one first ran 8 hours after its workflow was added). So
nothing in this repo is set wrong that we can see: GitHub hasn't started the schedule for a new repo yet, and its
docs say scheduled runs "can be delayed" under load and may be dropped. Nothing here can make it fire. What doesn't
depend on it:

- the hourly files above keep now and next right for 6 to 14 hours after the last build;
- the household add-on's hourly cron can start this workflow through GitHub's API (`workflow_dispatch`, which works)
  once it holds a fine-grained token for this repo with Actions: read and write, and `netflix.yml` on Wednesdays and
  Fridays at 10:07 UTC (that schedule hasn't fired either, so the Netflix rows only change when it runs);
- by hand: `gh workflow run free-channels.yml -R Barticom94/uk-extras`.
