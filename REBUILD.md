# Rebuilding *Coffee Last*

Enough to reproduce the project from nothing, for an LLM with a shell and no other context.

---

## 1. What is being built

A single page arguing one claim: **the American restaurant menu has a grammar — a strict vertical
order of dishes — and that order can be recovered statistically from data nobody collected on
purpose.**

The New York Public Library ran a crowdsourcing project, *What's on the Menu?*, from 2011 to 2019.
Volunteers transcribed dishes off scanned restaurant menus. The transcription interface recorded
**where on the page image the volunteer clicked** — `MenuItem.xpos` and `MenuItem.ypos`,
normalised to 0–1. Every one of the 1,335,245 transcribed dish appearances carries a pair. That
column is the whole project. It was a by-product of the interface, not a research output, and as
far as I can tell nobody has used it for this.

Sort one page's dishes by `ypos` and you recover the order they were printed in, which on a menu is
the order they were meant to be eaten in. Do it across the collection, treat every within-page pair
as a contest ("was A printed above B?"), and fit a Bradley–Terry model. Out comes a single ranking
of 1,276 dishes that reads as an actual bill of fare: named oysters, soup, fish, game, the roast,
vegetables, salad, pastry, ices, cheese, coffee.

The finding that carries the page is not that a ranking can be fitted — one always can — but that
**it deserves to exist**. The relation "printed above" is very nearly a total order, and the page
proves it three independent ways (§3 below).

---

## 2. Data

One source. Four CSVs.

```
https://archive.org/download/nypl-whats-on-the-menu-data/Dish.csv         27,401,253 B
https://archive.org/download/nypl-whats-on-the-menu-data/Menu.csv          3,252,511 B
https://archive.org/download/nypl-whats-on-the-menu-data/MenuPage.csv      4,737,939 B
https://archive.org/download/nypl-whats-on-the-menu-data/MenuItem.csv    120,026,696 B
```

Item page: <https://archive.org/details/nypl-whats-on-the-menu-data>. Public Domain Mark 1.0,
uploaded 2024-01-23 by josh.hadro@gmail.com — Josh Hadro ran NYPL Labs, which is the provenance
that makes this trustworthy. **`menus.nypl.org` is dead and so is the old
`s3.amazonaws.com/menusdata.nypl.org/gzips/…` path**; do not waste time on them, both 404.

`src/fetch.py` downloads all four and refuses anything less than half the expected size.

### Quirks that will bite

- **`Dish.first_appeared` and `Dish.last_appeared` are unusable.** They contain years `1` and
  `2928`. Every date in this project is derived from `Menu.date` on the menu the dish was printed
  on. If your date range starts at year 1, you used the wrong column.
- **`Menu.date` is sometimes junk too.** There are dates in `0190`, `1090` and `2920`. Accept only
  `1840 ≤ year ≤ 2015`; 16,959 of 17,550 menus survive.
- **`Menu.language` is empty for every row.** Do not build anything on it.
- **`Menu.currency` is blank for 11,094 menus** and `"Dollars"` for 5,549. Prices are only computed
  for menus where currency is blank or `Dollars`; the rest include Deutsche Marks, Francs and
  Swedish kronor and would silently poison a price series.
- **Only 26,607 of the 66,937 `MenuPage` rows carry any items.** The rest are covers, blanks and
  backs. `len(MenuPage)` is not your page count.
- **`MenuItem.price` is often empty** — 889,068 of 1,335,245 rows have one.
- The CSVs need `csv.field_size_limit` raised; `Menu.notes` contains very long free text.

---

## 3. Processing, and why

### Which pages count

A page is usable when it has **≥10 items**, its menu has a **valid date**, and it is **not
multi-column**.

Multi-column detection matters and is the one judgement call worth arguing about. A two-column card
reads down-then-across, so `ypos` is *not* reading order on it, and including such pages scrambles
the signal. Detection: sort the page's x values, find the largest gap between consecutive values;
if that gap is > 0.15 and falls between x = 0.25 and 0.75, and both sides have ≥4 items spanning
> 0.35 of the vertical range, call it multi-column. **Drop those pages, do not try to fix them** —
guessing the column break wrong silently reverses the order of half the card, which is worse than
losing the page. This removes 1,827 pages (8.1% of pages with 10+ items).

Result: **20,848 usable pages, 1,121,371 items.**

### Name normalisation

Deliberately conservative: NFKD, strip combining marks, lowercase, collapse `[\s._-]+` to a single
space, trim leading/trailing non-alphanumerics. **Do not merge spellings beyond that.** "Blue
Points", "Bluepoints" and "Blue Point Oysters" stay three dishes. This is honest — they are three
strings on the menus — and it buys a free validity check: they land within half a point of each
other in the fit, which they could not do by accident.

### The fit

Dishes appearing on **≥100 usable pages** (1,276 of them) get a fitted strength. For every usable
page, every unordered pair of distinct dishes on it is one observation of "the higher one was
printed above the lower one". That is **474,958 distinct pairs over 10,019,137 observations**.

Bradley–Terry by Newton steps on pairs seen **≥8 times** (229,045 pairs), damped to ±0.5 per step,
centred on the mean at the end. Converges in ~225 iterations.

### The three rigidity tests

These are the point of the page; get them right.

1. **Transitivity.** Take pairs seen ≥15 times and decided at ≥9:1 (99,290 of them). Sample
   triples A→B→C and check A→C. Report consistency. A cycle (C→A) counts as a violation.
2. **Pair accuracy.** Does the single fitted order call each pair's direction correctly? Report
   both raw and observation-weighted.
3. **Per-page Kendall τ**, and *this is the one that matters* — it is the only test the fit cannot
   pass by construction. For each page with ≥6 ranked dishes and ≥10 comparable pairs, correlate
   the printed order with the fitted order. **Run the identical computation against a random
   permutation of the same dishes as a control**, and publish both. Without the control the number
   is meaningless.

   **Reseed the RNG immediately before building the shuffled order.** In an early build the shuffle
   was drawn from whatever RNG state the triple sampling happened to leave behind, so the published
   control figure wobbled between runs (0.000, 0.015, −0.029) with no code change. Deterministic
   inputs, deterministic outputs.

### Position over time

Absolute `ypos` is not comparable across eras — a 60-dish liner card and a 12-dish diner card use
the page differently. Use **fractional rank**: a dish's index among the distinct dishes on its
page, divided by (count − 1), on pages with ≥8 dishes. 0 is the top line, 1 the bottom.

**The trap here, and it is a real one.** The collection's meal-type mix changes over time — the
early menus skew dinner, the later ones are mostly untyped. So "grapefruit moved up the card" could
be nothing but "later cards are breakfast cards". Two defences, and the page needs both:

- Check the shift **holds within a single `Menu.event` bucket**. It does: grapefruit runs 0.76 →
  0.15 within the `other` bucket alone, on n = 123/211.
- Carry an **internal control group** — celery, olives, radishes, lettuce salad, stewed prunes.
  These are among the most-printed items in the collection and they do not move (all five within
  ±0.02 across the same era split). If page composition were driving the movers, the control would
  drift with them. This is the single most persuasive element in §5 and it must be on the page.

Restricting to dinner-only pages in *both* eras is tempting but leaves only 7 comparable dishes —
too few. Say so rather than pretending the control is tighter than it is.

### The pair table shipped to the page

Keys in the pair counter are ordered by the **dish string**; the page looks pairs up by **rank
index**. Normalise to (lower index, higher index) and flip the win count with it. Getting this
wrong silently reverses individual verdicts and is invisible unless you check a pair whose answer
you already know. The builder asserts on one: **Blue Points above Coffee must come back as 457 of
457.** Keep that assert.

---

## 4. The page

Fragment-shaped (no doctype — `wrap_for_pages.py` supplies it), one big JSON payload spliced at
`__DATA__` by `src/inject.py`, which also runs `wrap_for_pages.py` and `add_catalog_link.py`.

Identity: card stock and letterpress. Cream `#F6F1E4`, ink `#171310`, and a **two-ended colour
scale that is the page's main visual idea** — oyster teal `#2F6B7A` for the top of the card,
coffee brown `#8A4A1E` for the foot. A dish's colour is a function of its fitted strength, so it
keeps the same colour everywhere it appears: in the reconstructed card, in the duel, in a real
menu. Interpolate in JS by reading the CSS custom properties and recompute on theme change — do
not use `color-mix()` here, these values go into SVG `fill` attributes.

Sections:

1. **The reconstructed bill of fare.** 194 hand-picked lines out of the 1,276, rendered as a menu
   card with course bands. *Which* lines appear is a curated choice (one spelling per dish, spread
   across the whole range) held in `src/card_keys.txt`; *where* they appear is the fit's, untouched.
   The page must say this. Automatic near-duplicate merging was tried first and read badly —
   it produced a card that was 80% oysters and never reached the coffee.
   Clicking a line shows its page count, strength, median place, and the dishes it is hardest and
   easiest to separate from.
2. **The duel.** Any two of 1,276 dishes; shows the observed split and the count, falling back to
   the fit's prediction when fewer than 15 cards carry both.
3. **Rigidity.** The τ histogram against the shuffled control.
4. **Five real cards**, drawn at their transcribed (x, y), ink coloured by global fitted rank, each
   linking to its NYPL scan. This is the most persuasive figure on the page: every card bleeds
   cleanly from teal to brown top to bottom. **Draw them from coordinates; do not hotlink the
   scans.**
5. **What moved** — slope chart with the control group, plus per-decade tracks.
6. **The named beds.**
7. **Prices.**
8. Method and limits.

Course band labels are cut on **fitted strength**, not rank, so they survive a change to the card.
They are my labels, not the data's, and the page says so. Cheese and the plain cup of coffee
genuinely interleave over a full point of strength and no cut separates them — the band is named
"Cheese, crackers — and the coffee" rather than faking a clean boundary.

---

## 5. Verification table

Rebuild and check against these. Anything materially off means a parse or filter went wrong.

| Quantity | Expected |
|---|---|
| Menus / pages / items in source | 17,550 / 66,937 / 1,335,245 |
| Pages carrying ≥1 item | 26,607 |
| Distinct dish names | 431,041 raw, 380,429 after normalising |
| Menus with a usable date | 16,959, spanning 1851–2015 |
| Multi-column pages dropped | 1,827 |
| **Usable pages / items** | **20,848 / 1,121,371** |
| Dishes on ≥100 usable pages | 1,276 |
| Distinct co-occurring pairs / observations | 474,958 / 10,019,137 |
| Pairs entering the fit (n ≥ 8) | 229,045 |
| Pair accuracy, raw / obs-weighted | 86.0% / 88.5% |
| Triples sampled / violations / consistency | 1,172,949 / ~12,650 / **98.9%** |
| Pages scored for τ | 15,425 |
| Median τ, fitted / shuffled | **0.662 / ~0.0** |
| Pages with τ > 0.8 / τ < 0 | 22.0% / 5.6% |
| **Blue Points printed above Coffee** | **457 of 457 — no exceptions** |
| Coffee vs Tea | ~50/50 across 3,680 shared cards |
| Coffee's median place, dinner pages ≥8 dishes | **1.000**, last outright on 931 of 1,790 |
| Top of the fitted order | Bluepoints, Cape Cods, Grape Fruit Cocktail, Cotuits, Lynnhavens |
| Bottom of the fitted order | Johannis, Bread or Rolls and Butter, French Coffee, Turkish Coffee |
| Grapefruit, 1880–1915 → 1930–2000 | 0.76 → 0.15 (two-word "grape fruit": 0.76 → 0.07) |
| Port / Sherry / Sliced tomatoes | 0.36 → 0.73 / 0.24 → 0.58 / 0.21 → 0.56 |
| Control: celery / olives / radishes | 0.13 → 0.11 / 0.13 → 0.15 / 0.14 → 0.14 |
| Named beds per 100 dated menus, 1910s → 1980s | ~124 → 6.5, zero in the 1990s |
| Demi-tasse median price, 1890s–1940s | $0.15 in all six decades |
| Celery vs coffee median price, 1900s | $0.30 vs $0.10 |
| Payload / page size | ~2.4 MB / ~2.45 MB |

Recognisable sanity checks beyond the numbers: the fitted order should put **Rockaways, Cotuits and
Lynnhavens within a point of each other at the very top**, **terrapin and canvas back duck in the
game band**, and **cigars below coffee**. If salads come out above soup, `ypos` has been inverted.

---

## 6. What the page must say about itself

Non-negotiable, all present in §8 of the page:

- **The collection is not America.** It is the Buttolph collection and its successors: heavily New
  York, heavily hotel and transatlantic liner. The Waldorf Astoria alone supplies ~4.7% of usable
  pages; Norddeutscher Lloyd, Hotel Astor, Hamburg-Amerika and Red Star Line are next. It peaks
  hard in the 1900s–1910s and thins to a trickle after 1960. Every claim is a claim about what this
  collection holds.
- **The rigidity result survives that bias; the dated trends are weaker.** τ is measured *within*
  pages, so a biased sample of cards is still a sample of cards. Time series across a collection
  whose composition changes are a different matter, which is why §5 leans on the control group.
- **Spelling is not merged**, and why that is deliberate.
- **The course labels are mine**, the order is the data's.
- **"Coffee last" is a median, not a law** — and the exact, narrower claim that *is* exceptionless
  is the Blue Points one.
- **Multi-column pages were dropped, not fixed.**
- **`first_appeared`/`last_appeared` are unusable**, so all dates come from the menu.

---

## 7. Running it

```bash
python src/fetch.py           # ~155 MB into src/raw/, skips files already there
python src/build_payload.py   # ~3 min, ~1 GB RAM -> src/payload.json
python src/inject.py          # -> index.html, wrapped and catalog-linked
```

`python src/build_payload.py --dump-order` writes `src/order_dump.txt`, the full 1,276-line fitted
order — the thing to read first if a number looks wrong, and what `card_keys.txt` was picked from.

Raw CSVs and `payload.json` are gitignored; the scripts refetch and regenerate them.
