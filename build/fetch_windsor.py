#!/usr/bin/env python3
"""Pull Refactoring's Meta data from the Windsor.ai REST API into build/raw/.

Runs inside GitHub Actions. Needs the WINDSOR_API_KEY environment variable
(stored as a GitHub repository secret, never in this file).

Writes:
  build/raw/meta_daily.json  daily ad set rows since launch
  build/raw/ads_30d.json     ad-level rows for the 30 days ending END
Exits non-zero (so the workflow stops and nothing is committed) if the pull
fails or looks empty.
"""
import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

ACCOUNT = "1238226194734920"          # Meta ad account "RFT" (Refactoring)
LAUNCH = "2026-08-19"
RAW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")

DAILY_FIELDS = ["date", "campaign", "adset_name", "spend", "clicks",
                "actions_lead", "actions_complete_registration"]
AD_FIELDS = ["ad_id", "ad_name", "campaign", "adset_name", "ad_created_time", "spend",
             "reach", "impressions", "link_clicks", "actions_lead",
             "actions_complete_registration", "thumbnail_url"]


def pull(fields, date_from, date_to):
    key = os.environ.get("WINDSOR_API_KEY")
    if not key:
        sys.exit("WINDSOR_API_KEY is not set")
    qs = urllib.parse.urlencode({
        "api_key": key,
        "date_from": date_from,
        "date_to": date_to,
        "fields": ",".join(fields),
        "select_accounts": f"facebook__{ACCOUNT}",
    })
    url = "https://connectors.windsor.ai/facebook?" + qs
    with urllib.request.urlopen(url, timeout=300) as r:
        body = json.load(r)
    rows = (body.get("data") or body.get("result") or []) if isinstance(body, dict) else body
    # keep newsletter campaigns only
    return [x for x in rows if "Newsletter" in (x.get("campaign") or "")]


def classify_reg(adset_name):
    return "| Reg" in (adset_name or "")


def fetch_images(ads, per_campaign=4):
    """Download thumbnails for the top ads by spend in each campaign that are not
    already in images.json. Failures are skipped; the page shows a placeholder."""
    import base64, collections, io
    path = os.path.join(RAW, "images.json")
    images = json.load(open(path)) if os.path.exists(path) else {}
    spend, camp, thumb = collections.defaultdict(float), {}, {}
    for r in ads:
        spend[r["ad_id"]] += float(r.get("spend") or 0)
        camp[r["ad_id"]] = (r.get("campaign") or "").split("|")[2].strip() if (r.get("campaign") or "").count("|") >= 2 else ""
        if r.get("thumbnail_url"):
            thumb[r["ad_id"]] = r["thumbnail_url"]
    wanted = []
    for c in set(camp.values()):
        wanted += sorted([a for a in spend if camp[a] == c], key=lambda a: -spend[a])[:per_campaign]
    added = 0
    for ad in wanted:
        if ad in images or ad not in thumb:
            continue
        try:
            req = urllib.request.Request(thumb[ad], headers={"User-Agent": "Mozilla/5.0"})
            raw = urllib.request.urlopen(req, timeout=60).read()
            try:
                from PIL import Image
                im = Image.open(io.BytesIO(raw)).convert("RGB")
                im.thumbnail((600, 600))
                buf = io.BytesIO(); im.save(buf, "JPEG", quality=85); raw = buf.getvalue()
                mime = "image/jpeg"
            except Exception:
                mime = "image/png" if raw[:4] == b"\x89PNG" else "image/jpeg"
            images[ad] = f"data:{mime};base64," + base64.b64encode(raw).decode()
            added += 1
        except Exception as e:
            print(f"image skipped for {ad}: {e}")
    json.dump(images, open(path, "w"))
    print(f"images added={added}")


def main():
    end = os.environ.get("END_DATE") or (
        dt.datetime.utcnow() - dt.timedelta(hours=5) - dt.timedelta(days=1)).date().isoformat()
    start30 = (dt.date.fromisoformat(end) - dt.timedelta(days=29)).isoformat()

    daily = pull(DAILY_FIELDS, LAUNCH, end)
    recent = [r for r in daily if r["date"][:10] >= (dt.date.fromisoformat(end) - dt.timedelta(days=2)).isoformat()
              and float(r.get("spend") or 0) > 0]
    if not daily or not recent:
        sys.exit(f"Windsor returned no recent spend (rows={len(daily)}); not updating the page")

    ads = pull(AD_FIELDS, start30, end)
    if not ads:
        sys.exit("Windsor returned no ad-level rows; not updating the page")

    os.makedirs(RAW, exist_ok=True)
    json.dump(daily, open(os.path.join(RAW, "meta_daily.json"), "w"))
    json.dump(ads, open(os.path.join(RAW, "ads_30d.json"), "w"))
    fetch_images(ads)
    with open(os.environ.get("GITHUB_ENV", os.devnull), "a") as f:
        f.write(f"END_DATE={end}\n")
    print(f"end={end} daily_rows={len(daily)} ad_rows={len(ads)}")


if __name__ == "__main__":
    main()
