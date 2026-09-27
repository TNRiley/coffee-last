#!/usr/bin/env python
"""Splice payload.json into template.html and produce the finished index.html.

The last two steps matter: wrap_for_pages.py turns the Artifact-shaped fragment
into a standalone document (without it GitHub Pages serves the page in quirks
mode and renders UTF-8 as Latin-1, which mangles every en dash and the tau), and
add_catalog_link.py puts the breadcrumb back to the catalog on it. Regenerating
the page without them silently drops both, so they run from here.
"""
import os
import json
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
OUT = os.path.join(PROJ, "index.html")
MARK = "__DATA__"


def workspace_root(start):
    p = start
    while True:
        if os.path.isdir(os.path.join(p, "projects")):
            return p
        nxt = os.path.dirname(p)
        if nxt == p:          # dirname("C:") == "C:" on Windows: stop on no change
            raise SystemExit("could not find the workspace root")
        p = nxt


def main():
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf-8").read()
    if MARK not in tpl:
        raise SystemExit("template.html has no %s marker" % MARK)
    with open(os.path.join(HERE, "payload.json"), encoding="utf-8") as f:
        data = f.read()
    json.loads(data)          # refuse to ship anything that will not parse
    page = tpl.replace(MARK, data)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("index.html   %.2f MB" % (os.path.getsize(OUT) / 1e6))

    root = workspace_root(HERE)
    tools = os.path.join(root, "catalog", "tools")
    for script in ("wrap_for_pages.py", "add_catalog_link.py"):
        path = os.path.join(tools, script)
        if not os.path.exists(path):
            print("skip         %s (not found)" % script)
            continue
        subprocess.run([sys.executable, path, OUT], check=True)
    print("index.html   %.2f MB (wrapped)" % (os.path.getsize(OUT) / 1e6))


if __name__ == "__main__":
    main()
