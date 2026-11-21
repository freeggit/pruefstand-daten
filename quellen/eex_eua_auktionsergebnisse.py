#!/usr/bin/env python3
"""EEX: Ergebnisse der EU-Emissionsrechte-Primaerauktionen (EUA, EU ETS1), Tagesreihen ab 2012.
Quelle: oeffentliche Jahresdateien der EEX (Archiv 2012-2025 als ZIP mit xls/xlsx, laufendes Jahr als xlsx).
Nur EUA-Auktionen (Kontrakte ohne Luftfahrt EUAA und ohne ETS2). Je Kalendertag mit mindestens einer
Auktion: deckungsquote = Summe Gebotsvolumen / Summe Auktionsvolumen; preis = volumengewichteter
Zuschlagspreis (EUR/tCO2). Tage ohne Auktion fehlen (nichts aufgefuellt). xls (2012-2019) wird mit dem
Minimalleser aus census_einzelhandelsumsaetze_termine.py (OLE2+BIFF8) gelesen; nur Standardbibliothek."""
import datetime, gzip, io, json, os, re, sys, urllib.request, zipfile
import xml.etree.ElementTree as ET

ID = "eex_eua_auktionsergebnisse"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "data", "neu", ID)
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
ARCHIV = ("https://www.eex.com/fileadmin/EEX/Downloads/Markets/Environmentals/EUA_Emission_Spot_Primary_"
          "Market_Auction_Report/Archive_Reports/emission-spot-primary-market-auction-report-2012-2025-data.zip")
LAUFEND = "https://public.eex-group.com/eex/eua-auction-report/emission-spot-primary-market-auction-report-%d-data.xlsx"
SEITE = "https://www.eex.com/en/market-data/market-data-hub/environmentals/eex-eua-primary-auction-spot-download"
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


# Minimalleser OLE2 + BIFF8 (Kopie aus census_einzelhandelsumsaetze_termine.py)
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


def hole(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def zeilen_xls(raw):
    rows = {}
    for s, r, c, v in cells(raw):
        if s == 0:
            rows.setdefault(r, {})[c] = v
    return [[rows[r].get(k) for k in range(max(rows[r]) + 1)] for r in sorted(rows)]


def zeilen_xlsx(raw):
    z = zipfile.ZipFile(io.BytesIO(raw))
    try:
        ss = [''.join(t.text or '' for t in si.iter(M + 't'))
              for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall(M + 'si')]
    except KeyError:
        ss = []
    out = []
    for r in ET.fromstring(z.read('xl/worksheets/sheet1.xml')).iter(M + 'row'):
        d = {}
        for c in r.findall(M + 'c'):
            col = 0
            for ch in re.sub(r'\d', '', c.get('r')):
                col = col * 26 + ord(ch) - 64
            v = c.find(M + 'v')
            x = v.text if v is not None else ''.join(t.text or '' for t in c.iter(M + 't'))
            if c.get('t') == 's' and x is not None:
                x = ss[int(x)]
            elif x not in (None, '') and c.get('t') not in ('str', 'inlineStr'):
                try:
                    x = float(x)
                except ValueError:
                    pass
            d[col - 1] = x
        out.append([d.get(k) for k in range(max(d) + 1)] if d else [])
    return out


def zahl(x):
    if isinstance(x, float):
        return x
    try:
        return float(str(x).replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def auswerten(rows, tage):
    kopf = None
    for row in rows:
        namen = [str(x).strip().lower() if x is not None else '' for x in row]
        if kopf is None:
            if 'date' in namen and any(n.startswith('auction price') for n in namen):
                kopf = {
                    'd': namen.index('date'),
                    'k': namen.index('contract'),
                    'p': next(i for i, n in enumerate(namen) if n.startswith('auction price')),
                    'v': next(i for i, n in enumerate(namen) if n.startswith('auction volume')),
                    'b': next(i for i, n in enumerate(namen) if n.startswith('total amount of bids')),
                }
            continue
        def g(i):
            return row[i] if i < len(row) else None
        dv, kon = g(kopf['d']), str(g(kopf['k']) or '').strip().upper()
        if not isinstance(dv, float) or not kon:
            continue
        if 'AA' in kon or 'ETS2' in kon or kon.startswith('E2'):
            continue  # Luftfahrt (EUAA) und ETS2 ausgeschlossen
        p, v, b = zahl(g(kopf['p'])), zahl(g(kopf['v'])), zahl(g(kopf['b']))
        if p is None or v is None or v <= 0:
            continue
        tag = datetime.date(1899, 12, 30) + datetime.timedelta(days=int(dv))
        t = tage.setdefault(tag, [0.0, 0.0, 0.0, 0.0])  # vol, vol*preis, vol mit gebot, gebote
        t[0] += v; t[1] += v * p
        if b is not None and b > 0:
            t[2] += v; t[3] += b
    if kopf is None:
        raise RuntimeError("Kopfzeile nicht gefunden")


def schreibe(name, werte):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%s\n" % (d.isoformat(), w) for d, w in werte)).encode())
    with open(os.path.join(OUT, name + ".csv.gz"), "wb") as f:
        f.write(buf.getvalue())


def main():
    tage = {}
    z = zipfile.ZipFile(io.BytesIO(hole(ARCHIV)))
    jahre = set()
    for n in sorted(z.namelist()):
        m = re.search(r'report-(\d{4})-data\.xlsx?$', n)
        if not m:
            continue
        raw = z.read(n)
        auswerten(zeilen_xls(raw) if n.endswith('.xls') else zeilen_xlsx(raw), tage)
        jahre.add(int(m.group(1)))
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    for j in range(max(jahre) + 1, heute.year + 1):
        auswerten(zeilen_xlsx(hole(LAUFEND % j)), tage)
    tage = {d: t for d, t in tage.items() if d <= heute}
    if len(tage) < 500:
        raise RuntimeError("zu wenige Auktionstage: %d" % len(tage))
    os.makedirs(OUT, exist_ok=True)
    preis = [(d, round(tage[d][1] / tage[d][0], 4)) for d in sorted(tage)]
    deck = [(d, round(tage[d][3] / tage[d][2], 4)) for d in sorted(tage) if tage[d][2] > 0]
    schreibe("preis", preis)
    schreibe("deckungsquote", deck)
    pub = ("taeglich: Auktionsergebnisse werden laut Auktionsverordnung (EU) 2023/2830 Art. 61 bzw. "
           "1031/2010 Art. 61 spaetestens 15 Minuten nach Schluss des Bieterfensters (Auktion um 11:00 MEZ) "
           "auf eex.com veroeffentlicht, also am Auktionstag")
    meta = {
        "preis": {"einheit": "EUR je tCO2", "beschreibung": "Volumengewichteter Zuschlagspreis der EUA-Primaerauktionen (EU ETS1) je Auktionstag an der EEX (EU-, DE-, PL-Auktionen; ohne Luftfahrt EUAA und ETS2)",
                  "quelle_url": SEITE, "verdichtung": "volumengewichtetes Mittel ueber alle EUA-Auktionen des Kalendertags", "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": pub},
        "deckungsquote": {"einheit": "Verhaeltnis Gebotsvolumen zu Auktionsvolumen", "beschreibung": "Deckungsquote (Cover Ratio) der EUA-Primaerauktionen je Auktionstag an der EEX: Summe Gebotsvolumen / Summe Auktionsvolumen (ohne Luftfahrt EUAA und ETS2)",
                          "quelle_url": SEITE, "verdichtung": "Summe Gebote / Summe Volumen ueber alle EUA-Auktionen des Kalendertags (Auktionen ohne Gebotsangabe ausgelassen)", "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": pub},
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("Tage", len(preis), len(deck), preis[0], preis[-1])


if __name__ == "__main__":
    main()
