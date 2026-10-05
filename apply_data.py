#!/usr/bin/env python3
"""
Swap the embedded `var DATA = {...};` JSON block in the dashboard with fresh
numbers, without touching anything else in the file (CSS, chart-drawing JS,
ad creative images, layout).

Wall Street Prompt variant of the PIM script: DATA holds one block per
newsletter under DATA["pubs"] (e.g. "dave", "felipe"). Each pub's
`dailyHistory` archive is upserted by date and never trimmed, separately from
the rolling 30-day `signups` window used for charts. Everything else is a deep
merge, so a partial refresh (e.g. Meta-only when Kit is unreachable) never
blanks out the other half of the page.

Usage:
  python3 apply_data.py --template index.html --data data.json --out index.html
"""
import argparse
import json

MARKER = "var DATA = "


def extract_current_data(html):
    marker_pos = html.find(MARKER)
    if marker_pos == -1:
        raise SystemExit("Could not find the 'var DATA = {...};' block in the template file.")
    json_start = marker_pos + len(MARKER)
    try:
        obj, json_end = json.JSONDecoder().raw_decode(html, json_start)
    except json.JSONDecodeError as e:
        raise SystemExit(f"Existing DATA block is not valid JSON: {e}")
    rest = html[json_end:]
    tail = 1 if rest[:1] == ";" else 0
    if rest[tail:tail + 1] == "\n":
        tail += 1
    return obj, marker_pos, json_end + tail


def deep_merge(base, overlay):
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = dict(base)
        for k, v in overlay.items():
            out[k] = deep_merge(base.get(k), v) if k in base else v
        return out
    return overlay


def upsert_daily_history(existing, new_days):
    by_date = {d["date"]: d for d in (existing or [])}
    for d in new_days or []:
        by_date[d["date"]] = d
    return sorted(by_date.values(), key=lambda d: d["date"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    html = open(args.template, encoding="utf-8").read()
    current, start, end = extract_current_data(html)
    new = json.load(open(args.data, encoding="utf-8"))

    merged = deep_merge(current, new)
    for key, pub in (new.get("pubs") or {}).items():
        incoming = list(pub.get("dailyHistory") or []) + list(pub.get("signups") or [])
        if incoming:
            old = ((current.get("pubs") or {}).get(key) or {}).get("dailyHistory")
            merged["pubs"][key]["dailyHistory"] = upsert_daily_history(old, incoming)

    block = MARKER + json.dumps(merged, ensure_ascii=False, indent=2) + ";\n"
    out = html[:start] + block + html[end:]
    # sanity: the new block must parse back
    extract_current_data(out)
    open(args.out, "w", encoding="utf-8").write(out)
    print(f"Applied data to {args.out} ({len(out)} bytes).")


if __name__ == "__main__":
    main()
