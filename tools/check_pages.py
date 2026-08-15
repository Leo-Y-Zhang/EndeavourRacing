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
import re
import subprocess
import sys
import tempfile
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
            ["node", "--check", path], capture_output=True, text=True, encoding="utf-8",
            errors="replace",
        )
        Path(path).unlink(missing_ok=True)
        if result.returncode != 0:
            first = (result.stderr or "").strip().splitlines()
            bad.append(f"script at line {line}: {first[-1] if first else 'syntax error'}")
    check(f"{app}: every inline script parses as JavaScript", not bad,
          f"{len(scripts)} script block(s)" + ("" if not bad else "; " + "; ".join(bad[:3])))


def check_external_links(by_app: dict[str, set[str]]) -> None:
    """Request every outbound URL. A sponsor's site going dark is worth knowing.

    Deliberately not part of the push gate: this depends on fifteen other
    people's servers, and a red build must mean something is wrong here.
    """
    import urllib.error
    import urllib.request

    print("\nOutbound links (requested live)\n")
    urls = sorted({u for group in by_app.values() for u in group})
    dead = []
    for url in urls:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; EndeavourRacing link check)"},
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                code = response.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        except Exception as exc:  # noqa: BLE001 -- network shapes vary wildly
            code = f"unreachable ({type(exc).__name__})"
        # 403 and 405 are bot-blocking, not a dead page.
        ok = str(code).startswith("2") or code in (403, 405)
        print(f"  [{'PASS' if ok else 'FAIL'}] {code}  {url}")
        if not ok:
            dead.append(f"{url} -> {code}")
    check("every outbound link resolves", not dead, "; ".join(dead[:4]))


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
