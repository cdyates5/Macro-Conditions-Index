#!/usr/bin/env python3
"""
refresh.py - regenerate the Financial Conditions Lead Index in place.

Re-pulls market data, tops up the ISM history, recomputes the composite /
regressions / projection, and swaps the embedded data blob inside index.html.
Everything else in the dashboard (Chart.js, panels, styling, CSV export) is
left untouched.

    python3 refresh.py                 # refresh ./index.html
    python3 refresh.py --dry-run       # compute + report, write nothing
    python3 refresh.py path/to.html    # explicit target

ISM DESIGN NOTE
    ISM Manufacturing PMI is never revised, so its history lives in
    data/ism.csv (committed to the repo) rather than being re-scraped in
    full each run. Each run tries to append only the newest print from a
    public source. If that source is unavailable the run still succeeds
    using the stored history - the dashboard just carries the prior ISM
    vintage. To add a print by hand, append one line to data/ism.csv:
        2026-09,54.1
"""
import sys, os, json, csv, datetime as dt
import warnings
warnings.filterwarnings("ignore", message="Mean of empty slice")
try:
    import numpy as np, requests, urllib3
    urllib3.disable_warnings()
except ImportError:
    sys.exit("ERROR: missing deps -> pip install -r requirements.txt")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
DRY = "--dry-run" in sys.argv
TARGET = ARGS[0] if ARGS else os.path.join(HERE, "index.html")
ISM_CSV = os.path.join(HERE, "data", "ism.csv")

# never-revised cycle troughs: if these drift, the data is wrong - abort
ANCHORS = {"2020-04": 41.5, "2008-12": 32.9, "1991-01": 39.2, "2001-10": 40.8}

def log(m): print(m, flush=True)

# ------------------------------------------------------------------ market
def yf_monthly(sym, rng="40y"):
    r = requests.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                     params={"range": rng, "interval": "1d"},
                     headers={"User-Agent": UA}, verify=False, timeout=45)
    r.raise_for_status()
    res = r.json()["chart"]["result"][0]
    out = {}
    for t, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
        if c is None: continue
        d = dt.datetime.fromtimestamp(t, dt.timezone.utc)
        out[f"{d.year}-{d.month:02d}"] = float(c)    # last close in month
    if not out: raise RuntimeError(f"no data returned for {sym}")
    return out

# ------------------------------------------------------------------ ISM
def load_ism_csv():
    if not os.path.exists(ISM_CSV):
        sys.exit(f"ERROR: {ISM_CSV} not found - it holds the ISM history seed.")
    ism = {}
    with open(ISM_CSV) as f:
        for row in csv.DictReader(f):
            if row.get("month") and row.get("pmi"):
                ism[row["month"].strip()] = float(row["pmi"])
    bad = [f"{k}: {ism.get(k)} != {v}" for k, v in ANCHORS.items()
           if k not in ism or abs(ism[k] - v) > 0.35]
    if bad:
        sys.exit("ERROR: ISM anchor check failed (history looks corrupted):\n  " + "\n  ".join(bad))
    return ism

def fetch_latest_ism():
    """Newest published print as (month, value), or None if unavailable."""
    try:
        r = requests.post("https://scanner.tradingview.com/economics2/scan",
                          json={"symbols": {"tickers": ["ECONOMICS:USBCOI"]},
                                "columns": ["close", "time"]},
                          headers={"User-Agent": UA}, timeout=25)
        r.raise_for_status()
        val, ts = r.json()["data"][0]["d"]
        if val is None or ts is None: return None
        d = dt.datetime.fromtimestamp(ts, dt.timezone.utc)   # reference month end
        if not (25.0 < float(val) < 80.0): return None       # sanity band
        return f"{d.year}-{d.month:02d}", round(float(val), 1)
    except Exception as e:
        log(f"  (latest-ISM fetch unavailable: {type(e).__name__})")
        return None

def append_ism(month, value):
    with open(ISM_CSV, "a") as f:
        f.write(f"{month},{value:g}\n")

# ------------------------------------------------------------------ fetch
log("Fetching market legs (Yahoo)...")
SYMS = {"DXY": "DX-Y.NYB", "GSCI": "^SPGSCI", "Y10": "^TNX", "SPX": "^GSPC", "NDX": "^NDX"}
raw = {}
for k, s in SYMS.items():
    raw[k] = yf_monthly(s)
    log(f"  {k:4s} -> {max(raw[k])} = {raw[k][max(raw[k])]:.2f}")

log("Loading ISM history (data/ism.csv)...")
ism = load_ism_csv()
log(f"  {len(ism)} obs, through {max(ism)} = {ism[max(ism)]:g}  (anchors OK)")
latest = fetch_latest_ism()
if latest:
    mth, val = latest
    if mth > max(ism):
        ism[mth] = val
        if not DRY:
            append_ism(mth, val)
            log(f"  + appended new print {mth} = {val:g}")
        else:
            log(f"  + would append {mth} = {val:g} (dry-run)")
    elif abs(ism.get(mth, val) - val) > 0.35:
        log(f"  ! source disagrees at {mth}: stored {ism.get(mth)} vs fetched {val} - keeping stored")

# ------------------------------------------------------------------ align
def months(a, b):
    (ya, ma), (yb, mb) = a, b; out = []; y, m = ya, ma
    while (y, m) <= (yb, mb):
        out.append(f"{y}-{m:02d}"); m += 1
        if m > 12: m = 1; y += 1
    return out

common_last = min(max(raw[k]) for k in ("DXY", "GSCI", "Y10"))   # complete composite only
hy, hm = map(int, common_last.split("-"))
idx = months((1986, 7), (hy, hm))
ey, em, fut = hy, hm, []
for _ in range(18):
    em += 1
    if em > 12: em = 1; ey += 1
    fut.append(f"{ey}-{em:02d}")
idx_ext = idx + fut; N, NE = len(idx), len(idx) + 18
S = lambda d: np.array([d.get(k, np.nan) for k in idx], float)
DXY, GSCI, Y10 = S(raw["DXY"]), S(raw["GSCI"]), S(raw["Y10"])
SPX, NDX, ISM = S(raw["SPX"]), S(raw["NDX"]), S(ism)

# ------------------------------------------------------------------ compute
def devma(x, w):
    o = np.full_like(x, np.nan)
    for i in range(w, len(x)): o[i] = x[i] - np.nanmean(x[max(0, i-w):i])
    return o
Z    = lambda x: (x - np.nanmean(x)) / np.nanstd(x)
def yoy(x):
    o = np.full_like(x, np.nan); o[12:] = (x[12:]/x[:-12] - 1) * 100; return o
def pad(a):
    b = np.full(NE, np.nan); b[:len(a)] = a; return b

zDol, zCom, zRat = Z(devma(DXY, 36)), Z(devma(GSCI, 36)), Z(devma(Y10, 36))
zDolE, zComE, zRatE = pad(zDol), pad(zCom), pad(zRat)
ISME = pad(ISM)
FCIE = -np.nanmean(np.vstack([zDolE, zComE, zRatE]), axis=0)
spxY, ndxY = pad(yoy(SPX)), pad(yoy(NDX))

prof = {}
for L in range(25):
    a = FCIE[:NE-L] if L else FCIE; b = ISME[L:] if L else ISME
    m = ~np.isnan(a) & ~np.isnan(b)
    prof[L] = round(float(np.corrcoef(a[m], b[m])[0, 1]), 4) if m.sum() > 80 else None

reg = {}
for L in range(6, 19):
    X = np.vstack([zDolE[:NE-L], zComE[:NE-L], zRatE[:NE-L]]).T; y = ISME[L:]
    m = ~np.isnan(X).any(axis=1) & ~np.isnan(y)
    A = np.column_stack([np.ones(m.sum()), X[m]])
    coef, *_ = np.linalg.lstsq(A, y[m], rcond=None); pred = A @ coef
    r2 = 1 - np.sum((y[m]-pred)**2) / np.sum((y[m]-np.mean(y[m]))**2)
    reg[str(L)] = dict(coef=[round(float(c), 4) for c in coef], r2=round(float(r2), 4),
                       n=int(m.sum()), r=round(float(np.sqrt(max(r2, 0))), 4))

i2017 = idx.index("2017-01")
def eqfit(tgt, L):
    a = FCIE[:NE-L] if L else FCIE; b = tgt[L:] if L else tgt
    m = ~np.isnan(a) & ~np.isnan(b)
    A = np.column_stack([np.ones(m.sum()), a[m]])
    coef, *_ = np.linalg.lstsq(A, b[m], rcond=None)
    r = float(np.corrcoef(b[m], A @ coef)[0, 1])
    a2 = FCIE[i2017:NE-L] if L else FCIE[i2017:]; b2 = tgt[i2017+L:]
    n2 = min(len(a2), len(b2)); a2, b2 = a2[:n2], b2[:n2]
    m2 = ~np.isnan(a2) & ~np.isnan(b2)
    r17 = float(np.corrcoef(a2[m2], b2[m2])[0, 1]) if m2.sum() > 40 else None
    return dict(coef=[round(float(coef[0]), 3), round(float(coef[1]), 3)],
                r=round(r, 4), r2=round(r*r, 4),
                r2017=(round(r17, 4) if r17 is not None else None), n=int(m.sum()))

eqreg, eqprof = {"SPX": {}, "NDX": {}}, {"SPX": {}, "NDX": {}}
for L in range(15):
    eqreg["SPX"][str(L)] = eqfit(spxY, L); eqreg["NDX"][str(L)] = eqfit(ndxY, L)
    eqprof["SPX"][str(L)] = eqreg["SPX"][str(L)]["r"]; eqprof["NDX"][str(L)] = eqreg["NDX"][str(L)]["r"]

last_ism_i = max(i for i in range(N) if not np.isnan(ISM[i]))
last_eq_i  = max(i for i in range(N) if not np.isnan(spxY[i]))
cl = lambda a: [None if (x is None or (isinstance(x, float) and np.isnan(x))) else round(float(x), 3) for x in a]
DATA = dict(idx=idx_ext, n_hist=N, last_ism_idx=int(last_ism_i), last_eq_idx=int(last_eq_i),
            ISM=cl(ISME), zDol=cl(zDolE), zCom=cl(zComE), zRat=cl(zRatE), FCI=cl(FCIE),
            SPXY=cl(spxY), NDXY=cl(ndxY), lead_profile={str(k): v for k, v in prof.items()},
            reg=reg, default_lead=12, eqreg=eqreg, eqprof=eqprof, eq_default_lead=6,
            meta=dict(hist_end=idx[last_ism_i], generated=dt.date.today().isoformat()))

# ------------------------------------------------------------------ write
if not os.path.exists(TARGET): sys.exit(f"ERROR: target not found: {TARGET}")
html = open(TARGET, encoding="utf-8").read()
i0 = html.find("const D = ")
i1 = html.find(";\n// ---------- helpers")
if i0 < 0 or i1 < i0:
    sys.exit("ERROR: data markers not found - is this the dashboard HTML?")
new_html = html[:i0] + "const D = " + json.dumps(DATA) + html[i1:]
if DRY:
    log("\n(dry-run: index.html not written)")
else:
    open(TARGET, "w", encoding="utf-8").write(new_html)

peak = max((L for L in range(6, 19) if prof[L] is not None), key=lambda L: prof[L])
log("\n" + "=" * 58)
log(f"{'DRY-RUN' if DRY else 'REFRESHED'}  {os.path.basename(TARGET)}")
log(f"  ISM through    : {idx[last_ism_i]} = {ISM[last_ism_i]:g}   markets: {idx[-1]}")
log(f"  FCI now        : {FCIE[last_eq_i]:+.2f}  (dollar {float(zDol[last_eq_i]):+.2f}, "
    f"commodities {float(zCom[last_eq_i]):+.2f}, rates {float(zRat[last_eq_i]):+.2f})")
log(f"  ISM reg @12m   : R2={reg['12']['r2']:.3f}  r={reg['12']['r']:.2f}   peak lead {peak}m (r={prof[peak]:+.2f})")
log(f"  generated      : {DATA['meta']['generated']}")
log("=" * 58)
