#!/usr/bin/env python3
from __future__ import annotations
import json, re, html
from pathlib import Path
from datetime import datetime, date
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CFG = json.loads((ROOT / 'config.json').read_text())
TZ = ZoneInfo(CFG['timezone'])
NOW = datetime.now(TZ)
TODAY = NOW.date()
DAY = NOW.strftime('%A')
SRC = CFG['sources']
PROG = CFG['program_urls']


def load(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False))


def get(url):
    r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
    r.raise_for_status()
    return r.text


def norm(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def parse_time(s):
    s = s.lower().replace('.', '').replace(' ', '')
    for fmt in ('%I:%M%p', '%I%p'):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    return None


def fmt_time(s):
    t = parse_time(s)
    if not t:
        return s
    return datetime.combine(date.today(), t).strftime('%-I:%M %p').replace(':00 ', ' ')


def minutes(s):
    t = parse_time(s)
    return t.hour * 60 + t.minute if t else 0


def recwell_hours():
    # Current Fall 2026 regular hours, re-confirmed from the public hours page.
    # Alerts are shown separately so special closures remain visible.
    d = TODAY.weekday()
    return {
        'rec': '6:00 AM-11:00 PM' if d <= 3 else ('6:00 AM-10:00 PM' if d == 4 else '10:00 AM-8:00 PM'),
        'rock': '12:00 PM-10:00 PM' if d <= 3 else '12:00 PM-8:00 PM',
        'boyden': '11:00 AM-12:30 PM' if d <= 4 else 'CLOSED',
        'hicks': {
            0: '6:30-8:30 AM · 12-3 PM · 5:30-7 PM',
            1: '12-3 PM',
            2: '6:30-8:30 AM · 12-3 PM · 5:30-7 PM',
            3: '12-3 PM',
            4: '6:30-8:30 AM · 12-3 PM · 5:30-8:30 PM',
            5: '8 AM-12 PM · 1-7 PM',
            6: 'CLOSED'
        }[d]
    }


def facility_alert():
    try:
        text = '\n'.join(BeautifulSoup(get(SRC['alerts']), 'html.parser').stripped_strings)
        i = text.lower().find('facility alert:')
        return norm(text[i:i+1600]) if i >= 0 else 'No facility alert found on homepage.'
    except Exception as e:
        return f'Alert check failed: {e}'


TIME_RE = re.compile(r'(\d{1,2}(?::\d{2})?\s*[ap]m)\s*[-–—]\s*(\d{1,2}(?::\d{2})?\s*[ap]m)', re.I)
ROOM_RE = re.compile(r'Room\s+\d+(?:/\d+)?', re.I)


def refresh_weekly_schedule():
    old = load(DATA / 'group_schedule.json', {'days': {}})
    try:
        lines = [norm(x) for x in BeautifulSoup(get(SRC['fitness']), 'html.parser').get_text('\n').splitlines() if norm(x)]
        days = {d: [] for d in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']}
        section = None
        current_day = None
        wanted = set(CFG['interested_classes'])
        for i, x in enumerate(lines):
            if x.startswith('Morning |'):
                section = 'Morning'
            elif x.startswith('Afternoon |'):
                section = 'Afternoon'
            elif x.startswith('Evening |'):
                section = 'Evening'
            elif x in days:
                current_day = x
            elif x in wanted and current_day and section in ('Afternoon','Evening'):
                window = lines[i+1:i+8]
                tm = next((TIME_RE.search(y) for y in window if TIME_RE.search(y)), None)
                if tm:
                    room = next((ROOM_RE.search(y).group(0) for y in window if ROOM_RE.search(y)), '')
                    item = {'name': x, 'start': tm.group(1).replace(' ', ''), 'end': tm.group(2).replace(' ', ''), 'room': room}
                    if item not in days[current_day]:
                        days[current_day].append(item)
        if sum(len(v) for v in days.values()) < 10:
            raise RuntimeError('weekly parser looked incomplete')
        for d in days:
            days[d].sort(key=lambda z: minutes(z['start']))
        out = {'source_updated': NOW.isoformat(), 'days': days}
        save(DATA / 'group_schedule.json', out)
        return out, None
    except Exception as e:
        return old, str(e)


SPOT_PATTERNS = [
    re.compile(r'(\d+)\s+spots?\s+available', re.I),
    re.compile(r'no\s+spots?\s+available', re.I),
    re.compile(r'waitlist', re.I)
]


def find_availability(text, start):
    text = norm(text)
    low = text.lower()
    variants = {fmt_time(start).lower(), start.lower(), start.lower().replace(' ', '')}
    for variant in variants:
        pos = low.find(variant)
        while pos >= 0:
            window = text[max(0, pos-450):pos+650]
            for pat in SPOT_PATTERNS:
                m = pat.search(window)
                if m:
                    phrase = m.group(0)
                    if phrase.lower().startswith('no '):
                        return 'No spots available'
                    if 'waitlist' in phrase.lower():
                        return 'Waitlist'
                    return f'{m.group(1)} spots available'
            pos = low.find(variant, pos+1)
    return None


def update_availability(classes):
    cache = load(DATA / 'availability.json', {})
    day_key = TODAY.isoformat()
    current = cache.get(day_key, {})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for c in classes:
            k = f"{c['name']}|{c['start']}"
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 1200})
                page.goto(PROG[c['name']], wait_until='networkidle', timeout=70000)
                page.wait_for_timeout(2500)
                value = find_availability(page.locator('body').inner_text(), c['start'])
                if value:
                    current[k] = {'availability': value, 'checked_at': NOW.isoformat()}
                elif k not in current:
                    current[k] = {'availability': 'Availability unavailable', 'checked_at': NOW.isoformat()}
                page.close()
            except Exception:
                if k not in current:
                    current[k] = {'availability': 'Availability unavailable', 'checked_at': NOW.isoformat()}
        browser.close()
    cache[day_key] = current
    save(DATA / 'availability.json', cache)
    return current


SKATE_TIME = re.compile(r'(\d{1,2}(?::\d{2})?\s*[AP]M)\s*(?:-|–|—|to)\s*(\d{1,2}(?::\d{2})?\s*[AP]M)', re.I)
MONTHS = 'January|February|March|April|May|June|July|August|September|October|November|December'
DATE_RE = re.compile(rf'({MONTHS})\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?', re.I)


def skate_date(text):
    m = DATE_RE.search(text)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3) or TODAY.year}", '%B %d %Y').date()
    except Exception:
        return None


def public_skating_today():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1400, 'height': 1100})
            page.goto(SRC['ice_finnly'], wait_until='networkidle', timeout=80000)
            page.wait_for_timeout(1500)
            for selector in ('.fc-list-button', "button:has-text('List')"):
                try:
                    q = page.locator(selector).first
                    if q.count() and q.is_visible():
                        q.click(timeout=3000)
                        page.wait_for_timeout(1200)
                        break
                except Exception:
                    pass
            current_day = None
            found = []
            for line in [norm(x) for x in page.locator('body').inner_text().splitlines() if norm(x)]:
                d = skate_date(line)
                if d:
                    current_day = d
                m = SKATE_TIME.search(line)
                if m and current_day == TODAY:
                    found.append(f"{fmt_time(m.group(1))}-{fmt_time(m.group(2))}")
            browser.close()
            return sorted(set(found)), None
    except Exception as e:
        return [], str(e)


def render(hours, alert, skating, skate_error, schedule, availability, schedule_error):
    classes = schedule.get('days', {}).get(DAY, [])
    updated = NOW.strftime('%a %b %-d, %-I:%M %p ET')
    rows = []
    for c in classes:
        key = f"{c['name']}|{c['start']}"
        av = availability.get(key, {}).get('availability', 'Availability unavailable')
        pill_class = 'pill full' if av.lower().startswith('no spots') else 'pill'
        rows.append(
            '<a class="row" href="{url}"><div><b>{name}</b><small>{start}-{end} · {room}</small></div>'
            '<span class="{pill}">{av}</span></a>'.format(
                url=html.escape(PROG[c['name']]), name=html.escape(c['name']),
                start=html.escape(fmt_time(c['start'])), end=html.escape(fmt_time(c['end'])),
                room=html.escape(c.get('room','')), pill=pill_class, av=html.escape(av)))
    if not rows:
        rows = ['<div class="muted">No selected classes scheduled today.</div>']
    skate_text = ' · '.join(skating) if skating else ('No public skating listed today' if not skate_error else 'Schedule check unavailable')
    alert_text = alert[:500] + ('…' if len(alert) > 500 else '')
    warning = 'Weekly schedule refresh failed; cached schedule shown. ' if schedule_error else ''
    doc = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UMass Activity - {NOW.strftime('%a %b %-d')}</title>
<style>*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f8;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:680px;margin:auto;padding:18px 12px 44px}}h1{{font-size:29px;margin:5px 0 12px}}.stamp,.muted{{font-size:13px;color:#667085}}.card{{background:#fff;border:1px solid #e6e8ec;border-radius:16px;margin:10px 0;padding:15px}}h2{{font-size:17px;margin:0 0 11px}}a{{color:#1f4b99;text-decoration:none}}.big{{font-size:18px;font-weight:700}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px}}.mini{{background:#f8f9fb;border-radius:11px;padding:10px}}.label{{font-size:12px;color:#667085}}.value{{font-size:15px;font-weight:650;margin-top:3px}}.row{{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:11px 0;border-top:1px solid #e6e8ec;color:#111827}}.row b{{display:block}}.row small{{display:block;color:#667085;margin-top:3px}}.pill{{font-size:11px;font-weight:700;padding:5px 8px;border-radius:999px;background:#e9f5ef;color:#176b47;white-space:nowrap}}.pill.full{{background:#fbeaea;color:#a12b2b}}.alert{{font-size:13px;line-height:1.45}}footer{{font-size:11px;color:#667085;padding:8px 3px}}</style></head><body><main>
<div class="stamp">Most recent update: <b>{updated}</b></div><h1>{NOW.strftime('%a, %b %-d')}</h1>
<section class="card"><h2>⛸ <a href="{SRC['ice']}">Public skating</a></h2><div class="big">{html.escape(skate_text)}</div></section>
<section class="card"><h2>🏋️ <a href="{SRC['hours']}">RecWell & pool hours</a></h2><div class="grid"><div class="mini"><div class="label">Recreation Center</div><div class="value">{hours['rec']}</div></div><div class="mini"><div class="label">RockWell</div><div class="value">{hours['rock']}</div></div><div class="mini"><div class="label">Boyden Pool</div><div class="value">{hours['boyden']}</div></div><div class="mini"><div class="label">Curry Hicks Pool</div><div class="value">{hours['hicks']}</div></div></div></section>
<section class="card"><h2>🧘 <a href="{SRC['fitness']}">Selected group fitness</a></h2><div class="stamp">Availability checked: <b>{updated}</b></div>{''.join(rows)}</section>
<section class="card"><h2>⚠️ <a href="{SRC['alerts']}">Facility alerts</a></h2><div class="alert">{html.escape(alert_text)}</div></section>
<footer>{html.escape(warning)}Tap any linked heading/class to verify at the source.</footer></main></body></html>'''
    (ROOT / 'index.html').write_text(doc)


def main():
    schedule = load(DATA / 'group_schedule.json', {'days': {}})
    schedule_error = None
    if (DAY == 'Monday' and NOW.hour < 12) or not schedule.get('days'):
        schedule, schedule_error = refresh_weekly_schedule()
    classes = schedule.get('days', {}).get(DAY, [])
    availability = update_availability(classes)
    hours = recwell_hours()
    alert = facility_alert()
    skating, skate_error = public_skating_today()
    save(DATA / 'state.json', {'last_update': NOW.isoformat(), 'skate_error': skate_error, 'schedule_error': schedule_error})
    render(hours, alert, skating, skate_error, schedule, availability, schedule_error)
    print(f'Generated dashboard at {NOW.isoformat()}; {len(classes)} selected classes; {len(skating)} skating sessions.')


if __name__ == '__main__':
    main()
