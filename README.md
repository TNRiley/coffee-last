# ☕ Coffee Last

**Volunteers transcribing 45,000 old restaurant menus left behind the spot on the page they clicked. Sorted by that one number, the American bill of fare turns out to be a single order that almost nobody broke.**

→ **[Open it](https://tnriley.github.io/coffee-last/)**

The New York Public Library's menu collection, transcribed dish by dish between 2011 and 2019, recorded an (x, y) click position for every one of its 1,335,245 dish appearances. Sort a page by the y and the courses fall out in sequence, though no volunteer ever labelled a course. Treat every within-page pair as a contest — was the celery printed above the Camembert? — and fit the 10 million resulting contests the way you would rank chess players, and 1,276 dishes collapse onto one line: raw oysters named by the bed they came from, then soup, fish, game, the roast, vegetables, salad, pastry, ices, cheese, and coffee. It is one order, not many: across 1.17 million sampled triples, "printed above" is transitive 98.9% of the time, a single ranking calls 88.5% of well-observed pairs correctly, and the median real menu page correlates with it at 0.66 against 0.02 for a shuffled control. Blue Points beat coffee on all 457 cards carrying both, without one exception. The order is rigid but not frozen — grapefruit walked from 0.76 down the card to 0.15, dessert fruit to opening course, while sherry and port went the other way and the relish trio of celery, olives and radishes never moved at all. Includes the reconstructed bill of fare, a head-to-head oracle over any two of the 1,276 dishes, and five real cards redrawn at the coordinates they were transcribed at.

## Running it

One self-contained HTML file. No build step, no server, no network access at runtime — open `index.html` in a browser, or serve the directory with any static host.

```bash
python3 -m http.server 8000   # then visit http://localhost:8000
```

## Rebuilding it from scratch

[REBUILD.md](REBUILD.md) is written for an LLM with a shell and nothing else: the data sources and their quirks, the processing decisions, the page's structure and interactions, and a table of expected values to check the result against.

## Source

The full build pipeline is in [`src/`](src/), with a README describing how to regenerate the page from scratch.

## Data

- **[NYPL "What's on the Menu?" final data export, 1 December 2022 - 17,550 menus, 66,937 pages, 431,041 dish names and 1,335,245 dish appearances with prices and normalised (x, y) click positions. The project site has been retired; this export survives as an Internet Archive item uploaded by Josh Hadro, who ran NYPL Labs.](https://archive.org/details/nypl-whats-on-the-menu-data)** — Public Domain Mark 1.0
- **[NYPL Digital Collections - the page scans themselves, linked per card by catalogue uuid. No image is copied or hotlinked; every menu drawn on the page is rendered from the transcribed coordinates.](https://digitalcollections.nypl.org/)** — Linked, not redistributed

Every figure on the page is computed from the data shipped with it. Check the page's own methods panel for how each number is derived and where it should not be pushed.

## Built with

vanilla JS, inline SVG, Bradley-Terry fit in pure Python.

## Licence

Code is MIT (see [LICENSE](LICENSE)). Data keeps the licence of its source, listed above.

---

Part of [Quick Projects](https://github.com/TNRiley/quick-projects) — one self-contained thing, built in one session. First published 2026-09-27.
