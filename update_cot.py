"""
COT Weekly Updater
==================
Downloads CFTC Legacy COT data, fetches prices via yfinance,
and generates a self-contained HTML viewer.

Usage:
    python update_cot.py              # generates cot_viewer.html in current dir
    python update_cot.py -o ~/Desktop # generates in specified folder

Requirements:
    pip install pandas yfinance

Schedule:
    - CFTC publishes every Friday ~3:30 PM ET (as-of Tuesday)
    - Run this any time after Friday evening
    - Windows Task Scheduler or cron: every Saturday morning is ideal
"""

import pandas as pd
import json
import argparse
import os
import sys
import io
import zipfile
from datetime import datetime, timedelta
from urllib.request import urlopen, Request
from collections import Counter
import warnings
warnings.filterwarnings('ignore')

# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────

LOOKBACK_WEEKS = 52

TICKER_MAP = {
    # Metals
    'GOLD - COMMODITY EXCHANGE INC.': 'GC=F',
    'SILVER - COMMODITY EXCHANGE INC.': 'SI=F',
    'COPPER- #1 - COMMODITY EXCHANGE INC.': 'HG=F',
    'PLATINUM - NEW YORK MERCANTILE EXCHANGE': 'PL=F',
    'PALLADIUM - NEW YORK MERCANTILE EXCHANGE': 'PA=F',
    'ALUMINUM - COMMODITY EXCHANGE INC.': 'ALI=F',
    'STEEL-HRC - COMMODITY EXCHANGE INC.': 'HRC=F',
    # Energy
    'WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE': 'CL=F',
    'HENRY HUB - NEW YORK MERCANTILE EXCHANGE': 'NG=F',
    'NAT GAS NYME - NEW YORK MERCANTILE EXCHANGE': 'NG=F',
    'GASOLINE RBOB - NEW YORK MERCANTILE EXCHANGE': 'RB=F',
    'NY HARBOR ULSD - NEW YORK MERCANTILE EXCHANGE': 'HO=F',
    'BRENT LAST DAY - NEW YORK MERCANTILE EXCHANGE': 'BZ=F',
    'PROPANE - NEW YORK MERCANTILE EXCHANGE': 'B0=F',
    # Agriculture
    'CORN - CHICAGO BOARD OF TRADE': 'ZC=F',
    'SOYBEANS - CHICAGO BOARD OF TRADE': 'ZS=F',
    'SOYBEAN MEAL - CHICAGO BOARD OF TRADE': 'ZM=F',
    'SOYBEAN OIL - CHICAGO BOARD OF TRADE': 'ZL=F',
    'WHEAT-SRW - CHICAGO BOARD OF TRADE': 'ZW=F',
    'WHEAT-HRW - CHICAGO BOARD OF TRADE': 'KE=F',
    'OATS - CHICAGO BOARD OF TRADE': 'ZO=F',
    'ROUGH RICE - CHICAGO BOARD OF TRADE': 'ZR=F',
    'COTTON NO. 2 - ICE FUTURES U.S.': 'CT=F',
    'SUGAR NO. 11 - ICE FUTURES U.S.': 'SB=F',
    'COFFEE C - ICE FUTURES U.S.': 'KC=F',
    'COCOA - ICE FUTURES U.S.': 'CC=F',
    'FRZN CONCENTRATED ORANGE JUICE - ICE FUTURES U.S.': 'OJ=F',
    'LEAN HOGS - CHICAGO MERCANTILE EXCHANGE': 'HE=F',
    'LIVE CATTLE - CHICAGO MERCANTILE EXCHANGE': 'LE=F',
    'FEEDER CATTLE - CHICAGO MERCANTILE EXCHANGE': 'GF=F',
    # Currencies
    'EURO FX - CHICAGO MERCANTILE EXCHANGE': '6E=F',
    'JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE': '6J=F',
    'BRITISH POUND - CHICAGO MERCANTILE EXCHANGE': '6B=F',
    'SWISS FRANC - CHICAGO MERCANTILE EXCHANGE': '6S=F',
    'CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE': '6C=F',
    'AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE': '6A=F',
    'NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE': '6N=F',
    'MEXICAN PESO - CHICAGO MERCANTILE EXCHANGE': '6M=F',
    'BRAZILIAN REAL - CHICAGO MERCANTILE EXCHANGE': '6L=F',
    # Equity Indices
    'E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE': 'ES=F',
    'NASDAQ MINI - CHICAGO MERCANTILE EXCHANGE': 'NQ=F',
    'RUSSELL E-MINI - CHICAGO MERCANTILE EXCHANGE': 'RTY=F',
    'DJIA x $5 - CHICAGO BOARD OF TRADE': 'YM=F',
    'NIKKEI STOCK AVERAGE - CHICAGO MERCANTILE EXCHANGE': 'NKD=F',
    # Bonds & Rates
    'UST 10Y NOTE - CHICAGO BOARD OF TRADE': 'ZN=F',
    'UST 2Y NOTE - CHICAGO BOARD OF TRADE': 'ZT=F',
    'UST 5Y NOTE - CHICAGO BOARD OF TRADE': 'ZF=F',
    'UST BOND - CHICAGO BOARD OF TRADE': 'ZB=F',
    'ULTRA UST 10Y - CHICAGO BOARD OF TRADE': 'TN=F',
    'ULTRA US T BOND - CHICAGO BOARD OF TRADE': 'UB=F',
    # Crypto
    'BITCOIN - CHICAGO MERCANTILE EXCHANGE': 'BTC=F',
    'ETHER CASH SETTLED - CHICAGO MERCANTILE EXCHANGE': 'ETH=F',
    # Dairy
    'BUTTER (CASH SETTLED) - CHICAGO MERCANTILE EXCHANGE': 'CB=F',
    'MILK, Class III - CHICAGO MERCANTILE EXCHANGE': 'DC=F',
}

# ─────────────────────────────────────────────────────────────────────
# CATEGORY LOGIC
# ─────────────────────────────────────────────────────────────────────

def categorize(name):
    n = name.upper()
    if any(k in n for k in ['BITCOIN','ETHER','SHIB','DOGECOIN','SOLANA','SOL ','CARDONA',
        'CHAINLINK','LITECOIN','POLKADOT','AVALANCHE','XRP','ZCASH','STELLAR','HEDERA',
        'SUI ','NANO BITCOIN','NANO ETHER','NANO SOL','NANO XRP','NANO STELLAR',
        'COINBASE','LMX LABS']): return 'Crypto'
    if any(k in n for k in ['GOLD','SILVER','COPPER','PLATINUM','PALLADIUM','ALUMINUM',
        'STEEL','COBALT','LITHIUM','FERROUS']): return 'Metals'
    if any(k in n for k in ['CRUDE','WTI','BRENT','GASOLINE','RBOB','ULSD','HEATING',
        'HENRY HUB','NAT GAS','NATURAL GAS','PROPANE','ETHANOL','BUTANE','ETHANE',
        'ETHYLENE','FUEL OIL','JET','CONDENSATE','MARINE','HSFO']): return 'Energy'
    if any(k in n for k in ['PJM','ERCOT','MISO','NYISO','ISO NE','CAISO','MID-C',
        'PALO VERDE','SPP ','NODAL','CARBON','RGGI','REC','SREC','AEC','GREEN-E',
        'D4 ','D6 ','RIN']): return 'Power & Emissions'
    if any(k in n for k in ['BASIS','INDEX','SONAT','TRANSCO','TETCO','WAHA','MALIN',
        'MICHCON','ALGONQUIN','CHICAGO CITY','CIG ROCKIES','DOMINION','EP SAN JUAN',
        'FLORIDA GAS','HSC ','HOUSTON SHIP','NGPL','NNG VENTURA','NWP','ONEOK',
        'PANHANDLE','PG&E','REX ZONE','SOCAL','TCO ','TENNESSEE','TGT ZONE',
        'CG MAINLINE','AECO','CHICAGO FIN']): return 'Nat Gas Basis'
    if any(k in n for k in ['WHEAT','CORN','SOYBEAN','OATS','RICE','COTTON','SUGAR',
        'COFFEE','COCOA','ORANGE JUICE','LUMBER','CANOLA','PALM OIL','LEAN HOGS',
        'LIVE CATTLE','FEEDER CATTLE','MILK','BUTTER','CHEESE','NON FAT DRY']): return 'Agriculture'
    if any(k in n for k in ['DOLLAR','EURO FX','JAPANESE YEN','BRITISH POUND','SWISS FRANC',
        'CANADIAN','MEXICAN PESO','BRAZILIAN REAL','AUSTRALIAN','NZ DOLLAR',
        'SO AFRICAN RAND','USD INDEX']): return 'Currencies'
    if any(k in n for k in ['S&P 500','S&P 400','NASDAQ','DJIA','DOW JONES','RUSSELL',
        'NIKKEI','VIX','MSCI','E-MINI S&P']): return 'Equity Indices'
    if any(k in n for k in ['UST ','ULTRA US','FED FUNDS','SOFR','ERIS','T BOND',
        '10Y NOTE','2Y NOTE','5Y NOTE','MICRO 10 YEAR','EURO SHORT','INT RATE']): return 'Bonds & Rates'
    return 'Other'

# ─────────────────────────────────────────────────────────────────────
# DOWNLOAD CFTC DATA
# ─────────────────────────────────────────────────────────────────────

def download_cftc():
    """Download current + previous year CFTC Legacy Futures-Only CSVs."""
    now = datetime.now()
    years = [now.year, now.year - 1]
    frames = []

    for yr in years:
        url = f"https://www.cftc.gov/files/dea/history/deacot{yr}.zip"
        print(f"  Downloading {url} ...", end=" ", flush=True)
        try:
            req = Request(url, headers={'User-Agent': 'Mozilla/5.0 (COT Updater)'})
            resp = urlopen(req)
            z = zipfile.ZipFile(io.BytesIO(resp.read()))
            for name in z.namelist():
                if name.endswith('.txt'):
                    df = pd.read_csv(z.open(name))
                    df.columns = df.columns.str.strip().str.strip('"')
                    frames.append(df)
                    print(f"OK ({len(df)} rows)")
        except Exception as e:
            print(f"SKIP ({e})")

    if not frames:
        print("ERROR: No CFTC data downloaded!")
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)
    # Deduplicate (both zips may share overlapping rows)
    df = df.drop_duplicates(subset=['Market and Exchange Names', 'As of Date in Form YYYY-MM-DD'])
    return df


# ─────────────────────────────────────────────────────────────────────
# PROCESS
# ─────────────────────────────────────────────────────────────────────

def process(df):
    df['date'] = pd.to_datetime(df['As of Date in Form YYYY-MM-DD'])
    df['symbol'] = df['Market and Exchange Names'].str.strip()
    df['nc_long'] = pd.to_numeric(df['Noncommercial Positions-Long (All)'], errors='coerce')
    df['nc_short'] = pd.to_numeric(df['Noncommercial Positions-Short (All)'], errors='coerce')
    df['oi'] = pd.to_numeric(df['Open Interest (All)'], errors='coerce')
    df['chg_nc_long'] = pd.to_numeric(df['Change in Noncommercial-Long (All)'], errors='coerce')
    df['chg_nc_short'] = pd.to_numeric(df['Change in Noncommercial-Short (All)'], errors='coerce')
    df['net_pos'] = df['nc_long'] - df['nc_short']
    df['chg_net_pos'] = df['chg_nc_long'] - df['chg_nc_short']
    df['category'] = df['symbol'].apply(categorize)

    df = df.sort_values(['symbol', 'date']).reset_index(drop=True)

    max_date = df['date'].max()
    cutoff = max_date - timedelta(weeks=LOOKBACK_WEEKS)
    df = df[df['date'] >= cutoff].copy()

    print(f"  Date range: {df['date'].min().date()} → {df['date'].max().date()}")
    print(f"  Symbols: {df['symbol'].nunique()}")
    return df


# ─────────────────────────────────────────────────────────────────────
# FETCH PRICES
# ─────────────────────────────────────────────────────────────────────

def fetch_prices(df):
    import yfinance as yf

    cot_dates = sorted(df['date'].unique())
    start = pd.Timestamp(cot_dates[0]) - timedelta(days=7)
    end = pd.Timestamp(cot_dates[-1]) + timedelta(days=1)

    tickers = list(set(TICKER_MAP.values()))
    print(f"  Fetching prices for {len(tickers)} tickers ...", flush=True)

    price_data = {}
    try:
        raw = yf.download(tickers, start=start, end=end,
                          progress=False, auto_adjust=True, threads=True)
        if len(tickers) == 1:
            price_data[tickers[0]] = raw['Close']
        else:
            close = raw['Close']
            for tk in tickers:
                if tk in close.columns:
                    s = close[tk].dropna()
                    if len(s) > 0:
                        price_data[tk] = s
    except Exception as e:
        print(f"  Price fetch error: {e}")

    print(f"  Got prices for {len(price_data)} tickers")
    return price_data


def get_price(price_data, ticker, target_date):
    if ticker not in price_data:
        return None
    s = price_data[ticker]
    mask = s.index <= target_date
    if mask.any():
        return float(s[mask].iloc[-1])
    return None


# ─────────────────────────────────────────────────────────────────────
# BUILD JSON
# ─────────────────────────────────────────────────────────────────────

def build_json(df, price_data):
    symbols_data = {}
    for sym, grp in df.groupby('symbol'):
        grp = grp.sort_values('date')
        yf_ticker = TICKER_MAP.get(sym)
        cat = grp['category'].iloc[0]

        weeks = []
        for _, row in grp.iterrows():
            d = row['date']
            price = get_price(price_data, yf_ticker, d) if yf_ticker else None
            w = [
                d.strftime('%Y-%m-%d'),
                int(row['nc_long']) if pd.notna(row['nc_long']) else 0,
                int(row['nc_short']) if pd.notna(row['nc_short']) else 0,
                int(row['net_pos']) if pd.notna(row['net_pos']) else 0,
                int(row['chg_net_pos']) if pd.notna(row['chg_net_pos']) else 0,
                int(row['chg_nc_long']) if pd.notna(row['chg_nc_long']) else 0,
                int(row['chg_nc_short']) if pd.notna(row['chg_nc_short']) else 0,
                int(row['oi']) if pd.notna(row['oi']) else 0,
                round(price, 4) if price else None,
            ]
            weeks.append(w)

        if len(weeks) >= 2:
            symbols_data[sym] = {
                'c': cat,
                'hp': yf_ticker is not None and any(w[8] is not None for w in weeks),
                'w': weeks,
            }

    sym_list = []
    for sym in sorted(symbols_data):
        info = symbols_data[sym]
        sym_list.append({'name': sym, 'cat': info['c'], 'hp': info['hp'], 'nw': len(info['w'])})

    wp = sum(1 for v in symbols_data.values() if v['hp'])
    print(f"  {len(symbols_data)} symbols ({wp} with price)")
    return symbols_data, sym_list


# ─────────────────────────────────────────────────────────────────────
# GENERATE HTML
# ─────────────────────────────────────────────────────────────────────

def generate_html(symbols_data, sym_list, output_path):
    data_js = f"const COT_DATA = {json.dumps(symbols_data, separators=(',',':'))};\n"
    data_js += f"const SYM_LIST = {json.dumps(sym_list, separators=(',',':'))};\n"

    generated = datetime.now().strftime('%Y-%m-%d %H:%M')

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>COT Report — Non-Commercial Positioning ({LOOKBACK_WEEKS} Weeks)</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0f1117; --bg2: #1a1d27; --bg3: #242835;
    --fg: #e4e4e7; --fg2: #a1a1aa; --fg3: #71717a;
    --accent: #818cf8; --green: #34d399; --red: #f87171;
    --blue: #60a5fa; --orange: #fb923c; --yellow: #fbbf24;
    --border: #2e3240;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--fg); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }}
  .header {{ padding: 20px 24px 16px; border-bottom: 1px solid var(--border); }}
  .header h1 {{ font-size: 20px; font-weight: 600; color: var(--fg); margin-bottom: 4px; }}
  .header p {{ color: var(--fg3); font-size: 13px; }}
  .controls {{ display: flex; gap: 12px; padding: 16px 24px; flex-wrap: wrap; align-items: center; border-bottom: 1px solid var(--border); }}
  .controls select, .controls input {{ background: var(--bg2); border: 1px solid var(--border); color: var(--fg); padding: 8px 12px; border-radius: 6px; font-size: 13px; outline: none; }}
  .controls select:focus, .controls input:focus {{ border-color: var(--accent); }}
  .controls select {{ min-width: 160px; }}
  #symbolSelect {{ min-width: 400px; }}
  .controls input {{ min-width: 200px; }}
  .controls label {{ color: var(--fg3); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .ctrl-group {{ display: flex; flex-direction: column; gap: 4px; }}
  .nav-btns {{ display: flex; gap: 6px; align-items: flex-end; }}
  .nav-btns button {{ background: var(--bg3); border: 1px solid var(--border); color: var(--fg); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; }}
  .nav-btns button:hover {{ background: var(--accent); color: #fff; }}
  .counter {{ color: var(--fg3); font-size: 12px; align-self: flex-end; padding-bottom: 2px; }}
  .summary-row {{ display: flex; gap: 12px; padding: 16px 24px; flex-wrap: wrap; }}
  .stat-card {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: 12px 16px; min-width: 150px; flex: 1; }}
  .stat-card .label {{ color: var(--fg3); font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }}
  .stat-card .value {{ font-size: 20px; font-weight: 600; }}
  .stat-card .sub {{ color: var(--fg3); font-size: 12px; margin-top: 2px; }}
  .pos {{ color: var(--green); }} .neg {{ color: var(--red); }}
  .chart-container {{ padding: 16px 24px; }}
  .chart-wrap {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; padding: 16px; height: 340px; position: relative; }}
  .table-container {{ padding: 0 24px 24px; }}
  .tbl-wrap {{ background: var(--bg2); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  thead th {{ background: var(--bg3); color: var(--fg2); font-weight: 600; text-transform: uppercase; font-size: 11px; letter-spacing: 0.5px; padding: 10px 12px; text-align: right; position: sticky; top: 0; z-index: 1; }}
  thead th:first-child {{ text-align: left; }}
  tbody td {{ padding: 8px 12px; border-top: 1px solid var(--border); text-align: right; font-variant-numeric: tabular-nums; }}
  tbody td:first-child {{ text-align: left; color: var(--fg2); }}
  tbody tr:hover {{ background: rgba(129,140,248,0.06); }}
  .tbl-scroll {{ max-height: 500px; overflow-y: auto; }}
  .tbl-scroll::-webkit-scrollbar {{ width: 6px; }}
  .tbl-scroll::-webkit-scrollbar-thumb {{ background: var(--bg3); border-radius: 3px; }}
  .bar {{ display: inline-block; height: 10px; border-radius: 2px; vertical-align: middle; margin-right: 4px; min-width: 2px; }}
  .bar-pos {{ background: var(--green); }} .bar-neg {{ background: var(--red); }}
</style>
</head>
<body>
<div class="header">
  <h1>CFTC Commitment of Traders — Non-Commercial Positioning</h1>
  <p>Legacy Futures-Only Report · Last {LOOKBACK_WEEKS} Weeks · Generated {generated}</p>
</div>
<div class="controls">
  <div class="ctrl-group"><label>Category</label><select id="catSelect"><option value="All">All Categories</option></select></div>
  <div class="ctrl-group"><label>Symbol</label><select id="symbolSelect"></select></div>
  <div class="ctrl-group"><label>Search</label><input id="searchBox" type="text" placeholder="Type to filter symbols..."></div>
  <div class="nav-btns"><button id="prevBtn">&#8592; Prev</button><button id="nextBtn">Next &#8594;</button></div>
  <div class="counter" id="counter"></div>
</div>
<div class="summary-row" id="summaryRow"></div>
<div class="chart-container"><div class="chart-wrap"><canvas id="mainChart"></canvas></div></div>
<div class="table-container"><div class="tbl-wrap"><div class="tbl-scroll" id="tableScroll"></div></div></div>
<script>
{data_js}
let filteredSymbols=[];let currentIndex=0;let chart=null;
const categories=['All',...new Set(SYM_LIST.map(s=>s.cat))].sort((a,b)=>{{if(a==='All')return -1;if(b==='All')return 1;const order=['Metals','Energy','Agriculture','Currencies','Equity Indices','Bonds & Rates','Crypto','Nat Gas Basis','Power & Emissions','Other'];return order.indexOf(a)-order.indexOf(b);}});
const catSel=document.getElementById('catSelect');const symSel=document.getElementById('symbolSelect');const searchBox=document.getElementById('searchBox');
categories.forEach(c=>{{if(c==='All')return;const o=document.createElement('option');o.value=c;o.textContent=c;catSel.appendChild(o);}});
function fmt(n){{if(n==null)return'\\u2014';return n.toLocaleString('en-US');}}
function fmtSigned(n){{if(n==null)return'\\u2014';return(n>=0?'+':'')+n.toLocaleString('en-US');}}
function fmtPrice(p){{if(p==null)return'\\u2014';if(Math.abs(p)>=100)return p.toLocaleString('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}});if(Math.abs(p)>=1)return p.toLocaleString('en-US',{{minimumFractionDigits:4,maximumFractionDigits:4}});return p.toLocaleString('en-US',{{minimumFractionDigits:6,maximumFractionDigits:6}});}}
function updateSymbolList(){{const cat=catSel.value;const q=searchBox.value.toLowerCase().trim();filteredSymbols=SYM_LIST.filter(s=>{{if(cat!=='All'&&s.cat!==cat)return false;if(q&&!s.name.toLowerCase().includes(q))return false;return true;}});symSel.innerHTML='';filteredSymbols.forEach((s,i)=>{{const o=document.createElement('option');o.value=i;o.textContent=s.name+(s.hp?' \\u25cf':'');symSel.appendChild(o);}});document.getElementById('counter').textContent=filteredSymbols.length+' symbols';if(filteredSymbols.length>0){{currentIndex=0;symSel.value=0;renderSymbol(filteredSymbols[0].name);}}else{{document.getElementById('summaryRow').innerHTML='';document.getElementById('tableScroll').innerHTML='<p style="padding:20px;color:var(--fg3)">No symbols found</p>';if(chart){{chart.destroy();chart=null;}}}}}}
function renderSymbol(name){{const info=COT_DATA[name];if(!info)return;const weeks=info.w;const first=weeks[0];const last=weeks[weeks.length-1];const hasPrice=info.hp&&weeks.some(w=>w[8]!=null);const netChg52=last[3]-first[3];const longChg52=last[1]-first[1];const shortChg52=last[2]-first[2];const pctOI=last[7]>0?((last[3]/last[7])*100).toFixed(1):'\\u2014';let priceHtml='';if(hasPrice){{const fp=weeks.find(w=>w[8]!=null);const lp=[...weeks].reverse().find(w=>w[8]!=null);if(fp&&lp&&fp[8]&&lp[8]){{const pchg=((lp[8]-fp[8])/fp[8]*100).toFixed(2);const cls=pchg>=0?'pos':'neg';priceHtml=`<div class="stat-card"><div class="label">Price</div><div class="value">${{fmtPrice(lp[8])}}</div><div class="sub ${{cls}}">${{pchg>=0?'+':''}}${{pchg}}% over period</div></div>`;}}}}document.getElementById('summaryRow').innerHTML=`<div class="stat-card"><div class="label">Current Net Position</div><div class="value ${{last[3]>=0?'pos':'neg'}}">${{fmt(last[3])}}</div><div class="sub">${{pctOI}}% of OI</div></div><div class="stat-card"><div class="label">52W Net Change</div><div class="value ${{netChg52>=0?'pos':'neg'}}">${{fmtSigned(netChg52)}}</div><div class="sub">Long ${{fmtSigned(longChg52)}} / Short ${{fmtSigned(shortChg52)}}</div></div><div class="stat-card"><div class="label">Current Longs</div><div class="value">${{fmt(last[1])}}</div><div class="sub">WoW ${{fmtSigned(last[5])}}</div></div><div class="stat-card"><div class="label">Current Shorts</div><div class="value">${{fmt(last[2])}}</div><div class="sub">WoW ${{fmtSigned(last[6])}}</div></div>${{priceHtml}}<div class="stat-card"><div class="label">Open Interest</div><div class="value">${{fmt(last[7])}}</div><div class="sub">${{info.c}}</div></div>`;if(chart)chart.destroy();const ctx=document.getElementById('mainChart').getContext('2d');const labels=weeks.map(w=>w[0]);const datasets=[{{label:'Net Position',data:weeks.map(w=>w[3]),borderColor:'#818cf8',backgroundColor:'rgba(129,140,248,0.1)',fill:true,tension:0.3,pointRadius:2,yAxisID:'y',order:1}}];const scales={{x:{{ticks:{{color:'#71717a',maxRotation:45,font:{{size:10}}}},grid:{{color:'rgba(46,50,64,0.5)'}}}},y:{{position:'left',ticks:{{color:'#818cf8',font:{{size:10}},callback:v=>v>=1000||v<=-1000?(v/1000).toFixed(0)+'K':v}},grid:{{color:'rgba(46,50,64,0.5)'}},title:{{display:true,text:'Net Position',color:'#818cf8',font:{{size:11}}}}}}}};if(hasPrice){{const prices=weeks.map(w=>w[8]);datasets.push({{label:'Price',data:prices,borderColor:'#fbbf24',borderWidth:2,pointRadius:1,tension:0.3,yAxisID:'y1',order:0,spanGaps:true}});scales.y1={{position:'right',ticks:{{color:'#fbbf24',font:{{size:10}}}},grid:{{drawOnChartArea:false}},title:{{display:true,text:'Price',color:'#fbbf24',font:{{size:11}}}}}};}}chart=new Chart(ctx,{{type:'line',data:{{labels,datasets}},options:{{responsive:true,maintainAspectRatio:false,interaction:{{mode:'index',intersect:false}},plugins:{{legend:{{labels:{{color:'#a1a1aa',font:{{size:11}},usePointStyle:true,pointStyle:'line'}}}},tooltip:{{backgroundColor:'#1a1d27',titleColor:'#e4e4e7',bodyColor:'#a1a1aa',borderColor:'#2e3240',borderWidth:1,callbacks:{{label:ctx=>ctx.dataset.label+': '+(ctx.dataset.yAxisID==='y1'?fmtPrice(ctx.raw):fmt(ctx.raw))}}}}}},scales}}}});const maxAbsChg=Math.max(...weeks.map(w=>Math.abs(w[4])),1);let rows='';for(let i=weeks.length-1;i>=0;i--){{const w=weeks[i];const barW=Math.round(Math.abs(w[4])/maxAbsChg*60);const barCls=w[4]>=0?'bar-pos':'bar-neg';const priceTd=hasPrice?`<td>${{w[8]!=null?fmtPrice(w[8]):'\\u2014'}}</td>`:'';const priceChgTd=hasPrice&&i<weeks.length-1?(()=>{{const prev=weeks.slice(0,i).reverse().find(pw=>pw[8]!=null);if(!prev||!w[8])return'<td>\\u2014</td>';const chg=((w[8]-prev[8])/prev[8]*100).toFixed(2);return`<td class="${{chg>=0?'pos':'neg'}}">${{chg>=0?'+':''}}${{chg}}%</td>`;}})():(hasPrice?'<td>\\u2014</td>':'');rows+=`<tr><td>${{w[0]}}</td>${{priceTd}}${{priceChgTd}}<td>${{fmt(w[1])}}</td><td>${{fmt(w[2])}}</td><td class="${{w[3]>=0?'pos':'neg'}}">${{fmt(w[3])}}</td><td><span class="bar ${{barCls}}" style="width:${{barW}}px"></span><span class="${{w[4]>=0?'pos':'neg'}}">${{fmtSigned(w[4])}}</span></td><td class="${{w[5]>=0?'pos':'neg'}}">${{fmtSigned(w[5])}}</td><td class="${{w[6]>=0?'pos':'neg'}}">${{fmtSigned(w[6])}}</td><td>${{fmt(w[7])}}</td></tr>`;}}const priceHeaders=hasPrice?'<th>Price</th><th>Price Chg%</th>':'';document.getElementById('tableScroll').innerHTML=`<table><thead><tr><th>Report Date</th>${{priceHeaders}}<th>NC Long</th><th>NC Short</th><th>Net Pos</th><th>WoW \\u0394 Net</th><th>WoW \\u0394 Long</th><th>WoW \\u0394 Short</th><th>Open Int</th></tr></thead><tbody>${{rows}}</tbody></table>`;}}
catSel.addEventListener('change',()=>{{searchBox.value='';updateSymbolList();}});searchBox.addEventListener('input',updateSymbolList);symSel.addEventListener('change',()=>{{currentIndex=parseInt(symSel.value);renderSymbol(filteredSymbols[currentIndex].name);}});document.getElementById('prevBtn').addEventListener('click',()=>{{if(filteredSymbols.length===0)return;currentIndex=(currentIndex-1+filteredSymbols.length)%filteredSymbols.length;symSel.value=currentIndex;renderSymbol(filteredSymbols[currentIndex].name);}});document.getElementById('nextBtn').addEventListener('click',()=>{{if(filteredSymbols.length===0)return;currentIndex=(currentIndex+1)%filteredSymbols.length;symSel.value=currentIndex;renderSymbol(filteredSymbols[currentIndex].name);}});document.addEventListener('keydown',e=>{{if(e.target.tagName==='INPUT')return;if(e.key==='ArrowLeft')document.getElementById('prevBtn').click();if(e.key==='ArrowRight')document.getElementById('nextBtn').click();}});
updateSymbolList();
</script>
</body>
</html>'''
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"  Saved: {output_path} ({os.path.getsize(output_path)/1024:.0f} KB)")


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='COT Weekly Updater')
    parser.add_argument('-o', '--output-dir', default='.', help='Output directory (default: current)')
    parser.add_argument('-f', '--filename', default='cot_viewer.html', help='Output filename')
    args = parser.parse_args()

    output_path = os.path.join(args.output_dir, args.filename)
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  COT WEEKLY UPDATER — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    print("\n[1/4] Downloading CFTC data...")
    df = download_cftc()

    print("\n[2/4] Processing...")
    df = process(df)

    print("\n[3/4] Fetching prices...")
    price_data = fetch_prices(df)

    print("\n[4/4] Building HTML...")
    symbols_data, sym_list = build_json(df, price_data)
    generate_html(symbols_data, sym_list, output_path)

    print(f"\n{'='*60}")
    print(f"  DONE! Open {output_path} in your browser.")
    print(f"{'='*60}\n")


if __name__ == '__main__':
    main()
