#!/usr/bin/env python3
from __future__ import annotations
import html,json,re
from pathlib import Path
from datetime import datetime,date,timedelta
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parent
DATA=ROOT/'data'
CFG=json.loads((ROOT/'config.json').read_text())
TZ=ZoneInfo(CFG['timezone'])
NOW=datetime.now(TZ); TODAY=NOW.date(); SRC=CFG['sources']; WANTED=set(CFG['interested_classes'])
DAYS=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
TIME_RANGE=re.compile(r'(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)\s*[-–—]\s*(\d{1,2}(?::\d{2})?\s*[ap]\.?m\.?)',re.I)
ROOM_RE=re.compile(r'Room\s+\d+(?:/\d+)?',re.I)
SPOTS=[re.compile(r'(\d+)\s+spots?\s+available',re.I),re.compile(r'no\s+spots?\s+available',re.I),re.compile(r'waitlist',re.I)]
MONTHS='January|February|March|April|May|June|July|August|September|October|November|December'
DATE_RE=re.compile(rf'({MONTHS})\s+(\d{{1,2}})(?:,\s*(\d{{4}}))?',re.I)
SKATE_RE=re.compile(r'(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)\s*(?:-|–|—|to)\s*(\d{1,2}(?::\d{2})?\s*[AP]\.?M\.?)',re.I)

def load(p,d):
    try:return json.loads(p.read_text())
    except:return d

def save(p,o): p.write_text(json.dumps(o,indent=2,ensure_ascii=False))
def norm(s): return re.sub(r'\s+',' ',s or '').strip()
def fetch(u):
    r=requests.get(u,timeout=30,headers={'User-Agent':'Mozilla/5.0'});r.raise_for_status();return r.text

def ptime(s):
    s=s.lower().replace('.','').replace(' ','')
    for f in ('%I:%M%p','%I%p'):
        try:return datetime.strptime(s,f).time()
        except:pass

def fmt(s):
    t=ptime(s)
    return datetime.combine(date.today(),t).strftime('%-I:%M %p').replace(':00 ',' ') if t else s

def week_dates():
    mon=TODAY-timedelta(days=TODAY.weekday());return [mon+timedelta(days=i) for i in range(7)]

def hours_for(d):
    w=d.weekday()
    return {'rec':'6:00 AM–11:00 PM' if w<=3 else ('6:00 AM–10:00 PM' if w==4 else '10:00 AM–8:00 PM'),'rock':'12:00 PM–10:00 PM' if w<=3 else '12:00 PM–8:00 PM','boyden':'11:00 AM–12:30 PM' if w<=4 else 'CLOSED','hicks':{0:'6:30–8:30 AM · 12–3 PM · 5:30–7 PM',1:'12–3 PM',2:'6:30–8:30 AM · 12–3 PM · 5:30–7 PM',3:'12–3 PM',4:'6:30–8:30 AM · 12–3 PM · 5:30–8:30 PM',5:'8 AM–12 PM · 1–7 PM',6:'CLOSED'}[w]}

def alert():
    try:
        t='\n'.join(BeautifulSoup(fetch(SRC['alerts']),'html.parser').stripped_strings);i=t.lower().find('facility alert:');return norm(t[i:i+1600]) if i>=0 else 'No facility alert found on homepage.'
    except Exception as e:return f'Alert check failed: {e}'

def weekly_refresh():
    old=load(DATA/'group_schedule.json',{'days':{}})
    try:
        soup=BeautifulSoup(fetch(SRC['fitness']),'html.parser');lines=[norm(x) for x in soup.get_text('\n').splitlines() if norm(x)];days={d:[] for d in DAYS};section=day=None
        links={norm(a.get_text(' ',strip=True)):requests.compat.urljoin(SRC['fitness'],a['href']) for a in soup.find_all('a',href=True) if norm(a.get_text(' ',strip=True)) in WANTED}
        for i,line in enumerate(lines):
            if line.startswith('Morning |'):section='Morning'
            elif line.startswith('Afternoon |'):section='Afternoon'
            elif line.startswith('Evening |'):section='Evening'
            elif line in days:day=line
            elif line in WANTED and day and section in ('Afternoon','Evening'):
                window=lines[i+1:i+9];tm=next((TIME_RANGE.search(x) for x in window if TIME_RANGE.search(x)),None)
                if tm:
                    room=next((ROOM_RE.search(x).group(0) for x in window if ROOM_RE.search(x)),'')
                    item={'name':line,'start':tm.group(1).replace(' ',''),'end':tm.group(2).replace(' ',''),'room':room,'url':links.get(line,SRC['fitness'])}
                    if item not in days[day]:days[day].append(item)
        if sum(len(v) for v in days.values())<8:raise RuntimeError('weekly parser incomplete')
        out={'source_updated':NOW.isoformat(),'days':days};save(DATA/'group_schedule.json',out);return out,None
    except Exception as e:return old,str(e)

def sdate(line):
    m=DATE_RE.search(line)
    if not m:return None
    try:return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3) or TODAY.year}",'%B %d %Y').date()
    except:return None

def skating_week():
    wanted=set(week_dates());out={d.isoformat():[] for d in wanted}
    try:
        with sync_playwright() as p:
            b=p.chromium.launch(headless=True);pg=b.new_page(viewport={'width':1400,'height':1100});pg.goto(SRC['ice_finnly'],wait_until='networkidle',timeout=90000);pg.wait_for_timeout(1500)
            for sel in ('.fc-list-button',"button:has-text('List')"):
                try:
                    q=pg.locator(sel).first
                    if q.count() and q.is_visible():q.click();pg.wait_for_timeout(1000);break
                except:pass
            cur=None
            for line in [norm(x) for x in pg.locator('body').inner_text().splitlines() if norm(x)]:
                d=sdate(line)
                if d:cur=d
                m=SKATE_RE.search(line)
                if m and cur in wanted:
                    x=f'{fmt(m.group(1))}–{fmt(m.group(2))}'
                    if x not in out[cur.isoformat()]:out[cur.isoformat()].append(x)
            b.close();return out,None
    except Exception as e:return out,str(e)

def avail_text(text,start):
    body=norm(text);low=body.lower()
    for v in {fmt(start).lower(),start.lower(),start.lower().replace(' ','')}:
        pos=low.find(v)
        while pos>=0:
            w=body[max(0,pos-400):pos+600]
            for p in SPOTS:
                m=p.search(w)
                if m:
                    q=m.group(0)
                    if q.lower().startswith('no '):return 'No spots available'
                    if 'waitlist' in q.lower():return 'Waitlist'
                    return f'{m.group(1)} spots available'
            pos=low.find(v,pos+1)

def classes_for(schedule,d): return schedule.get('days',{}).get(d.strftime('%A'),[])

def update_availability(schedule):
    cache=load(DATA/'availability.json',{})
    dates=[TODAY,TODAY+timedelta(days=1)] if NOW.hour<14 else [TODAY+timedelta(days=1),TODAY+timedelta(days=2)]
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True)
        for d in dates:
            cur=cache.get(d.isoformat(),{})
            for c in classes_for(schedule,d):
                k=f"{c['name']}|{c['start']}";url=c.get('url',SRC['fitness'])
                if 'GetProgramDetails' not in url:
                    cur[k]={'availability':'Reservation link unavailable','checked_at':NOW.isoformat(),'url':url};continue
                try:
                    pg=b.new_page();pg.goto(url,wait_until='networkidle',timeout=70000);pg.wait_for_timeout(2200);a=avail_text(pg.locator('body').inner_text(),c['start']);cur[k]={'availability':a or 'Availability unavailable','checked_at':NOW.isoformat(),'url':url};pg.close()
                except:cur[k]={'availability':cur.get(k,{}).get('availability','Availability unavailable'),'checked_at':NOW.isoformat(),'url':url}
            cache[d.isoformat()]=cur
        b.close()
    save(DATA/'availability.json',cache);return cache

def snapshot(schedule,skating,facility_alert):
    s={'alert':facility_alert}
    for d in week_dates():
        s[d.isoformat()]={'hours':hours_for(d),'skating':skating.get(d.isoformat(),[]),'fitness':[{k:x.get(k,'') for k in ('name','start','end','room')} for x in classes_for(schedule,d)]}
    return s

def changes(old,new):
    if not old:return {}
    f={}
    for d in week_dates():
        k=d.isoformat();a=old.get(k,{});b=new.get(k,{});df={};oh=a.get('hours',{});nh=b.get('hours',{});hc=[x for x in ('rec','rock','boyden','hicks') if x in oh and oh.get(x)!=nh.get(x)]
        if hc:df['hours']=hc
        if 'skating' in a and a.get('skating')!=b.get('skating'):df['skating']=True
        if 'fitness' in a and a.get('fitness')!=b.get('fitness'):df['fitness']=True
        if df:f[k]=df
    if old.get('alert') is not None and old.get('alert')!=new.get('alert'):f['alert']=True
    return f

def render(schedule,av,skating,facility_alert,flags,skerr,serr):
    dates=week_dates();labels=[d.strftime('%a, %b %-d') for d in dates];isos=[d.isoformat() for d in dates];panels=[]
    for d in dates:
        k=d.isoformat();df=flags.get(k,{});h=hours_for(d);hc=set(df.get('hours',[]));sk=' · '.join(skating.get(k,[])) or 'No public skating listed';cards=[]
        cards.append('<section class="card%s"><h2>⛸ <a href="%s">Public skating</a></h2><div class="big">%s</div></section>' % (' changed' if df.get('skating') else '',SRC['ice'],html.escape(sk)))
        minis=''.join('<div class="mini%s"><div class="label">%s</div><div class="value">%s</div></div>' % (' changed' if n in hc else '',lab,html.escape(h[n])) for n,lab in [('rec','Recreation Center'),('rock','RockWell'),('boyden','Boyden Pool'),('hicks','Curry Hicks Pool')])
        cards.append('<section class="card"><h2>🏋️ <a href="%s">RecWell & pool hours</a></h2><div class="grid">%s</div></section>' % (SRC['hours'],minis))
        rows=''
        for c in classes_for(schedule,d):
            item=av.get(k,{}).get(f"{c['name']}|{c['start']}",{});txt=item.get('availability','Not checked yet');checked=item.get('checked_at');ct=''
            if checked:
                try:ct=datetime.fromisoformat(checked).astimezone(TZ).strftime(' · checked %-I:%M %p')
                except:pass
            rows += '<a class="row" href="%s" target="_blank"><div><b>%s</b><small>%s–%s · %s%s</small></div><span class="pill%s">%s</span></a>' % (html.escape(c.get('url',SRC['fitness'])),html.escape(c['name']),fmt(c['start']),fmt(c['end']),html.escape(c.get('room','')),ct,' full' if txt.lower().startswith('no spots') else '',html.escape(txt))
        if not rows:rows='<div class="muted">No selected classes scheduled.</div>'
        cards.append('<section class="card%s"><h2>🧘 <a href="%s">Selected group fitness</a></h2>%s</section>' % (' changed' if df.get('fitness') else '',SRC['fitness'],rows))
        panels.append('<div class="day" data-date="%s">%s</div>' % (k,''.join(cards)))
    updated=NOW.strftime('%a %b %-d, %-I:%M %p ET');alert_cls=' changed' if flags.get('alert') else ''
    css='''*{box-sizing:border-box}body{margin:0;background:#f4f6f8;color:#111827;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}main{max-width:680px;margin:auto;padding:14px 10px 40px}a{color:#1f4b99;text-decoration:none}.top{display:flex;justify-content:space-between;align-items:center;gap:8px}.stamp,.muted{font-size:12px;color:#667085}.actions{display:flex;gap:6px}button,.btn{background:white;border:1px solid #d5d9df;border-radius:10px;padding:8px 10px;font-size:12px;font-weight:700;color:#111827}.nav{display:grid;grid-template-columns:42px 1fr 42px;align-items:center;gap:8px;margin:10px 0}h1{text-align:center;font-size:27px;margin:0}.card{background:white;border:1px solid #e6e8ec;border-radius:16px;padding:15px;margin:10px 0}h2{font-size:17px;margin:0 0 10px}.big{font-size:18px;font-weight:700}.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.mini{background:#f8f9fb;border-radius:11px;padding:10px}.label{font-size:12px;color:#667085}.value{font-size:15px;font-weight:650;margin-top:3px}.row{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:11px 0;border-top:1px solid #e6e8ec;color:#111827}.row b{display:block}.row small{display:block;color:#667085;margin-top:3px}.pill{font-size:11px;font-weight:700;padding:5px 8px;border-radius:999px;background:#e9f5ef;color:#176b47;white-space:nowrap}.pill.full{background:#fbeaea;color:#a12b2b}.changed{background:#fff1a8!important}.day{display:none}.day.active{display:block}.notice{font-size:11px;color:#7c5a00;background:#fff8d8;padding:8px 10px;border-radius:10px}footer{font-size:11px;color:#667085;line-height:1.45;padding:8px 2px}'''
    body=''.join(panels)
    footer='Yellow = a pre-existing schedule item changed on this update; it clears on the next unchanged update.<br>Availability: 8 AM checks D and D+1; 8 PM checks D+1 and D+2, yielding D−2 8 PM, D−1 8 AM, D−1 8 PM, D-day 8 AM.'
    if serr:footer += '<br>Weekly schedule issue: '+html.escape(serr)
    if skerr:footer += '<br>Skating issue: '+html.escape(skerr)
    js='''const labels=%s,isos=%s;let i=%d;function show(n){i=Math.max(0,Math.min(labels.length-1,n));document.querySelectorAll('.day').forEach(x=>x.classList.remove('active'));document.querySelector('[data-date="'+isos[i]+'"]').classList.add('active');title.textContent=labels[i];prev.disabled=i===0;next.disabled=i===labels.length-1}prev.onclick=()=>show(i-1);next.onclick=()=>show(i+1);show(i);const parts=location.pathname.split('/').filter(Boolean);if(location.hostname.endsWith('.github.io')&&parts.length){const owner=location.hostname.split('.')[0],repo=parts[0];updateNow.href=`https://github.com/${owner}/${repo}/actions/workflows/update.yml`}else updateNow.href='https://github.com/';''' % (json.dumps(labels),json.dumps(isos),TODAY.weekday())
    doc='<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>UMass Activity Dashboard</title><style>'+css+'</style></head><body><main><div class="top"><div class="stamp">Updated <b>'+updated+'</b></div><div class="actions"><button onclick="location.reload()">Refresh page</button><a class="btn" id="updateNow" target="_blank">Update now ↗</a></div></div><div class="nav"><button id="prev">‹</button><h1 id="title"></h1><button id="next">›</button></div><div class="notice">“Update now” opens GitHub Actions. Tap <b>Run workflow</b>, then return here and refresh.</div>'+body+'<section class="card'+alert_cls+'"><h2>⚠️ <a href="'+SRC['alerts']+'">Facility alerts</a></h2><div>'+html.escape(facility_alert[:600])+'</div></section><footer>'+footer+'</footer></main><script>'+js+'</script></body></html>'
    (ROOT/'index.html').write_text(doc)

def main():
    sched=load(DATA/'group_schedule.json',{'days':{}});serr=None
    if (NOW.strftime('%A')=='Monday' and NOW.hour<14) or not sched.get('days'):sched,serr=weekly_refresh()
    sk,skerr=skating_week();fa=alert();av=update_availability(sched);cur=snapshot(sched,sk,fa);prev=load(DATA/'previous_snapshot.json',{});flags=changes(prev,cur);save(DATA/'change_flags.json',flags);save(DATA/'previous_snapshot.json',cur);render(sched,av,sk,fa,flags,skerr,serr);print('Updated',NOW.isoformat());print(json.dumps(flags,indent=2))
if __name__=='__main__':main()
