"""SEC EDGAR fetcher: resolve tickers, list filings, download documents and their text versions.

Usage:
  python tools/edgar.py list AMZN --forms "10-K,DEF 14A" --limit 10
  python tools/edgar.py get AMZN --form 10-K --year 2024          # fiscal year (period of report)
  python tools/edgar.py get AMZN --form 10-K --year 2024 --prior   # also fetch the prior year, for new_language.py
  python tools/edgar.py get AMZN --accession 0001018724-25-000004 --exhibits
  python tools/edgar.py letters AMZN --limit 5                      # 8-K EX-99 exhibits that look like shareholder letters
  python tools/edgar.py url https://example.com/2024-letter.pdf --name brk-2024-letter

Files land in filings/<TICKER>/<FORM>_<period>_<accession>/ with meta.json and a .txt per document.
SEC requires a descriptive User-Agent with a contact; set SEC_USER_AGENT="Name contact@domain" to use your own.
"""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_text import to_text  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
FILINGS_DIR = REPO_ROOT / "filings"
CACHE_DIR = FILINGS_DIR / "_cache"
USER_AGENT = os.environ.get("SEC_USER_AGENT", "financialdata-research contact@example.com")
ANNUAL_FORMS = {"10-K", "10-K405", "10-KT", "20-F", "40-F", "ARS"}
LETTER_HINTS = re.compile(r"letter|shareholder|stockholder|owner|annual report", re.I)

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"})
_last_request = 0.0


def _get(url: str) -> requests.Response:
    # SEC fair-access limit is 10 req/s; stay well under it.
    global _last_request
    wait = 0.15 - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    resp = _session.get(url, timeout=60)
    _last_request = time.time()
    resp.raise_for_status()
    return resp


def _cached_json(url: str, name: str, max_age: timedelta) -> dict:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / name
    if path.exists() and datetime.now() - datetime.fromtimestamp(path.stat().st_mtime) < max_age:
        return json.loads(path.read_text())
    data = _get(url).json()
    path.write_text(json.dumps(data))
    return data


def resolve_cik(ticker_or_cik: str) -> tuple[int, str, str]:
    """Return (cik, ticker, company title). Accepts a ticker (AMZN, BRK-B, BRK.B) or a numeric CIK."""
    if ticker_or_cik.isdigit():
        cik = int(ticker_or_cik)
        try:
            sub = submissions(cik)
        except requests.HTTPError:
            sys.exit(f"no SEC filer with CIK {cik}. Non-US names that don't file with the SEC (e.g. Tokyo listings) "
                     "need the IR PDF instead: `edgar.py url <pdf>` or drop the file in Drive")
        return cik, (sub.get("tickers") or [str(cik)])[0], sub.get("name", "")
    tickers = _cached_json("https://www.sec.gov/files/company_tickers.json", "company_tickers.json", timedelta(days=7))
    want = ticker_or_cik.upper().replace(".", "-")
    for row in tickers.values():
        if row["ticker"].upper() == want:
            return int(row["cik_str"]), row["ticker"].upper(), row["title"]
    sys.exit(f"ticker not found in SEC company_tickers.json: {ticker_or_cik}. Try the numeric CIK; if the company "
             "doesn't file with the SEC, use `edgar.py url <pdf>` or drop the file in Drive")


def submissions(cik: int) -> dict:
    return _cached_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json", f"sub_{cik}.json", timedelta(hours=12))


def iter_filings(cik: int, include_older: bool = False):
    """Yield one dict per filing, newest first. 'recent' holds ~1,000 filings; older pages load on request."""
    sub = submissions(cik)
    pages = [sub["filings"]["recent"]]
    if include_older:
        for f in sub["filings"].get("files", []):
            pages.append(_cached_json(f"https://data.sec.gov/submissions/{f['name']}", f["name"], timedelta(days=30)))
    for cols in pages:
        for i in range(len(cols["accessionNumber"])):
            yield {
                "form": cols["form"][i],
                "filingDate": cols["filingDate"][i],
                "reportDate": cols["reportDate"][i],
                "accession": cols["accessionNumber"][i],
                "primaryDocument": cols["primaryDocument"][i],
                "description": cols.get("primaryDocDescription", [""] * (i + 1))[i],
            }


def _fiscal_year(f: dict) -> int:
    # Period of report defines the fiscal year (AAPL FY2024 ends 2024-09-28); proxies have no period, use filing date.
    return int((f["reportDate"] or f["filingDate"])[:4])


def find_filing(cik: int, form: str, year: int | None) -> dict:
    for include_older in (False, True):
        for f in iter_filings(cik, include_older):
            if f["form"] == form and (year is None or _fiscal_year(f) == year):
                return f
    sys.exit(f"no {form} found for CIK {cik}" + (f" with fiscal year {year}" if year else ""))


def filing_base_url(cik: int, accession: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/"


def filing_documents(cik: int, accession: str) -> list[dict]:
    """Parse the filing index page: one row per document with its exhibit type (EX-99.1, EX-13, ...)."""
    from bs4 import BeautifulSoup

    html = _get(filing_base_url(cik, accession) + f"{accession}-index.html").text
    soup = BeautifulSoup(html, "lxml")
    docs = []
    for table in soup.select("table.tableFile"):
        for tr in table.select("tr")[1:]:
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            link = tr.select_one("a")
            if len(tds) >= 4 and link:
                docs.append({"seq": tds[0], "description": tds[1], "name": link.get_text(strip=True), "type": tds[3]})
    return docs


def download_filing(cik: int, ticker: str, company: str, f: dict, exhibits: bool) -> Path:
    period = f["reportDate"] or f["filingDate"]
    out_dir = FILINGS_DIR / ticker / f"{f['form'].replace(' ', '').replace('/', '-')}_{period}_{f['accession']}"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = filing_base_url(cik, f["accession"])
    wanted = [f["primaryDocument"]]
    docs = []
    if exhibits:
        docs = filing_documents(cik, f["accession"])
        # EX-99 = press releases / shareholder letters, EX-13 = annual report to shareholders.
        wanted += [d["name"] for d in docs if re.match(r"EX-(99|13)", d["type"]) and d["name"] not in wanted]
    saved = []
    for name in wanted:
        path = out_dir / name
        if not path.exists():
            path.write_bytes(_get(base + name).content)
        if path.suffix.lower() in (".htm", ".html", ".pdf", ".txt"):
            txt = path.with_suffix(path.suffix + ".txt")
            if not txt.exists() and path.suffix.lower() != ".txt":
                to_text(path)
        saved.append({"name": name, "url": base + name, "text": f"{name}.txt"})
    meta = {"company": company, "ticker": ticker, "cik": cik, **f, "index_url": base + f"{f['accession']}-index.html",
            "documents": saved, "exhibit_index": docs}
    (out_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    return out_dir


def cmd_list(args) -> None:
    cik, ticker, company = resolve_cik(args.ticker)
    forms = {s.strip() for s in args.forms.split(",")} if args.forms else None
    print(f"{company} ({ticker}) CIK {cik}")
    n = 0
    for f in iter_filings(cik, include_older=args.all):
        if forms and f["form"] not in forms:
            continue
        print(f"{f['form']:<10} filed {f['filingDate']}  period {f['reportDate'] or '-':<10}  {f['accession']}  {f['primaryDocument']}")
        n += 1
        if n >= args.limit:
            break


def cmd_get(args) -> None:
    cik, ticker, company = resolve_cik(args.ticker)
    if args.accession:
        f = next((x for inc in (False, True) for x in iter_filings(cik, inc) if x["accession"] == args.accession), None)
        if not f:
            sys.exit(f"accession not found: {args.accession}")
    else:
        f = find_filing(cik, args.form, args.year)
    out = download_filing(cik, ticker, company, f, args.exhibits or f["form"] in ("8-K", "ARS"))
    print(out)
    if args.prior:
        prior = find_filing(cik, f["form"], _fiscal_year(f) - 1)
        print(download_filing(cik, ticker, company, prior, args.exhibits))


def cmd_letters(args) -> None:
    """Shareholder letters filed as 8-K exhibits (Amazon files its annual letter this way every April)."""
    cik, ticker, company = resolve_cik(args.ticker)
    found = 0
    for f in iter_filings(cik, include_older=args.all):
        if f["form"] != "8-K":
            continue
        docs = filing_documents(cik, f["accession"])
        hits = [d for d in docs if d["type"].startswith("EX-99") and LETTER_HINTS.search(d["description"] + " " + d["name"])]
        for d in hits:
            print(f"{f['filingDate']}  {f['accession']}  {d['type']:<8} {d['description'] or d['name']}")
            found += 1
        if found >= args.limit:
            break
    if not found:
        print("no letter-like EX-99 exhibits found; descriptions are often blank, so also try `list --forms 8-K` "
              "and open the April filings, or `get --form ARS`")


def cmd_url(args) -> None:
    out_dir = FILINGS_DIR / "_web"
    out_dir.mkdir(parents=True, exist_ok=True)
    resp = requests.get(args.url, timeout=90, headers={"User-Agent": "Mozilla/5.0 (research)"})
    resp.raise_for_status()
    is_pdf = resp.content[:4] == b"%PDF" or args.url.lower().split("?")[0].endswith(".pdf")
    name = args.name or re.sub(r"[^A-Za-z0-9._-]+", "-", args.url.split("?")[0].rstrip("/").split("/")[-1])[:80]
    path = out_dir / (Path(name).stem + (".pdf" if is_pdf else ".html"))
    path.write_bytes(resp.content)
    to_text(path)
    (path.parent / (path.name + ".meta.json")).write_text(json.dumps({"url": args.url, "fetched": datetime.now().isoformat()}))
    print(path)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("ticker")
    p.add_argument("--forms", help='comma-separated, e.g. "10-K,DEF 14A,8-K,ARS"')
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--all", action="store_true", help="include filings older than the ~1,000 most recent")
    p.set_defaults(func=cmd_list)
    g = sub.add_parser("get")
    g.add_argument("ticker")
    g.add_argument("--form", default="10-K")
    g.add_argument("--year", type=int, help="fiscal year (period of report); proxies use filing year")
    g.add_argument("--accession")
    g.add_argument("--exhibits", action="store_true", help="also download EX-99 / EX-13 exhibits")
    g.add_argument("--prior", action="store_true", help="also download the prior fiscal year's filing of the same form")
    g.set_defaults(func=cmd_get)
    l = sub.add_parser("letters")
    l.add_argument("ticker")
    l.add_argument("--limit", type=int, default=5)
    l.add_argument("--all", action="store_true")
    l.set_defaults(func=cmd_letters)
    u = sub.add_parser("url")
    u.add_argument("url")
    u.add_argument("--name")
    u.set_defaults(func=cmd_url)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
