# UK Extras

A small static Stremio add-on for Nuvio, served from GitHub Pages:

    https://barticom94.github.io/uk-extras/manifest.json

| Catalogue | Type | Id | Rebuilt |
|---|---|---|---|
| Netflix UK Top 10 Shows | series | `ukx.netflix-top10-shows` | weekly |
| Netflix UK Top 10 Films | movie | `ukx.netflix-top10-films` | weekly |
| Netflix Most Popular Films | movie | `ukx.netflix-popular` | weekly |
| Free UK Channels | tv | `ukx.free` (genre: News, Entertainment, Movies, Kids, Sport, Documentary, Music, Lifestyle) | hourly |

Every catalogue has `showInHome: false`: they are meant for collection folders, not the home screen.
Netflix items are IMDb ids, so your metadata and stream add-ons open and play them. Free channels use `ukx:` ids,
and this add-on serves their meta and streams.

## Free channels

`build_channels.py` reads the GB channel lists and guides from [i.mjh.nz](https://i.mjh.nz/) for Samsung TV Plus,
Pluto TV and Plex (`<service>/.channels.json.gz` and `<service>/gb.xml.gz`). It:

- merges a channel that is on more than one service and keeps every copy as a stream, best first:
  Samsung TV Plus, then Pluto TV, then Plex (tested from a UK line on 29 Oct 2026: Samsung 119 of 120 and Pluto 76 of 77
  playlists answered; Plex answered too but rate-limits bursts with HTTP 429);
- drops channels that need DRM (Nuvio can't play them), adult channels and channels for other languages' markets;
- puts "Now:" and "Next:" (UK time) at the top of each description;
- sorts each genre in Samsung's and Pluto's own channel order, then Plex alphabetically.

Streams go through Matt Huisman's `jmp2.uk` redirects, the same ones his playlists use.

## Netflix rows

`build_netflix.py` reads Netflix's own files (`all-weeks-countries.tsv` for the GB rows, `most-popular.tsv`)
and matches each title on IMDb's search suggestions: same title, same kind, already released, and the most popular
of those on IMDb that week. `netflix_matches.txt` shows how each title was matched.
If one is wrong or missing, add it to `netflix_overrides.json` (`null` leaves a title out).

## Run it locally

    python -I build_netflix.py          # writes public/catalog/... and netflix_matches.txt
    python -I build_channels.py _site   # copies public/ into _site and adds the free channels
    python -I validate.py _site         # follows Nuvio's URLs: every tile has its meta and streams
    python -I test_build.py             # offline checks: UK time, merging, genres
    python -I tools/check_streams.py _site 30   # silent playlist check, from a UK line only

On Windows the `:` in `ukx:` file names is written as `%3A` (NTFS can't hold `:`). GitHub Pages runs on Linux and
decodes Nuvio's `ukx%3Aabc.json` back to `ukx:abc.json`.
