"""Structural checks for the three single-file apps.

Each app is one hand-written `index.html` of well over a thousand lines with its
whole stylesheet and program inlined. Nothing about that is built, so nothing
about it is compiled, linted or type-checked -- a stray brace in the inline
script leaves a page that loads, renders its markup, and does nothing at all.
This checks the properties that would otherwise only be discovered by opening
the page and noticing.

    python tools/check_pages.py            # structure, script syntax, anchors
    python tools/check_pages.py --strict   # also fail on external references

Standard library only, and no network. The external links are checked
separately, on a schedule, because somebody else's server being down is not a
defect in this repository.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APPS = ("website", "precision-lap", "mission-control")

VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
}

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))
    if not ok:
        failures.append(name)


class Structure(HTMLParser):
    """Tag balance, plus the ids, anchors, scripts and local asset references."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, int]] = []
        self.unbalanced: list[str] = []
        self.ids: set[str] = set()
        self.anchors: list[tuple[str, int]] = []
        self.external: list[str] = []
        self.preconnect: list[str] = []
        self.local_assets: list[tuple[str, int]] = []
        self.scripts: list[tuple[int, str]] = []
        self._script_line: int | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        href = a.get("href") or ""
        src = a.get("src") or ""
        # A preconnect/dns-prefetch href names an ORIGIN to open a connection
        # to, not a page. Requesting it bare returns 404 from a perfectly
        # healthy CDN, so it counts as a dependency but never as a link.
        rel = (a.get("rel") or "").lower().split()
        if tag == "link" and ({"preconnect", "dns-prefetch"} & set(rel)):
            if href.startswith(("http://", "https://", "//")):
                self.preconnect.append(href)
            return
        for url in (href, src):
            if not url:
                continue
            if url.startswith("#"):
                self.anchors.append((url[1:], self.getpos()[0]))
            elif url.startswith(("http://", "https://", "//")):
                self.external.append(url)
            elif not url.startswith(("data:", "mailto:", "tel:", "javascript:")):
                self.local_assets.append((url.split("?")[0].split("#")[0], self.getpos()[0]))
        if tag == "script" and not src:
            self._script_line = self.getpos()[0]
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.unbalanced.append(f"</{tag}> at line {self.getpos()[0]} closes nothing")
            return
        if self.stack[-1][0] != tag:
            open_tag, open_line = self.stack[-1]
            self.unbalanced.append(
                f"</{tag}> at line {self.getpos()[0]} closes <{open_tag}> opened at line {open_line}"
            )
            # resync so one mistake does not cascade into hundreds
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    return
            return
        self.stack.pop()

    def handle_data(self, data):
        if self._script_line is not None:
            self.scripts.append((self._script_line, data))
            self._script_line = None


# `node --check` parses the file as a CommonJS module, which wraps the body in a
# function: a stray top-level `return`, and a top-level `await`, both pass there
# and both stop a browser parsing the page at all. These bodies are inline
# <script> content, so compile them the way a browser does -- vm.Script, script
# goal, sloppy mode. Reporting e.message rather than letting node throw also
# keeps the failure readable: an uncaught SyntaxError ends its stderr with the
# node version banner, and that banner is what used to get quoted back.
CHECK_JS = (
    "const fs=require('fs'),vm=require('vm');"
    "try{new vm.Script(fs.readFileSync(process.argv[1],'utf8'),{filename:process.argv[1]});}"
    "catch(e){console.error(String((e&&e.message)||e));process.exit(1);}"
)


def node_available() -> bool:
    try:
        subprocess.run(["node", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def check_script_syntax(app: str, scripts: list[tuple[int, str]], have_node: bool) -> None:
    if not have_node:
        print(f"  [SKIP] {app}: node not on PATH, inline script syntax not checked")
        failures.append(f"{app}: node unavailable, script syntax unchecked")
        return
    bad = []
    for line, body in scripts:
        if not body.strip():
            continue
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
            fh.write(body)
            path = fh.name
        result = subprocess.run(
            ["node", "-e", CHECK_JS, path], capture_output=True, text=True, encoding="utf-8",
            errors="replace",
        )
        Path(path).unlink(missing_ok=True)
        if result.returncode != 0:
            first = (result.stderr or "").strip().splitlines()
            bad.append(f"script at line {line}: {first[-1] if first else 'syntax error'}")
    check(f"{app}: every inline script parses as JavaScript", not bad,
          f"{len(scripts)} script block(s)" + ("" if not bad else "; " + "; ".join(bad[:3])))


LINK_OK = "ok"
LINK_DEAD = "dead"
LINK_UNAVAILABLE = "unavailable"


def classify_link(code) -> str:
    """Split an outbound result into OUR defect, THEIR outage, or fine.

    The module docstring states the rule this implements: somebody else's server
    being down is not a defect in this repository. Only one of these three
    outcomes is evidence about the HTML committed here.

    - 2xx/3xx, and 403/405/429, are fine. 403 and 405 are bot-blocking, not a
      dead page. 429 is the same thing said differently: "too many requests" is
      the host rate-limiting this runner's shared IP, which is evidence about
      GitHub's egress and about how many other people are hitting that host, and
      none at all about whether the sponsor's site is up.

      MEASURED 2026-08-24: the weekly run went red solely because Instagram
      returned 429 for both endeavour.racing links, while every other link
      passed and the same two had been green the week before.

    - Any other 4xx is OUR defect. The server answered and said this specific
      path is not there, which is a statement about the URL written into the
      HTML in this repository. That is the case worth a red build.

    - 5xx, and anything unreachable (DNS, TLS, timeout), is THEIR outage. The
      URL may be perfectly correct and the host simply down.

      MEASURED 2026-08-24: the run went red solely because one sponsor,
      waterfronts.co.uk, returned 503 while the other fifteen links passed.
      Failing on that trains you to ignore the check, and an ignored red build
      is worse than no build -- this one guards thirteen sponsor links and needs
      to mean something when it fires.
    """
    if isinstance(code, int):
        if 200 <= code < 400 or code in (403, 405, 429):
            return LINK_OK
        if 400 <= code < 500:
            return LINK_DEAD
        return LINK_UNAVAILABLE
    return LINK_UNAVAILABLE


def warn(name: str, detail: str) -> None:
    """Surface something without failing the run.

    Under Actions this is a real annotation, so a sponsor going dark still shows
    on the run summary rather than only in the log nobody opens.
    """
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title={name}::{detail}")
    print(f"  [WARN] {name}  {detail}")


def check_external_links(by_app: dict[str, set[str]]) -> None:
    """Request every outbound URL. A sponsor's site going dark is worth knowing.

    Deliberately not part of the push gate: this depends on fifteen other
    people's servers, and a red build must mean something is wrong here.
    """
    import urllib.error
    import urllib.request

    def fetch(url: str):
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EndeavourRacing link check)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code
        except Exception as exc:  # noqa: BLE001 -- network shapes vary wildly
            return f"unreachable ({type(exc).__name__})"

    print("\nOutbound links (requested live)\n")
    urls = sorted({u for group in by_app.values() for u in group})
    dead, unavailable = [], []
    for url in urls:
        # Retry only the outcomes that a transient blip produces. A 404 is
        # stable by definition, so retrying it would just slow the run down.
        for attempt in range(3):
            code = fetch(url)
            verdict = classify_link(code)
            if verdict != LINK_UNAVAILABLE or attempt == 2:
                break
            time.sleep(2 * (attempt + 1))
        label = {LINK_OK: "PASS", LINK_DEAD: "FAIL", LINK_UNAVAILABLE: "WARN"}[verdict]
        print(f"  [{label}] {code}  {url}")
        if verdict == LINK_DEAD:
            dead.append(f"{url} -> {code}")
        elif verdict == LINK_UNAVAILABLE:
            unavailable.append(f"{url} -> {code}")

    check("every outbound link resolves", not dead, "; ".join(dead[:4]))
    if unavailable:
        warn("outbound host unreachable (not a defect here)", "; ".join(unavailable[:4]))


def selftest() -> int:
    """Prove the classifier, since the live check cannot be run deterministically.

    Every row here has been observed as a real outcome of this script except the
    404, which is the case the whole split exists to keep failing.
    """
    cases = [
        (200, LINK_OK), (202, LINK_OK), (301, LINK_OK),
        (403, LINK_OK), (405, LINK_OK), (429, LINK_OK),
        (404, LINK_DEAD), (410, LINK_DEAD), (400, LINK_DEAD),
        (500, LINK_UNAVAILABLE), (503, LINK_UNAVAILABLE), (504, LINK_UNAVAILABLE),
        ("unreachable (URLError)", LINK_UNAVAILABLE),
        ("unreachable (timeout)", LINK_UNAVAILABLE),
    ]
    bad = [f"{code} -> {classify_link(code)}, expected {want}"
           for code, want in cases if classify_link(code) != want]
    check(f"link classifier agrees on {len(cases)} known outcomes", not bad, "; ".join(bad[:3]))
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--strict", action="store_true",
                    help="also fail if a page references an external origin")
    ap.add_argument("--links", action="store_true",
                    help="also request every external URL and report any that is gone")
    args = ap.parse_args()

    have_node = node_available()
    summary = {}
    all_external: dict[str, set[str]] = {}

    # Runs on every invocation, including the push gate, so the rule that decides
    # whether a link result is this repository's problem is itself checked here
    # rather than only on the weekly networked run.
    print("\nLink classifier\n")
    selftest()

    for app in APPS:
        page = ROOT / app / "index.html"
        print(f"\n{app}/index.html  ({page.stat().st_size:,} bytes)\n")
        text = page.read_text(encoding="utf-8")

        parser = Structure()
        parser.feed(text)

        check(f"{app}: tags balance", not parser.unbalanced and not parser.stack,
              "; ".join(parser.unbalanced[:2]) or
              (f"unclosed: {[t for t, _ in parser.stack][:3]}" if parser.stack else ""))

        check_script_syntax(app, parser.scripts, have_node)

        missing = sorted({a for a, _ in parser.anchors if a and a not in parser.ids})
        check(f"{app}: every in-page link has a target", not missing,
              f"{len(parser.anchors)} anchors, {len(parser.ids)} ids"
              + (f"; missing {missing[:5]}" if missing else ""))

        absent = sorted({p for p, _ in parser.local_assets
                         if not (page.parent / p).exists()})
        check(f"{app}: every local file it references exists", not absent,
              f"{len(parser.local_assets)} reference(s)"
              + (f"; absent {absent[:5]}" if absent else ""))

        real_external = [u for u in parser.external if not u.startswith("http://www.w3.org/")]
        all_external[app] = set(real_external)
        origins = sorted({re.sub(r"^(https?:)?//([^/]+).*", r"\2", u)
                          for u in real_external + parser.preconnect})
        summary[app] = origins
        if args.strict:
            check(f"{app}: no external origins", not origins, ", ".join(origins))
        else:
            print(f"         external origins: {', '.join(origins) if origins else 'none'}")

    print("\nExternal origins each page depends on at load time:")
    print(json.dumps(summary, indent=2))

    if args.links:
        check_external_links(all_external)

    print()
    if failures:
        print(f"FAILED: {len(failures)} check(s) -> {', '.join(failures)}")
        return 1
    print("ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
