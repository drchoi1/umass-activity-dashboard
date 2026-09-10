#!/usr/bin/env python3
from __future__ import annotations
import html, json, re
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
CFG=json.loads((ROOT/'config.json').read_text())
TZ=ZoneInfo(CFG['timezone'])
NOW=datetime.now(TZ); TODAY=NOW.date(); SRC=CFG['sources']; WANTED=set(CFG['interested_classes'])

def load(p,d):
    try:return json.loads(p.read_text())
    except:return d

def save(p,o): p.write_text(json.dumps(o,indent=2,ensure_ascii=False))
def norm(s): return re.sub(r'\s+',' ',s or '').strip()
def fetch(url):
    r=requests.get(url,timeout=35,headers={'User-Agent':'Mozilla/5.0'}); r.raise_for_status(); return r.text

def ptime(s):
    s=s.lower().replace('.','').replace(' ','')
    for f in ('%I:%M%p','%I%p'):
        try:return datetime.strptime(s,f).time()
        except ValueError:pass

def fmt(s):
    t=ptime(s)
    return datetime.combine(date.today(),t).strftime('%-I:%M %p').replace(':00 ',' ') if t else s

def week_dates():
    m=TODAY-timedelta(days=TODAY.weekday()); return [m+timedelta(days=i) for i in range(7)]

def regular_hours(d):
    w=d.weekday()
    return {
      'rec':'6:00 AM–11:00 PM' if w<=3 else ('6:00 AM–10:00 PM' if w==4 else '10:00 AM–8:00 PM'),
      'rock':'12:00 PM–10:00 PM' if w<=3 else '12:00 PM–8:00 PM',
      'boyden':'11:00 AM–12:30 PM' if w<=4 else 'CLOSED',
      'hicks':{0:'6:30–8:30 AM · 12–3 PM · 5:30–7 PM',1:'12–3 PM',2:'6:30–8:30 AM · 12–3 PM · 5:30–7 PM',3:'12–3 PM',4:'6:30–8:30 AM · 12–3 PM · 5:30–8:30 PM',5:'8 AM–12 PM · 1–7 PM',6:'CLOSED'}[w]
    }

ALERT_CATEGORIES=('gym','rock','pools','fitness')

def classify_alerts(page_html):
    """Extract the homepage alert and keep schedule lines under their facility heading."""
    lines=[norm(x) for x in BeautifulSoup(page_html,'html.parser').get_text('\n').splitlines() if norm(x)]
    start=next((i for i,x in enumerate(lines) if 'facility alert:' in x.lower()),None)
    out={k:[] for k in ALERT_CATEGORIES}
    if start is None:return out
    context=None
    for line in lines[start:start+100]:
        low=line.lower()
        if line != lines[start] and (low.startswith('recwell fall semester hours') or low in (
            'quick links','recreation and wellbeing','recwell','contact us','hours of operation'
        )):break
        heading=low.rstrip(':')
        if heading in ('pools','pool') or re.fullmatch(r'(boyden|hicks) pool',heading):context='pools'
        elif heading in ('rockwell','rock wall') or re.search(r'\b(climbing|bouldering)\b',heading):context='rock'
        elif heading in ('group fitness','group fitness classes'):context='fitness'
        elif heading in ('recreation center','recreation centers','gym'):context='gym'
        if line == lines[start]:
            targets=[k for k in ALERT_CATEGORIES if re.search({
                'gym':r'recreation|recwell|gym','rock':r'rockwell|climb','pools':r'pool|swim|aquatic|boyden|hicks','fitness':r'fitness'
            }[k],low)] or list(ALERT_CATEGORIES)
            for k in targets:out[k].append(line)
        elif context:
            out[context].append(line)
    return out

def facility_alerts():
    try:
        return classify_alerts(fetch(SRC['alerts']))
    except Exception as e:return {k:[f'Alert check failed: {e}'] for k in ALERT_CATEGORIES}

TIME_RE=re.compile(r'(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)\s*[-–—]\s*(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)',re.I)
ROOM_RE=re.compile(r'Room\s+\d+(?:/\d+)?',re.I)

def parse_schedule(page_html):
        soup=BeautifulSoup(page_html,'html.parser')
        lines=[norm(x) for x in soup.get_text('\n').splitlines() if norm(x)]
        links={}
        for a in soup.find_all('a',href=True):
            if not ROOM_RE.search(norm(a.get_text(' ',strip=True))):continue
            for s in a.find_all_previous(string=True,limit=8):
                name=norm(str(s))
                if name in WANTED:
                    links[name]=requests.compat.urljoin(SRC['fitness'],a['href']);break
        days={d:[] for d in ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']}
        section=day=None
        for i,line in enumerate(lines):
            if line.startswith('Morning |'):section='Morning'
            elif line.startswith('Afternoon |'):section='Afternoon'
            elif line.startswith('Evening |'):section='Evening'
            elif line in days:day=line
            elif line in WANTED and day and section:
                window=lines[i+1:i+9]; tm=next((TIME_RE.search(x) for x in window if TIME_RE.search(x)),None)
                if not tm:continue
                room=next((ROOM_RE.search(x).group(0) for x in window if ROOM_RE.search(x)),'')
                item={'name':line,'start':tm.group(1).replace(' ',''),'end':tm.group(2).replace(' ',''),'room':room,'url':links.get(line,SRC['fitness'])}
                if item not in days[day]:days[day].append(item)
        return days

def refresh_schedule(old):
    try:
        days=parse_schedule(fetch(SRC['fitness']))
        if sum(len(v) for v in days.values())<5:raise RuntimeError('Fitness parser returned too few selected classes')
        out={'source_updated':NOW.isoformat(),'days':days}; save(DATA/'group_schedule.json',out); return out,None
    except Exception as e:return old,str(e)

MONTHS='January|February|March|April|May|June|July|August|September|October|November|December'
DATE_RE=re.compile(rf'({MONTHS})\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?',re.I)
SKATE_RE=re.compile(r'(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)\s*(?:-|–|—|to)\s*(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)',re.I)

def parse_date_text(s):
    m=DATE_RE.search(s)
    if not m:return None
    try:return datetime.strptime(f'{m.group(1)} {m.group(2)} {m.group(3) or TODAY.year}','%B %d %Y').date()
    except ValueError:return None

def skating_week():
    result={d.isoformat():[] for d in week_dates()}; wanted=set(week_dates())
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True); pg=b.new_page(viewport={'width':1400,'height':1000})
            pg.goto(SRC['ice_finnly'],wait_until='networkidle',timeout=90000); pg.wait_for_timeout(1500)
            for sel in ('.fc-list-button',"button:has-text('List')"):
                try:
                    q=pg.locator(sel).first
                    if q.count() and q.is_visible():q.click(timeout=4000);pg.wait_for_timeout(1000);break
                except Exception:pass
            current=None
            for line in [norm(x) for x in pg.locator('body').inner_text().splitlines() if norm(x)]:
                d=parse_date_text(line)
                if d:current=d
                m=SKATE_RE.search(line)
                if m and current in wanted:result[current.isoformat()].append(f'{fmt(m.group(1))}–{fmt(m.group(2))}')
            b.close()
        for k in result:result[k]=sorted(set(result[k]))
        return result,None
    except Exception as e:return result,str(e)

SPOTS=[re.compile(r'(\d+)\s+spots?\s+(?:available|remaining)',re.I),
       re.compile(r'(?:no\s+spots?\s+available|class\s+full|full)',re.I),re.compile(r'waitlist',re.I)]
def spot_text(body,start,target_date=None):
    body=norm(body); low=body.lower()
    if target_date:
        date_labels=(target_date.strftime('%A, %B %-d, %Y'),target_date.strftime('%B %-d, %Y'),
                     target_date.strftime('%-m/%-d/%Y'),target_date.strftime('%m/%d/%Y'))
        positions=[low.find(x.lower()) for x in date_labels if low.find(x.lower())>=0]
        if positions:
            pos=min(positions); body=body[pos:pos+2500];low=body.lower()
    for needle in {fmt(start).lower(),start.lower(),start.lower().replace(' ','')}:
        pos=low.find(needle)
        while pos>=0:
            w=body[max(0,pos-400):pos+600]
            for p in SPOTS:
                m=p.search(w)
                if m:
                    q=m.group(0)
                    if q.lower().startswith('no ') or 'full' in q.lower():return 'No spots available'
                    if 'waitlist' in q.lower():return 'Waitlist'
                    return f'{m.group(1)} spots available'
            pos=low.find(needle,pos+1)
    return None

def classes_for(schedule,d):return schedule.get('days',{}).get(d.strftime('%A'),[])

def update_availability(schedule):
    from playwright.sync_api import sync_playwright
    cache=load(DATA/'availability.json',{})
    dates=[TODAY,TODAY+timedelta(days=1)] if NOW.hour<14 else [TODAY+timedelta(days=1),TODAY+timedelta(days=2)]
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True)
        for d in dates:
            dk=d.isoformat(); dc=cache.get(dk,{})
            for c in classes_for(schedule,d):
                key=f"{c['name']}|{c['start']}"; url=c.get('url',SRC['fitness'])
                if 'getprogramdetails' not in url.lower():
                    dc.setdefault(key,{'availability':'Reservation link unavailable','checked_at':NOW.isoformat()});continue
                try:
                    pg=b.new_page();pg.goto(url,wait_until='networkidle',timeout=70000);pg.wait_for_timeout(1800)
                    dc[key]={'availability':spot_text(pg.locator('body').inner_text(),c['start'],d) or 'Availability unavailable','checked_at':NOW.isoformat()};pg.close()
                except Exception:dc.setdefault(key,{'availability':'Availability unavailable','checked_at':NOW.isoformat()})
            cache[dk]=dc
        b.close()
    save(DATA/'availability.json',cache);return cache

def snapshot(schedule,skating,alerts):
    s={'alerts':alerts}
    for d in week_dates():
        k=d.isoformat();s[k]={'hours':regular_hours(d),'skating':skating.get(k,[]),'fitness':[{x:y for x,y in c.items() if x in ('name','start','end','room')} for c in classes_for(schedule,d)]}
    return s

def changes(prev,cur):
    if not prev:return {}
    out={}
    for d in week_dates():
        k=d.isoformat();a=prev.get(k,{});b=cur.get(k,{});f={}
        oldh,newh=a.get('hours',{}),b.get('hours',{})
        hs=[x for x in ('rec','rock','boyden','hicks') if x in oldh and oldh.get(x)!=newh.get(x)]
        if hs:f['hours']=hs
        if 'skating' in a and a.get('skating')!=b.get('skating'):f['skating']=True
        if 'fitness' in a and a.get('fitness')!=b.get('fitness'):f['fitness']=True
        if f:out[k]=f
    if 'alerts' in prev and prev.get('alerts')!=cur.get('alerts'):out['alerts']=True
    return out

def esc(x):return html.escape(str(x or ''))

def render(schedule,av,skating,alerts,flags,skerr,serr):
    dates=week_dates();labels=[d.strftime('%a, %b %-d') for d in dates];panels=[]
    for d in dates:
        k=d.isoformat();f=flags.get(k,{});h=regular_hours(d)
        skate=' · '.join(skating.get(k,[])) or ('No public skating listed' if not skerr else 'Schedule check unavailable')
        fit=[]
        for c in classes_for(schedule,d):
            entry=av.get(k,{}).get(f"{c['name']}|{c['start']}",{});val=entry.get('availability','Not checked yet');checked=''
            if entry.get('checked_at'):
                try:checked=' · checked '+datetime.fromisoformat(entry['checked_at']).astimezone(TZ).strftime('%-I:%M %p')
                except Exception:pass
            full=' full' if val.lower().startswith('no spots') else ''
            fit.append('<a class="classrow" href="{}" target="_blank"><div><b>{}</b><small>{}–{} · {}{}</small></div><span class="pill{}">{}</span></a>'.format(esc(c.get('url',SRC['fitness'])),esc(c['name']),esc(fmt(c['start'])),esc(fmt(c['end'])),esc(c.get('room','')),esc(checked),full,esc(val)))
        if not fit:fit=['<div class="muted">No selected classes scheduled.</div>']
        changed_hours=set(f.get('hours',[]))
        def box(key,label,val):
            cls=' changed' if key in changed_hours else ''
            return f'<div class="mini{cls}"><span>{label}</span><b>{esc(val)}</b></div>'
        def alert_list(category):
            items=alerts.get(category,[])
            return '<ul class="alerts">'+''.join(f'<li>{esc(x)}</li>' for x in items)+'</ul>' if items else ''
        sc=' changed' if f.get('skating') else '';fc=' changed' if f.get('fitness') else ''
        ac=' changed' if flags.get('alerts') else ''
        panels.append(f'''<div class="day" data-date="{k}"><section class="card{sc}"><h2>⛸ <a href="{SRC['ice']}">Public skating</a></h2><div class="big">{esc(skate)}</div></section><section class="card{ac}"><h2>🏋️ <a href="{SRC['hours']}">Gym · Recreation Center</a></h2>{box('rec','Hours',h['rec'])}{alert_list('gym')}</section><section class="card{ac}"><h2>🧗 <a href="{SRC['hours']}">RockWell</a></h2>{box('rock','Hours',h['rock'])}{alert_list('rock')}</section><section class="card{ac}"><h2>🏊 <a href="{SRC['hours']}">Pools</a></h2><div class="grid">{box('boyden','Boyden Pool',h['boyden'])}{box('hicks','Curry Hicks Pool',h['hicks'])}</div>{alert_list('pools')}</section><section class="card{fc}{ac}"><h2>🧘 <a href="{SRC['fitness']}">Selected group fitness</a></h2>{''.join(fit)}{alert_list('fitness')}</section></div>''')
    updated=NOW.strftime('%a %b %-d, %-I:%M %p ET')
    warn=('Fitness parser warning: '+esc(serr)+'<br>' if serr else '')+('Skating parser warning: '+esc(skerr) if skerr else '')
    page=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UMass Activity Dashboard</title><style>*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f8;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}main{{max-width:680px;margin:auto;padding:16px 11px 40px}}a{{color:#1f4b99;text-decoration:none}}.top{{display:flex;justify-content:space-between;align-items:center;gap:8px}}.stamp,.muted{{font-size:12px;color:#667085}}.actions{{display:flex;gap:6px}}button,.btn{{font:inherit;font-size:12px;font-weight:700;border:1px solid #d5d9df;border-radius:10px;background:white;padding:8px 9px;color:#111827}}.nav{{display:grid;grid-template-columns:42px 1fr 42px;gap:8px;align-items:center;margin:11px 0}}.nav h1{{font-size:27px;text-align:center;margin:0}}.arrow{{font-size:22px}}.card{{background:white;border:1px solid #e6e8ec;border-radius:16px;margin:10px 0;padding:15px}}h2{{font-size:17px;margin:0 0 11px}}.big{{font-size:18px;font-weight:700}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:9px}}.mini{{background:#f8f9fb;border-radius:11px;padding:10px}}.mini span{{display:block;color:#667085;font-size:12px}}.mini b{{display:block;font-size:14px;margin-top:4px}}.alerts{{font-size:12px;color:#7a4d00;margin:10px 0 0;padding-left:20px}}.alerts li{{margin-top:5px}}.classrow{{display:flex;align-items:center;justify-content:space-between;gap:9px;padding:11px 0;border-top:1px solid #e6e8ec;color:#111827}}.classrow small{{display:block;color:#667085;font-size:12px;margin-top:3px}}.pill{{flex:none;font-size:11px;font-weight:700;padding:5px 8px;border-radius:999px;background:#e9f5ef;color:#176b47;max-width:145px;text-align:center}}.pill.full{{background:#fbeaea;color:#a12b2b}}.day{{display:none}}.day.active{{display:block}}.changed{{background:#fff1a8!important}}.notice{{font-size:11px;color:#755800;background:#fff8d8;border-radius:10px;padding:8px 10px}}footer{{font-size:11px;color:#667085;line-height:1.45;padding:8px 2px}}</style></head><body><main><div class="top"><div class="stamp">Updated <b>{esc(updated)}</b></div><div class="actions"><button onclick="location.reload()">Refresh</button><a class="btn" id="updateNow" target="_blank">Update now ↗</a></div></div><div class="nav"><button class="arrow" id="prev">‹</button><h1 id="title"></h1><button class="arrow" id="next">›</button></div><div class="notice">Update now opens GitHub Actions securely. Tap <b>Run workflow</b>, then return here and refresh after it finishes.</div>{''.join(panels)}<footer>Yellow = newly detected change; it clears on the next unchanged update.<br>Availability: 8 AM checks today + tomorrow; 8 PM checks tomorrow + the following day.<br>{warn}</footer></main><script>const labels={json.dumps(labels)};const dates={json.dumps([d.isoformat() for d in dates])};let idx={TODAY.weekday()};function show(i){{idx=Math.max(0,Math.min(6,i));document.querySelectorAll('.day').forEach(x=>x.classList.remove('active'));document.querySelector('[data-date="'+dates[idx]+'"]').classList.add('active');document.getElementById('title').textContent=labels[idx];document.getElementById('prev').disabled=idx===0;document.getElementById('next').disabled=idx===6}}document.getElementById('prev').onclick=()=>show(idx-1);document.getElementById('next').onclick=()=>show(idx+1);show(idx);const parts=location.pathname.split('/').filter(Boolean);const owner=location.hostname.split('.')[0];document.getElementById('updateNow').href=(location.hostname.endsWith('.github.io')&&parts.length)?'https://github.com/'+owner+'/'+parts[0]+'/actions/workflows/update.yml':'https://github.com/';</script></body></html>'''
    (ROOT/'index.html').write_text(page)

def main():
    schedule=load(DATA/'group_schedule.json',{'days':{}})
    schedule,serr=refresh_schedule(schedule)
    skating,skerr=skating_week();alerts=facility_alerts();av=update_availability(schedule)
    cur=snapshot(schedule,skating,alerts);prev=load(DATA/'previous_snapshot.json',{});flags=changes(prev,cur)
    save(DATA/'change_flags.json',flags);save(DATA/'previous_snapshot.json',cur)
    save(DATA/'state.json',{'updated_at':NOW.isoformat(),'fitness_error':serr,'skating_error':skerr,
                            'fitness_classes':sum(len(x) for x in schedule.get('days',{}).values())})
    render(schedule,av,skating,alerts,flags,skerr,serr)
    print('Generated live dashboard',NOW.isoformat())
if __name__=='__main__':main()
