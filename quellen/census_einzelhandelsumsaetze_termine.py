#!/usr/bin/env python3
"""US Census Advance Monthly Retail Sales: 1 am Veroeffentlichungstag, sonst 0, jeder Kalendertag ab
2001-01-01 bis heute. Quelle: MARTSreleasedates.xls (BIFF8, Jahr x Monat -> Tag im Monat). Die Termine
stehen im Voraus im Census-Kalender wirtschaftlicher Indikatoren. Weggelassen werden Termine, die durch
Haushaltssperren verschoben wurden und damals nicht im Voraus feststanden (2013-10, 2013-11, 2019 und
2025-10..2026-04: Zellen mit '**', 'N/A' bzw. Sperr-Verschiebung). Termine in der Zukunft nicht geschrieben.
Die XLS-Datei wird mit einem eigenen Minimalleser (OLE2 + BIFF8) gelesen, nur Standardbibliothek."""
import datetime, gzip, io, json, os, struct, urllib.request

ID = "census_einzelhandelsumsaetze_termine"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://www.census.gov/retail/marts/www/MARTSreleasedates.xls"
START = datetime.date(2001, 1, 1)
AUSGELASSEN = {(2013, 10), (2013, 11)}

import struct
def ole_stream(data, name='Workbook'):
    ss=1<<struct.unpack_from('<H',data,30)[0]; ms=1<<struct.unpack_from('<H',data,32)[0]
    nfat,dirstart,_,cutoff,mfstart,nmf,difstart,ndif=struct.unpack_from('<IIIIIIII',data,44)
    difat=list(struct.unpack_from('<109I',data,76))
    d=difstart
    while d<0xFFFFFFFA and ndif>0:
        off=(d+1)*ss; v=struct.unpack_from('<%dI'%(ss//4),data,off); difat+=v[:-1]; d=v[-1]; ndif-=1
    fat=[]
    for s in difat[:nfat]:
        fat+=struct.unpack_from('<%dI'%(ss//4),data,(s+1)*ss)
    def chain(s):
        o=[]
        while s<0xFFFFFFFA: o.append(s); s=fat[s]
        return o
    def rd(s): return b''.join(data[(i+1)*ss:(i+2)*ss] for i in chain(s))
    dire=rd(dirstart)
    ents=[]
    for i in range(0,len(dire),128):
        e=dire[i:i+128]; nl=struct.unpack_from('<H',e,64)[0]
        nm=e[:max(nl-2,0)].decode('utf-16le'); st,sz=struct.unpack_from('<I',e,116)[0],struct.unpack_from('<I',e,120)[0]
        ents.append((nm,st,sz,e[66]))
    root=ents[0]
    for nm,st,sz,t in ents:
        if nm==name:
            if sz>=cutoff: return rd(st)[:sz]
            mini=rd(root[1]); mfat=[]
            for s in chain(mfstart): mfat+=struct.unpack_from('<%dI'%(ss//4),data,(s+1)*ss)
            o=[];s=st
            while s<0xFFFFFFFA: o.append(mini[s*ms:(s+1)*ms]); s=mfat[s]
            return b''.join(o)[:sz]
def rk(v):
    m=v>>2
    if v&2:
        x=float(v>>2 if v<2**31 else (v-2**32)>>2)
    else:
        x=struct.unpack('<d',struct.pack('<Q',(v&0xFFFFFFFC)<<32))[0]
    return x/100 if v&1 else x
def cells(data):
    wb=ole_stream(data); i=0; sst=[]; out=[]; pend=None; sheets=0
    recs=[]
    while i+4<=len(wb):
        t,l=struct.unpack_from('<HH',wb,i); recs.append((t,wb[i+4:i+4+l])); i+=4+l
    # SST with continues
    for n,(t,b) in enumerate(recs):
        if t==0xFC:
            buf=b; k=n+1
            while k<len(recs) and recs[k][0]==0x3C: buf+=b'\x00'+recs[k][1]; k+=1  # approx: ignore flag resets
            cnt=struct.unpack_from('<I',buf,4)[0]; p=8
            for _ in range(cnt):
                try:
                    cl=struct.unpack_from('<H',buf,p)[0]; fl=buf[p+2]; p+=3
                    rt=0;fe=0
                    if fl&8: rt=struct.unpack_from('<H',buf,p)[0]; p+=2
                    if fl&4: fe=struct.unpack_from('<I',buf,p)[0]; p+=4
                    if fl&1: s=buf[p:p+2*cl].decode('utf-16le','replace'); p+=2*cl
                    else: s=buf[p:p+cl].decode('latin1'); p+=cl
                    p+=4*rt+fe; sst.append(s)
                except Exception: sst.append(''); break
    sheet=-1
    for t,b in recs:
        if t==0x809 and struct.unpack_from('<H',b,2)[0]==0x10: sheet+=1
        if t==0x203: r,c,x=struct.unpack_from('<HHx',b[:6]+b'\0') if False else (struct.unpack_from('<HH',b,0)+(struct.unpack_from('<d',b,6)[0],)); out.append((sheet,r,c,x))
        elif t==0x27E: r,c=struct.unpack_from('<HH',b,0); out.append((sheet,r,c,rk(struct.unpack_from('<I',b,6)[0])))
        elif t==0xBD:
            r,c0=struct.unpack_from('<HH',b,0); n=(len(b)-6)//6
            for j in range(n): out.append((sheet,r,c0+j,rk(struct.unpack_from('<I',b,4+6*j+2)[0])))
        elif t==0xFD:
            r,c,_x,si=struct.unpack_from('<HHHI',b,0); out.append((sheet,r,c,sst[si] if si<len(sst) else ''))
    return out


def main():
    r = urllib.request.Request(URL, headers={"User-Agent": UA})
    data = urllib.request.urlopen(r, timeout=30).read()
    today = datetime.datetime.now(datetime.timezone.utc).date()
    rows = {}
    for s, rr, c, x in cells(data):
        if s == 0:
            rows.setdefault(rr, {})[c] = x
    ev = set()
    for rr, cols in rows.items():
        y = cols.get(0)
        if not isinstance(y, float) or y < 2001:
            continue
        y = int(y)
        for m in range(1, 13):
            v = cols.get(m)
            if not isinstance(v, float) or (y, m) in AUSGELASSEN or y == 2019 or (y, m) >= (2025, 10) and (y, m) <= (2026, 4):
                continue
            d = datetime.date(y, m, int(v))
            if d.weekday() >= 5:
                raise SystemExit("Wochenende: %s" % d)
            if d <= today:
                ev.add(d)
    if len(ev) < 250:
        raise SystemExit("zu wenige Termine: %d" % len(ev))
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        d = START
        while d <= today:
            t.write("%s,%d\n" % (d.isoformat(), 1 if d in ev else 0))
            d += datetime.timedelta(days=1)
        t.flush()
    os.makedirs(OUT, exist_ok=True)
    open(os.path.join(OUT, "termine.csv.gz"), "wb").write(buf.getvalue())
    meta = {"termine": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 am Veroeffentlichungstag des Advance Monthly Retail Sales Report des US Census Bureau (Einzelhandelsumsaetze Vormonat, 8:30 Uhr Washingtoner Zeit), sonst 0, ab 2001-01-01. Durch Haushaltssperren verschobene Termine (2013-10/11, 2019, 2025-10 bis 2026-04) ausgelassen.",
        "quelle_url": "https://www.census.gov/retail/marts/www/MARTSreleasedates.xls",
        "verdichtung": "keine (Ereignisreihe)",
        "publikation": "taeglich (Termine stehen im Voraus im Census-Kalender wirtschaftlicher Indikatoren; Quelle: census.gov/economic-indicators/calendar-listview.html)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False}}
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=2, sort_keys=True)
    print(len(ev), "Termine")


main()
