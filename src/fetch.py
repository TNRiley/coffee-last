#!/usr/bin/env python
"""Download the NYPL 'What's on the Menu' final data export into src/raw/.

menus.nypl.org is gone. The project's last data export (2022-12-01) survives as
an Internet Archive item uploaded by Josh Hadro, who ran NYPL Labs, marked
Public Domain Mark 1.0. Those four CSVs are the whole dataset:

  Menu.csv      17,550 menus     date, sponsor, place, event, currency
  MenuPage.csv  66,937 pages     which menu, which page number, scan id + uuid
  MenuItem.csv  1,335,245 items  page, price, dish id, and an (xpos, ypos)
                                 click position normalised to the page image
  Dish.csv      431,041 names    the transcribed dish names

MenuItem.xpos/ypos is the reason this project exists, so do not drop it. The
first/last_appeared columns in Dish.csv are unusable (they contain years 1 and
2928); dates come from Menu.date instead.

Re-runnable: files already present and non-empty are left alone.
"""
import os
import sys
import urllib.request

BASE = "https://archive.org/download/nypl-whats-on-the-menu-data"
FILES = {
    "Dish.csv": 27_401_253,
    "Menu.csv": 3_252_511,
    "MenuPage.csv": 4_737_939,
    "MenuItem.csv": 120_026_696,
}
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")


def main():
    os.makedirs(RAW, exist_ok=True)
    for name, expect in FILES.items():
        dest = os.path.join(RAW, name)
        if os.path.exists(dest) and os.path.getsize(dest) > 0:
            print("have   %-14s %12d B" % (name, os.path.getsize(dest)))
            continue
        url = "%s/%s" % (BASE, name)
        print("fetch  %-14s %s" % (name, url))
        urllib.request.urlretrieve(url, dest)
        got = os.path.getsize(dest)
        print("       %-14s %12d B (expected about %d)" % (name, got, expect))
        if got < expect * 0.5:
            sys.exit("%s came back far too small - check the Archive item" % name)


if __name__ == "__main__":
    main()
