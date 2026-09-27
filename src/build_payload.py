#!/usr/bin/env python
"""Turn 1.3 million menu-transcription click positions into payload.json.

The whole project rests on one column nobody was trying to publish. When a
volunteer transcribed a dish on a scanned menu, the site recorded where on the
page image they clicked: MenuItem.xpos and MenuItem.ypos, normalised to 0-1.
Every one of the 1,335,245 items has a pair. Sort a page's items by ypos and you
get the order the dishes were printed in, which on a menu is the order they were
meant to be eaten in. Nobody labelled a single course; the order is a by-product
of the transcription interface.

What this script computes, in order:

  1. usable pages    single-column, dated, at least 10 items. Multi-column pages
                     break the "ypos is reading order" assumption and are dropped
                     (8.1% of pages with 10+ items).
  2. Bradley-Terry   every within-page pair "A printed above B" is a match.
                     Fit one strength per dish, so the whole library collapses
                     onto a single line: the canonical American bill of fare.
  3. rigidity        does one line really explain it? Triple consistency of the
                     decided pairs, pair accuracy of the fitted order, and the
                     per-page Kendall tau against a shuffled order as a control.
  4. movers          median fractional rank per decade, so positions from a
                     60-dish card and a 12-dish card are comparable. The relish
                     trio (celery, olives, radishes) is the internal control:
                     if page composition were driving the movers, it would move
                     too, and it does not.
  5. beds            named oyster and clam beds, per 100 dated menus by decade.
  6. prices          median nominal price by decade, USD menus only.
  7. ghosts          a handful of real pages, kept as true (x, y) coordinates so
                     the page can redraw the card itself.

Run fetch.py first. Takes a couple of minutes and about 1 GB of RAM.
"""
import collections
import csv
import io
import json
import math
import os
import random
import re
import statistics
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
OUT = os.path.join(HERE, "payload.json")

csv.field_size_limit(min(2 ** 31 - 1, sys.maxsize))

# ---------------------------------------------------------------- parameters
MIN_ITEMS = 10          # a page needs this many items to carry an order
MIN_PAGES_RANKED = 100  # a dish needs this many pages to earn a fitted strength
MIN_PAIR_BT = 8         # pair observations before it informs the fit
MIN_PAIR_SHOW = 15      # pair observations before the page will quote it
MIN_TAU_PAIRS = 10      # comparable pairs before a page gets a tau
YEAR_LO, YEAR_HI = 1840, 2015
EARLY = (1880, 1915)
LATE = (1930, 2000)
DECADES = list(range(1880, 2010, 10))


def read(name):
    with io.open(os.path.join(RAW, name), encoding="utf-8", newline="") as fh:
        r = csv.reader(fh)
        head = next(r)
        for row in r:
            row = (row + [""] * len(head))[: len(head)]
            yield dict(zip(head, row))


def key(name):
    """Fold spelling noise: accents, case, punctuation, runs of whitespace.

    Deliberately conservative. 'blue points' and 'bluepoints' stay separate
    dishes here, which is honest - they are separate strings on the menus - and
    the display menu merges them later for readability only.
    """
    s = unicodedata.normalize("NFKD", name or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower().strip()
    s = re.sub(r"[\s._\-]+", " ", s)
    s = re.sub(r"^[^a-z0-9]+|[^a-z0-9)]+$", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ 1. load
print("loading")
dishkey = {}
dishname = {}
for d in read("Dish.csv"):
    k = key(d["name"])
    dishkey[d["id"]] = k
    if k and k not in dishname:
        dishname[k] = (d["name"] or "").strip()

year, sponsor, place, event, currency, mealtype, mdate = {}, {}, {}, {}, {}, {}, {}
for m in read("Menu.csv"):
    dt = m["date"] or ""
    mdate[m["id"]] = dt
    if len(dt) >= 4 and dt[:4].isdigit():
        y = int(dt[:4])
        if YEAR_LO <= y <= YEAR_HI:
            year[m["id"]] = y
    sponsor[m["id"]] = (m["sponsor"] or "").strip()
    place[m["id"]] = (m["place"] or "").strip()
    event[m["id"]] = (m["event"] or "").strip()
    currency[m["id"]] = m["currency"] or ""
    e = (m["event"] or "").upper()
    mealtype[m["id"]] = ("breakfast" if "BREAKFAST" in e else
                         "lunch" if ("LUNCH" in e or "DEJEUNER" in e) else
                         "dinner" if ("DINNER" in e or "DINER" in e or "SUPPER" in e) else
                         "other")

pmenu, puuid, pno = {}, {}, {}
for p in read("MenuPage.csv"):
    pmenu[p["id"]] = p["menu_id"]
    puuid[p["id"]] = p["uuid"]
    pno[p["id"]] = p["page_number"]

pages = collections.defaultdict(list)
n_items = 0
for it in read("MenuItem.csv"):
    if not it["xpos"] or not it["ypos"]:
        continue
    n_items += 1
    try:
        x = float(it["xpos"]); y = float(it["ypos"])
    except ValueError:
        continue
    pages[it["menu_page_id"]].append((x, y, it["dish_id"], it["price"]))
print("  %d menus, %d pages, %d items" % (len(pmenu), len(pages), n_items))


def multicolumn(v):
    """Two columns of dishes read down-then-across, so ypos is not reading order.

    Detected as a wide horizontal gap near the middle with both sides spanning
    most of the page's vertical extent. Those pages are discarded, not fixed:
    guessing the column break wrong would silently scramble the order.
    """
    xs = sorted(p[0] for p in v)
    if len(xs) < MIN_ITEMS:
        return False
    gap, at = max((xs[i + 1] - xs[i], xs[i]) for i in range(len(xs) - 1))
    if gap > 0.15 and 0.25 < at < 0.75:
        left = [p[1] for p in v if p[0] <= at]
        right = [p[1] for p in v if p[0] > at]
        if (len(left) >= 4 and len(right) >= 4
                and max(left) - min(left) > 0.35 and max(right) - min(right) > 0.35):
            return True
    return False


usable, dropped_multi = {}, 0
for pid, v in pages.items():
    mid = pmenu.get(pid)
    if mid not in year or len(v) < MIN_ITEMS:
        continue
    if multicolumn(v):
        dropped_multi += 1
        continue
    usable[pid] = (year[mid], sorted(v, key=lambda p: p[1]))
usable_items = sum(len(v[1]) for v in usable.values())
print("  usable: %d pages, %d items (%d multi-column pages dropped)"
      % (len(usable), usable_items, dropped_multi))

# per-page ordered list of distinct dish keys, first appearance wins
pagekeys = {}
pagecount = collections.Counter()
for pid, (y, v) in usable.items():
    seen, ordered = set(), []
    for _, _, did, _ in v:
        k = dishkey.get(did, "")
        if k and k not in seen:
            seen.add(k); ordered.append(k)
    pagekeys[pid] = ordered
    for k in seen:
        pagecount[k] += 1

RANKED = set(k for k, n in pagecount.items() if n >= MIN_PAGES_RANKED)
print("  dishes on >=%d pages: %d" % (MIN_PAGES_RANKED, len(RANKED)))

# ------------------------------------------------- 2. pairwise + Bradley-Terry
print("pairing")
W, N = collections.Counter(), collections.Counter()
for pid, ordered in pagekeys.items():
    ks = [k for k in ordered if k in RANKED]
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            a, b = ks[i], ks[j]          # i is above j on the page
            if a < b:
                N[(a, b)] += 1; W[(a, b)] += 1
            else:
                N[(b, a)] += 1
print("  %d co-occurring pairs, %d observations" % (len(N), sum(N.values())))

fitpairs = [(p, W[p], n) for p, n in N.items() if n >= MIN_PAIR_BT]
nodes = sorted({d for p, _, _ in fitpairs for d in p})
print("  fitting %d dishes on %d pairs" % (len(nodes), len(fitpairs)))
th = {d: 0.0 for d in nodes}
for step in range(500):
    num = collections.defaultdict(float)
    den = collections.defaultdict(float)
    for (a, b), w, n in fitpairs:
        pa = 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, th[a] - th[b]))))
        g = w - n * pa
        num[a] += g; num[b] -= g
        h = n * pa * (1.0 - pa) + 1e-9
        den[a] += h; den[b] += h
    worst = 0.0
    for d in nodes:
        dl = max(-0.5, min(0.5, num[d] / den[d]))
        th[d] += dl
        worst = max(worst, abs(dl))
    if worst < 1e-6:
        break
mean = sum(th.values()) / len(th)
th = {d: v - mean for d, v in th.items()}
print("  converged in %d iterations" % (step + 1))

ok = tot = wok = wtot = 0
for (a, b), w, n in fitpairs:
    if (th[a] > th[b]) == (w / n > 0.5):
        ok += 1; wok += n
    tot += 1; wtot += n
pair_acc, pair_accw = 100.0 * ok / tot, 100.0 * wok / wtot
print("  pair accuracy %.1f%%, observation-weighted %.1f%%" % (pair_acc, pair_accw))

# ------------------------------------------------------------- 3. rigidity
print("rigidity")
decided = {}
for (a, b), n in N.items():
    if n < MIN_PAIR_SHOW:
        continue
    r = W[(a, b)] / n
    if r > 0.9:
        decided[(a, b)] = True
    elif r < 0.1:
        decided[(a, b)] = False
above = collections.defaultdict(set)
for (a, b), a_first in decided.items():
    (above[a] if a_first else above[b]).add(b if a_first else a)
random.seed(7)
heads = [k for k in above if above[k]]
triples = violations = 0
for _ in range(4_000_000):
    a = random.choice(heads)
    b = random.choice(tuple(above[a]))
    if not above[b]:
        continue
    cc = random.choice(tuple(above[b]))
    if cc == a:                     # a>b>c>a is a cycle: a violation by itself
        triples += 1; violations += 1; continue
    p = (a, cc) if a < cc else (cc, a)
    if p in decided:
        triples += 1
        if decided[p] != (p[0] == a):
            violations += 1
consistency = 100.0 * (1 - violations / max(triples, 1))
print("  %d triples, %d violations, %.3f%% consistent" % (triples, violations, consistency))

# Reseeded so the shuffled control does not depend on how much randomness the
# triple sampling above happened to consume, which made the published figure
# wobble between runs.
random.seed(11)
shuf = {k: random.random() for k in th}
BINS = [-1 + i * 0.1 for i in range(21)]


def tau(order_of, ks):
    conc = disc = 0
    for i in range(len(ks)):
        for j in range(i + 1, len(ks)):
            a, b = ks[i], ks[j]       # i above j on the page
            if order_of[a] == order_of[b]:
                continue
            if order_of[a] > order_of[b]:
                conc += 1
            else:
                disc += 1
    return (conc - disc) / (conc + disc) if conc + disc >= MIN_TAU_PAIRS else None


taus, rtaus, page_tau = [], [], {}
for pid, ordered in pagekeys.items():
    ks = [k for k in ordered if k in th]
    if len(ks) < 6:
        continue
    t = tau(th, ks)
    if t is None:
        continue
    taus.append(t); page_tau[pid] = t
    rt = tau(shuf, ks)
    if rt is not None:
        rtaus.append(rt)


def hist(vals):
    h = [0] * 20
    for v in vals:
        h[min(19, max(0, int((v + 1) / 0.1)))] += 1
    return h


taus.sort(); rtaus.sort()
print("  %d pages scored, median tau %.3f (shuffled %.3f)"
      % (len(taus), taus[len(taus) // 2], rtaus[len(rtaus) // 2]))

# ------------------------------------------------------- 4. fractional ranks
print("positions")
frac = collections.defaultdict(list)     # key -> [(year, fractional rank)]
for pid, (y, _) in usable.items():
    ks = pagekeys[pid]
    if len(ks) < 8:
        continue
    last = len(ks) - 1
    for i, k in enumerate(ks):
        frac[k].append((y, i / last))

med_frac = {k: statistics.median([f for _, f in v]) for k, v in frac.items() if len(v) >= 20}


def decade_series(k, floor=12):
    by = collections.defaultdict(list)
    for y, f in frac.get(k, ()):
        by[y // 10 * 10].append(f)
    return [round(statistics.median(by[d]), 4) if len(by.get(d, ())) >= floor else None
            for d in DECADES], [len(by.get(d, ())) for d in DECADES]


movers = []
for k, obs in frac.items():
    e = [f for y, f in obs if EARLY[0] <= y <= EARLY[1]]
    l = [f for y, f in obs if LATE[0] <= y <= LATE[1]]
    if len(e) >= 40 and len(l) >= 40:
        movers.append({
            "k": k, "name": dishname.get(k, k),
            "early": round(statistics.median(e), 4), "late": round(statistics.median(l), 4),
            "ne": len(e), "nl": len(l),
            "d": round(statistics.median(l) - statistics.median(e), 4),
        })
movers.sort(key=lambda m: m["d"])
print("  %d dishes comparable %d-%d vs %d-%d" % (len(movers), *EARLY, *LATE))

# The control group, carried separately because it is defined by what it does NOT
# do and so never turns up in either tail of the movers list.
CONTROL = ["celery", "olives", "radishes", "lettuce salad", "stewed prunes"]
control = [m for m in movers if m["k"] in CONTROL]
for m in control:
    print("  control: %-16s %.2f -> %.2f (%+.3f)" % (m["k"], m["early"], m["late"], m["d"]))

FEATURED = ["grapefruit", "grape fruit", "sherry", "port", "sauterne",
            "sliced tomatoes", "welsh rarebit",
            "champagne", "hamburger steak", "celery", "olives", "radishes", "lettuce salad",
            "stewed prunes", "coffee", "demi tasse", "apple pie", "baked apple", "cantaloupe",
            "fresh fruit", "consomme", "oyster stew", "clam broth", "blue points",
            "little neck clams", "vanilla ice cream", "roquefort", "chicken salad"]
tracks = {}
for k in FEATURED:
    s, n = decade_series(k)
    if any(v is not None for v in s):
        tracks[k] = {"name": dishname.get(k, k), "s": s, "n": n,
                     "m": round(med_frac[k], 4) if k in med_frac else None}

# ---------------------------------------------------------- 5. named beds
menus_by_decade = collections.Counter()
for mid, y in year.items():
    menus_by_decade[y // 10 * 10] += 1

BEDS = ["blue points", "bluepoints", "blue point oysters", "blue points, half shell",
        "cotuits", "cotuit oysters", "lynnhavens", "lynnhaven oysters",
        "cape cods", "cape cod oysters", "rockaways", "buzzard bays", "saddle rocks",
        "shrewsburys", "little necks", "little neck clams", "little necks clams",
        "cherrystones", "cherry stones", "cherry stone clams", "cherrystone clams"]
pyear = {pid: year[mid] for pid, mid in pmenu.items() if mid in year}
bed_hits = collections.defaultdict(collections.Counter)
for pid, v in pages.items():
    y = pyear.get(pid)
    if y is None:
        continue
    for _, _, did, _ in v:
        k = dishkey.get(did, "")
        if k in BEDS:
            bed_hits[k][y // 10 * 10] += 1
bed_rows, bed_all = [], collections.Counter()
for k in BEDS:
    row = bed_hits.get(k)
    if not row or sum(row.values()) < 100:
        continue
    bed_rows.append({"name": dishname.get(k, k), "k": k,
                     "c": [row.get(d, 0) for d in DECADES], "tot": sum(row.values()),
                     "t": round(th[k], 3) if k in th else None})
    for d, n in row.items():
        bed_all[d] += n
bed_rows.sort(key=lambda r: -r["tot"])

# ------------------------------------------------------------- 6. prices
USD = set(mid for mid, cur in currency.items() if cur in ("", "Dollars"))
pser = collections.defaultdict(lambda: collections.defaultdict(list))
for pid, v in pages.items():
    mid = pmenu.get(pid)
    if mid not in USD or mid not in year:
        continue
    dec = year[mid] // 10 * 10
    for _, _, did, pr in v:
        if not pr:
            continue
        try:
            p = float(pr)
        except ValueError:
            continue
        if 0 < p < 200:
            pser[dishkey.get(did, "")][dec].append(p)

PRICED = ["coffee", "demi tasse", "celery", "apple pie", "milk", "vanilla ice cream",
          "blue points", "little neck clams", "chicken salad", "sirloin steak"]
prices = []
for k in PRICED:
    d = pser.get(k, {})
    med = [round(statistics.median(d[dec]), 3) if len(d.get(dec, ())) >= 15 else None
           for dec in DECADES]
    if any(v is not None for v in med):
        prices.append({"name": dishname.get(k, k), "k": k, "med": med,
                       "n": [len(d.get(dec, ())) for dec in DECADES]})

# -------------------------------------------------------- 7. the ghost pages
# A handful of real pages, kept as the coordinates they were transcribed at, so
# the page can redraw the card itself instead of hotlinking NYPL's scans. One per
# house, picked for a legible number of dishes and a high tau - these are the
# cases the fitted order gets right, and the page says so and links the scan.
GHOSTS = ["Delmonico", "Waldorf", "Hotel Astor", "CUNARD", "Healy", "Ambassador", "Biltmore"]
cand = []
for pid, (y, v) in usable.items():
    t = page_tau.get(pid)
    if t is None or t < 0.6 or not (16 <= len(v) <= 44):
        continue
    sp = sponsor.get(pmenu[pid], "")
    for g in GHOSTS:
        if g.lower() in sp.lower():
            cand.append((g, -t, -len(v), pid))
            break
cand.sort()
ghosts, used = [], set()
for g, negt, _, pid in cand:
    if g in used:
        continue
    mid = pmenu[pid]
    items = []
    for x, y2, did, pr in usable[pid][1]:
        k = dishkey.get(did, "")
        items.append({"x": round(x, 4), "y": round(y2, 4),
                      "n": dishname.get(k, "") or "?", "p": pr,
                      "r": round(th[k], 3) if k in th else None})
    ghosts.append({"sponsor": sponsor[mid], "place": place[mid], "event": event[mid],
                   "date": mdate.get(mid, ""), "year": usable[pid][0],
                   "page": pno.get(pid, ""), "uuid": puuid.get(pid, ""),
                   "tau": round(-negt, 3), "items": items})
    used.add(g)
for gh in ghosts:
    print("  ghost: %s %-34s %2d items, tau %.2f"
          % (gh["date"] or gh["year"], gh["sponsor"][:34], len(gh["items"]), gh["tau"]))

# --------------------------------------------------- the order, and the card
order = sorted(th.items(), key=lambda kv: -kv[1])
ORDER = [{"n": dishname.get(k, k), "k": k, "t": round(v, 3), "p": pagecount[k],
          "f": round(med_frac[k], 3) if k in med_frac else None} for k, v in order]

if "--dump-order" in sys.argv:
    with io.open(os.path.join(HERE, "order_dump.txt"), "w", encoding="utf-8", newline="\n") as fh:
        for i, e in enumerate(ORDER):
            fh.write("%4d %+6.2f %5d  %s\n" % (i, e["t"], e["p"], e["n"]))
    print("dumped %d" % len(ORDER))
    sys.exit(0)

# The printed card. Which lines appear is a choice - one spelling per dish, and a
# spread that covers the whole fitted line rather than 200 kinds of oyster. Where
# they appear is not a choice: the card is sorted by the fit, and nothing is
# nudged. Automatic near-duplicate merging was tried first and read badly, so
# these were picked off the fitted order by hand; see card_keys.txt.
exec(io.open(os.path.join(HERE, "card_keys.txt"), encoding="utf-8").read())

CARD = [e for e in ORDER if e["k"] in set(CARD_KEYS)]
missing = set(CARD_KEYS) - set(e["k"] for e in CARD)
if missing:
    print("  WARNING card keys no longer in the fit: %s" % ", ".join(sorted(missing)))
print("  card: %d lines of %d ranked dishes" % (len(CARD), len(ORDER)))

# Course bands, cut on fitted strength rather than on rank, so they stay put if
# the card changes. The order is the data's; these labels and cut points are
# mine, read off the fitted line afterwards, and the page says so. Two of them
# genuinely overlap - cheese and coffee share the foot of the menu - and the
# page says that too rather than pretending the courses are disjoint.
BANDS = [
    (4.20, 99, "Oysters and clams", "on the half shell, by the bed they came from"),
    (3.35, 4.20, "Cocktails, canapes, relishes", "caviar, olives, celery, salted almonds"),
    (2.60, 3.35, "Soup", "clear, thick, and in a cup"),
    (1.30, 2.60, "Fish, birds and game", "sole, terrapin, plover, canvas back duck"),
    (0.35, 1.30, "The roast, the steak, the chop", "and the vegetables beside it"),
    (-0.05, 0.35, "Vegetables and potatoes", "priced by the dish, ordered separately"),
    (-0.70, -0.05, "Salad", "lettuce, tomato, romaine, and a dressing"),
    (-1.60, -0.70, "Pastry, pie and pudding", "and the sherry and port that came with them"),
    (-2.55, -1.60, "Ices, cake and fruit", "tortoni, charlotte russe, grapes, figs"),
    # Cheese and the plain cup of coffee genuinely interleave over a full point
    # of strength, and no cut separates them. The label says so rather than
    # pretending otherwise.
    (-3.35, -2.55, "Cheese, crackers — and the coffee",
     "Roquefort and Camembert, printed among the cups"),
    (-99, -3.35, "Last of all", "the demi-tasse, the mineral water, the cigars"),
]
bands = []
for lo, hi, label, note in BANDS:
    members = [i for i, e in enumerate(CARD) if lo <= e["t"] < hi]
    if members:
        bands.append({"label": label, "note": note,
                      "from": members[0], "to": members[-1] + 1,
                      "lo": lo, "hi": hi})

# -------------------------------------------- the pair table, for the oracle
# Keys in N are ordered by the dish string; the page looks pairs up by rank index,
# so normalise to (lower index, higher index) here and flip the win count with it.
# Getting this wrong silently reverses individual verdicts, which is invisible
# unless you check a pair whose answer you already know: oysters beat coffee.
idx = {e["k"]: i for i, e in enumerate(ORDER)}
pairs_a, pairs_b, pairs_n, pairs_w = [], [], [], []
for (a, b), n in N.items():
    if n < MIN_PAIR_SHOW or a not in idx or b not in idx:
        continue
    ia, ib, w = idx[a], idx[b], W[(a, b)]
    if ia > ib:
        ia, ib, w = ib, ia, n - w
    pairs_a.append(ia); pairs_b.append(ib); pairs_n.append(n); pairs_w.append(w)
assert all(a < b for a, b in zip(pairs_a, pairs_b))
sanity = [(i, j, w, n) for i, j, w, n in zip(pairs_a, pairs_b, pairs_w, pairs_n)
          if ORDER[i]["k"] == "blue points" and ORDER[j]["k"] == "coffee"]
if sanity:
    i, j, w, n = sanity[0]
    print("  sanity: Blue Points above Coffee on %d of %d shared pages" % (w, n))
    assert w / n > 0.9, "the pair table is inverted"
print("  pair table: %d pairs" % len(pairs_a))

meal_counts = collections.Counter(mealtype[pmenu[pid]] for pid in usable)

# The title's claim, stated as narrowly as it can be: on dinner pages carrying at
# least eight dishes, where does the line reading "Coffee" sit?
coffee_dinner, coffee_dinner_last = [], 0
for pid in usable:
    ks = pagekeys[pid]
    if mealtype[pmenu[pid]] != "dinner" or len(ks) < 8 or "coffee" not in ks:
        continue
    f = ks.index("coffee") / (len(ks) - 1)
    coffee_dinner.append(f)
    if f == 1.0:
        coffee_dinner_last += 1

payload = {
    "coverage": {
        "menus": len(sponsor), "pages": len(pages), "items": n_items,
        "dishes": len(dishname), "datedMenus": len(year),
        "usablePages": len(usable), "usableItems": usable_items,
        "droppedMulti": dropped_multi,
        "yearLo": min(year.values()), "yearHi": max(year.values()),
        "mealCounts": dict(meal_counts),
        "sponsors": [list(t) for t in collections.Counter(
            sponsor[pmenu[pid]] for pid in usable if sponsor.get(pmenu[pid])).most_common(8)],
    },
    "rigidity": {
        "pairs": len(N), "pairObs": sum(N.values()), "fitPairs": len(fitpairs),
        "ranked": len(th), "pairAcc": round(pair_acc, 1), "pairAccW": round(pair_accw, 1),
        "triples": triples, "violations": violations, "consistency": round(consistency, 3),
        "decided": len(decided),
        "tauPages": len(taus), "tauMedian": round(taus[len(taus) // 2], 3),
        "tauMean": round(sum(taus) / len(taus), 3),
        "tauHigh": round(100 * sum(1 for t in taus if t > 0.8) / len(taus), 1),
        "tauNeg": round(100 * sum(1 for t in taus if t < 0) / len(taus), 2),
        "tauRandMedian": round(rtaus[len(rtaus) // 2], 3),
        "hist": hist(taus), "histRand": hist(rtaus), "bins": [round(b, 1) for b in BINS],
        "coffeeDinnerMedian": round(statistics.median(coffee_dinner), 3) if coffee_dinner else None,
        "coffeeDinnerN": len(coffee_dinner),
        "coffeeDinnerLast": coffee_dinner_last,
    },
    "order": ORDER,
    "card": [idx[e["k"]] for e in CARD],
    "bands": bands,
    "pairs": {"a": pairs_a, "b": pairs_b, "n": pairs_n, "w": pairs_w},
    "decades": DECADES,
    "movers": {"up": movers[:18], "down": movers[-18:], "control": control,
               "count": len(movers), "minPair": MIN_PAIR_SHOW},
    "tracks": tracks,
    "beds": {"rows": bed_rows, "all": [bed_all.get(d, 0) for d in DECADES],
             "menus": [menus_by_decade.get(d, 0) for d in DECADES]},
    "prices": prices,
    "ghosts": ghosts,
}

with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
    json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
print("payload.json  %.2f MB" % (os.path.getsize(OUT) / 1e6))
