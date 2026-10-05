#!/usr/bin/env python3
"""Assemble the Refactoring paid acquisition dashboard.

Inputs (build/raw):
  meta_adset_daily.csv   date, ad set code, spend, clicks, lead, reg (Windsor, RFT account)
  ads_30d.json           Windsor ad-level pull for the 30-day window
  images.json            optional {ad_id: data-uri} creative thumbnails
  logo.svg               Refactoring wordmark

Signup rule (matches Orin's weekly reports): ad sets optimised for registration
("| Reg") count Complete Registration; every other ad set counts Lead.

Outputs:
  out/page.html   body-only content for the Claude Artifact
  out/index.html  full standalone document for GitHub/Netlify
"""
import csv, json, datetime as dt, os, html, collections

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, 'raw')
style = open(os.path.join(ROOT, 'style_block.html')).read()
body = open(os.path.join(ROOT, 'body_template.html')).read()
logo = open(os.path.join(RAW, 'logo.svg')).read().strip()
logo = logo.replace('<svg width="183" height="33"', '<svg class="brand-logo" role="img" aria-label="Refactoring"', 1)
img_path = os.path.join(RAW, 'images.json')
images = json.load(open(img_path)) if os.path.exists(img_path) else {}

REPORT_END = dt.date(2026, 10, 4)
START30 = REPORT_END - dt.timedelta(days=29)
START7 = REPORT_END - dt.timedelta(days=6)
PRIOR7 = (REPORT_END - dt.timedelta(days=13), REPORT_END - dt.timedelta(days=7))
TARGET_CPA = 2.0
PRICE = 150.0

GROUP = {'R': 'us', 'L': 'us', 'ROW': 'row', 'RT': 'test', 'LS': 'test', 'LN': 'test'}
AUDIENCES = [
    ('us', 'US prospecting', 'Broad US audience, 25+'),
    ('row', 'Non-US prospecting', 'Broad audience outside the US, launched Oct 2'),
    ('test', 'Creative testing', 'New creative tested on the US audience before moving to prospecting'),
]


def signups(code, lead, reg):
    return reg if code in ('R', 'RT') else lead


rows = []
for r in csv.DictReader(open(os.path.join(RAW, 'meta_adset_daily.csv'))):
    d = dt.date.fromisoformat(r['date'])
    rows.append({'date': d, 'code': r['adset'], 'spend': float(r['spend']),
                 'subs': signups(r['adset'], int(r['lead']), int(r['reg']))})

by_day = collections.OrderedDict()
day = min(r['date'] for r in rows)
while day <= REPORT_END:
    by_day[day] = [0.0, 0]
    day += dt.timedelta(days=1)
for r in rows:
    by_day[r['date']][0] += r['spend']
    by_day[r['date']][1] += r['subs']


def rec(d, v):
    return {'date': d.isoformat(), 'spend': round(v[0], 2), 'subs': v[1], 'cpa': round(v[0] / v[1], 2) if v[1] else 0}


history = [rec(d, v) for d, v in by_day.items()]
last30 = [rec(d, v) for d, v in by_day.items() if d >= START30]


def window(a, b, group=None):
    s = n = 0
    for r in rows:
        if a <= r['date'] <= b and (group is None or GROUP[r['code']] == group):
            s += r['spend']; n += r['subs']
    return s, n


s30, n30 = window(START30, REPORT_END)
s7, n7 = window(START7, REPORT_END)
sp7, np7 = window(*PRIOR7)
cpa30, cpa7 = s30 / n30, s7 / n7

audiences = []
for key, name, desc in AUDIENCES:
    a30 = window(START30, REPORT_END, key)
    a7 = window(START7, REPORT_END, key)
    audiences.append({'key': key, 'name': name, 'desc': desc,
                      'spend30': round(a30[0], 2), 'subs30': a30[1],
                      'spend7': round(a7[0], 2), 'subs7': a7[1]})


def fmt_range(a, b):
    return f"{a.strftime('%b')} {a.day} &ndash; {b.strftime('%b')} {b.day}, {b.year}"


period_txt = f"{START30.strftime('%b')} {START30.day} – {REPORT_END.strftime('%b')} {REPORT_END.day}, {REPORT_END.year}"
data = {
    'reportingPeriod': period_txt,
    'chartRangeLabel': f"{START30.strftime('%b')} {START30.day} – {REPORT_END.strftime('%b')} {REPORT_END.day}",
    'pubs': {
        'refactoring': {
            'signups': last30,
            'summary': {'spend': f"${s30:,.2f}", 'signups': f"{n30:,}", 'cpa': f"${cpa30:.2f}"},
            'dailyHistory': history,
            'kpis': {'signups30': n30, 'spend30': round(s30, 2), 'cpa30': round(cpa30, 2),
                     'cpa7': round(cpa7, 2), 'cpa7prev': round(sp7 / np7, 2) if np7 else None,
                     'target': TARGET_CPA},
            'breakEven': {'price': PRICE, 'cpa30': round(cpa30, 2), 'cpa7': round(cpa7, 2)},
            'audiences': audiences,
            'quality': None,
        }
    },
}

# ---- creatives ----
ads = json.load(open(os.path.join(RAW, 'ads_30d.json')))['data']
agg = collections.defaultdict(lambda: {'spend': 0, 'reach': 0, 'imp': 0, 'subs': 0})
for r in ads:
    a = agg[r['ad_id']]
    a['name'] = r['ad_name']; a['created'] = r['ad_created_time'][:10]
    a['camp'] = r['campaign'].split('|')[2].strip()
    a['spend'] += r['spend'] or 0; a['reach'] += r['reach'] or 0; a['imp'] += r['impressions'] or 0
    a['subs'] += (r['actions_complete_registration'] if '| Reg' in r['adset_name'] else r['actions_lead']) or 0

LABELS = {
    'static_reddit_nativereddit-stylesocialproof': ('&ldquo;Reddit thread&rdquo; social proof', 'Static'),
    'static_graphic_eli5v2-howtorunanengineeringteam': ('ELI5: How to run an engineering team', 'Static'),
    'static_textheavy_leadoneday_new-url': ('&ldquo;Lead one day&rdquo; text static', 'Static'),
    'video_graphic_clipboard-whiteboardvariation': ('Clipboard to whiteboard', 'Video'),
    'video_textoverlay_ugcstyleengineertestimonial': ('Engineer testimonial (UGC style)', 'Video'),
    'video_textoverlay_3thingsseniorengineersareactuallypaidfor': ('3 things senior engineers are paid for', 'Video'),
    'static_notes_past3weeks-notesrefactoring': ('Notes app: past 3 weeks', 'Static'),
    'static_notes_softwareengineeringteam-onestepahead': ('Notes app: one step ahead', 'Static'),
    'static_textheavy_ifyourea-shipfaster_new-url': ('&ldquo;Ship faster&rdquo; text static', 'Static'),
}
PLACEHOLDER_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"></rect><circle cx="8.5" cy="10" r="1.4"></circle><path d="M21 16l-5-5-4 4-3-3-6 6"></path></svg>'


def creative_box(num, camp, title, sub):
    items = sorted([(k, v) for k, v in agg.items() if v['camp'] == camp], key=lambda kv: -kv[1]['spend'])
    cs = sum(v['spend'] for _, v in items); cn = sum(v['subs'] for _, v in items)
    avg = cs / cn
    out = []
    for i, (ad, c) in enumerate(items[:4], 1):
        label, fmt = LABELS.get(c['name'], (html.escape(c['name']), 'Video' if c['name'].startswith('video') else 'Static'))
        alt = html.unescape(label).replace('"', '') + ' ad creative'
        if ad in images:
            thumb = f'<img class="ct-thumb" src="{images[ad]}" alt="{html.escape(alt)}">'
        else:
            thumb = f'<div class="ct-thumb-placeholder">{PLACEHOLDER_ICON}</div>'
        days = (REPORT_END - dt.date.fromisoformat(c['created'])).days + 1
        cpa = c['spend'] / c['subs'] if c['subs'] else 0
        cls, arrow = ('good', '▼') if cpa <= avg else ('bad', '▲')
        freq = c['imp'] / c['reach'] if c['reach'] else 0
        out.append(f'''          <tr>
            <td class="num">{i}</td>
            <td><div class="ct-name-cell">{thumb}<div><div class="ct-label">{label}</div></div></div></td>
            <td><span class="ct-format">{fmt}</span></td>
            <td class="num">{days} days</td>
            <td class="num">{c['reach']:,}</td>
            <td class="num">{freq:.2f}</td>
            <td class="num">${c['spend']:,.0f}</td>
            <td class="num">{c['subs']:,}</td>
            <td class="num"><span class="ct-cpa {cls}">{arrow} ${cpa:.2f}</span></td>
          </tr>''')
    rows_html = '\n'.join(out)
    return f'''      <div class="campaign-box">
        <div class="campaign-box-head">
          <span class="campaign-box-num">{num}</span>
          <span class="campaign-box-title">{title}</span>
        </div>
        <p class="campaign-box-sub">{sub} CPA is colored against this campaign&rsquo;s blended average (${avg:.2f}).</p>
        <div class="campaign-box-body">
          <div class="creative-table-wrap">
            <table class="creative-table">
              <thead><tr><th>#</th><th>Creative</th><th>Format</th><th>Active for</th><th class="num">Reach</th><th class="num">Frequency</th><th class="num">Spend</th><th class="num">Signups</th><th class="num">CPA</th></tr></thead>
              <tbody>
{rows_html}
              </tbody>
            </table>
          </div>
          <p class="creative-table-note">Click any creative to enlarge it.</p>
        </div>
      </div>'''


PENDING_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"></circle><path d="M12 7v5l3 2"></path></svg>'

panel = f'''  <div class="pub-panel" id="panel-refactoring">
    <div class="kpi-row">
      <div class="kpi"><div class="label">Signups, last 30 days</div><div class="value" data-role="kpi-signups-value"></div><div class="note" data-role="kpi-signups-note"></div></div>
      <div class="kpi"><div class="label">Cost per signup, 30 days</div><div class="value" data-role="kpi-cpa30-value"></div><span class="chip" data-role="kpi-cpa30-chip"></span></div>
      <div class="kpi"><div class="label">Cost per signup, last 7 days</div><div class="value" data-role="kpi-cpa7-value"></div><span class="chip" data-role="kpi-cpa7-chip"></span><div class="note" data-role="kpi-cpa7-note"></div></div>
      <div class="kpi"><div class="label">Break-even paid conversion</div><div class="value is-target" data-role="kpi-be-value"></div><div class="note" data-role="kpi-be-note"></div></div>
    </div>

    <section>
      <div class="section-head"><h2 class="section-title">Compare periods</h2></div>
      <p class="section-sub">Meta spend, signups, and cost per signup, measured against a prior stretch of the same length.</p>
      <div class="card">
        <div class="compare-tabs" role="tablist">
          <button type="button" class="compare-tab is-active" data-role="tab-rolling" role="tab" aria-selected="true">Trailing 30 days</button>
          <button type="button" class="compare-tab" data-role="tab-months" role="tab" aria-selected="false">Pick two months</button>
        </div>
        <div class="compare-panel" data-role="cmp-rolling">
          <div class="compare-caption" data-role="cmp-rolling-caption"></div>
          <div class="compare-stats" data-role="cmp-rolling-stats"></div>
        </div>
        <div class="compare-panel" data-role="cmp-months" style="display:none;">
          <div class="compare-picker">
            <label>Month A<select id="month-a" data-role="month-a"></select></label>
            <span class="compare-vs">vs</span>
            <label>Month B<select id="month-b" data-role="month-b"></select></label>
          </div>
          <div class="compare-caption" data-role="cmp-months-caption"></div>
          <div class="compare-stats" data-role="cmp-months-stats"></div>
          <p class="compare-note" data-role="cmp-months-note"></p>
        </div>
      </div>
    </section>

    <section>
      <div class="section-head"><h2 class="section-title">Acquisition, last 30 days</h2></div>
      <p class="section-sub">Both newsletter campaigns combined. Registration-optimised ad sets count Complete Registration; lead-optimised ad sets count Lead.</p>
      <div class="chart-grid">
        <div class="card chart-card">
          <h3>Signups per day</h3>
          <div class="sub" data-role="chart-signups-sub"></div>
          <svg data-role="chart-signups" viewBox="0 0 680 200" role="img" aria-label="Daily newsletter signups from Meta ads"></svg>
        </div>
        <div class="card chart-card">
          <h3>Cost per signup</h3>
          <div class="sub" data-role="chart-cpa-sub"></div>
          <svg data-role="chart-cpa" viewBox="0 0 680 200" role="img" aria-label="Daily cost per signup"></svg>
        </div>
      </div>
      <div class="card">
        <div class="callout-row">
          <div class="stat"><div class="num" data-role="sum-spend"></div><div class="lbl">30-day spend</div></div>
          <div class="stat"><div class="num" data-role="sum-signups"></div><div class="lbl">30-day signups</div></div>
          <div class="stat"><div class="num" data-role="sum-cpa"></div><div class="lbl">blended cost / signup</div></div>
        </div>
        <details class="raw">
          <summary>View all 30 days as a table</summary>
          <div class="raw-table-wrap">
            <table class="raw-table">
              <thead><tr><th>Date</th><th>Spend</th><th>Signups</th><th>CPA</th></tr></thead>
              <tbody data-role="raw-tbody"></tbody>
            </table>
          </div>
        </details>
      </div>
    </section>

    <section>
      <div class="section-head"><h2 class="section-title">Audiences</h2></div>
      <p class="section-sub">Cost per signup is colored against the {f"${TARGET_CPA:.0f}"} target: green is at or under, red is above.</p>
      <div data-role="aud-body"></div>
    </section>

    <section>
      <div class="section-head"><h2 class="section-title">Top performing ad creatives</h2></div>
      <p class="section-sub">The four ads with the most spend in each campaign over the last 30 days. Green is cheaper than that campaign&rsquo;s average, red is more expensive.</p>
{creative_box(1, 'Prospecting', 'Prospecting', 'Scaled spend on proven creative.')}
{creative_box(2, 'Testing', 'Creative testing', 'New concepts get a smaller budget here before moving to prospecting.')}
    </section>

    <section>
      <div class="section-head"><h2 class="section-title">Subscriber quality by ad</h2></div>
      <p class="section-sub">How readers from each ad engage after they subscribe, and how many go on to a paid membership.</p>
      <div class="pending-banner" data-role="quality-banner">
        {PENDING_ICON}
        <div>
          <div class="t">Waiting on subscriber data from Refactoring</div>
          <div class="s">This table fills in once we can match each signup&rsquo;s UTM to its Substack engagement and paid status.</div>
          <div class="needs">
            <div class="need"><div class="k">Airtable</div><div class="v">Form signups with email, date, utm_medium (ad set) and utm_campaign (ad)</div></div>
            <div class="need"><div class="k">Substack export</div><div class="v">Email, signup date, opens and clicks (7 and 30 days), paid status and plan</div></div>
            <div class="need"><div class="k">Paid upgrades</div><div class="v">Upgrade date and plan for members who joined since Aug 19</div></div>
          </div>
        </div>
      </div>
      <div data-role="quality-body">
        <div class="card table-scroll pending-table" aria-hidden="true"><table class="aud-table"><thead><tr><th>Ad</th><th>Subscribers</th><th>Day-7 open</th><th>Day-30 open</th><th>Click rate</th><th>Went paid</th><th>Cost / paid member</th></tr></thead><tbody>
          <tr><td>Engineer testimonial (UGC style)</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td></tr>
          <tr><td>ELI5: How to run an engineering team</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td></tr>
          <tr><td>&ldquo;Reddit thread&rdquo; social proof</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td><td>&ndash;</td></tr>
        </tbody></table></div>
      </div>
    </section>

    <section>
      <div class="section-head"><h2 class="section-title">Free-to-paid break-even</h2></div>
      <p class="section-sub">The share of ad-acquired readers who need to become paid members for first-year membership revenue to cover ad spend, at the {f"${PRICE:.0f}"}/year price. Sponsorship value per reader is not included.</p>
      <div class="card" data-role="be-body"></div>
    </section>
  </div>
'''

data_json = json.dumps(data, ensure_ascii=False, indent=2)
content = body.replace('__PANELS__', panel).replace('__PERIOD__', html.escape(data['reportingPeriod'])).replace('__LOGO__', logo)
content = content.replace('var DATA = __DATA__;', 'var DATA = ' + data_json + ';')
assert '—' not in content and '&mdash;' not in content, 'em dash found'

title = '<title>Refactoring Ads Dashboard</title>\n'
page = title + style + '\n' + content
os.makedirs(os.path.join(ROOT, 'out'), exist_ok=True)
open(os.path.join(ROOT, 'out/page.html'), 'w').write(page)
index = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
         '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
         '<meta name="robots" content="noindex,nofollow">\n'
         + title + style + '\n</head>\n<body>\n' + content + '\n</body>\n</html>\n')
open(os.path.join(ROOT, 'out/index.html'), 'w').write(index)
print('page.html', len(page), 'index.html', len(index))
print('30d', round(s30, 2), n30, round(cpa30, 2), '7d', round(s7, 2), n7, round(cpa7, 2), 'prior7', round(sp7, 2), np7)
for a in audiences: print(a)
