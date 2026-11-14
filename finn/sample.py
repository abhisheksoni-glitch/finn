"""Offline sample snapshot so the app runs anywhere with zero setup.

Inputs (prices, filings, financial tables, transcript excerpts) are SYNTHETIC
and illustrative; they are pushed through the real engine (classifier, scorer,
results card, research numbers, alert rules). `meta.source = "sample"` makes
the UI show a banner. Run `python -m finn build` for live data.
"""
import json
import math
import random
from datetime import datetime, timedelta

from . import settings
from .engine import alerts as al
from .engine import research, results, triage
from .engine.retrieval import chunk_pages

AS_OF = datetime(2026, 11, 13, 20, 30)
QCOLS = ["Sep 2024", "Dec 2024", "Mar 2025", "Jun 2025", "Sep 2025", "Dec 2025", "Mar 2026", "Jun 2026", "Sep 2026"]
YCOLS = ["Mar 2021", "Mar 2022", "Mar 2023", "Mar 2024", "Mar 2025", "Mar 2026", "TTM"]

BASE_PX = {"RELIANCE": 1480, "HDFCBANK": 1010, "INFY": 1590, "BHARTIARTL": 2060, "LT": 3920,
           "BAJFINANCE": 1015, "SUNPHARMA": 1740, "TITAN": 3810, "MARUTI": 15900, "ULTRACEMCO": 12100,
           "POLYCAB": 8650, "DIXON": 15400, "PERSISTENT": 6150, "TRENT": 4480, "DEEPAKNTR": 1890,
           "IEX": 142, "KAYNES": 6900, "CDSL": 1610}

# symbol -> {date: (return %, volume multiple)}
EVENTS = {"POLYCAB": {"2026-11-13": (7.8, 3.4)}, "DIXON": {"2026-11-13": (-6.1, 2.7)},
          "IEX": {"2026-11-13": (-9.2, 4.1)}, "KAYNES": {"2026-11-11": (5.1, 2.3)},
          "LT": {"2026-11-13": (2.2, 1.9)}, "PERSISTENT": {"2026-11-13": (-5.3, 2.4)}, "TRENT": {"2026-11-12": (-4.4, 1.7)},
          "HDFCBANK": {"2026-10-20": (3.1, 2.1)}, "SUNPHARMA": {"2026-10-28": (-4.6, 2.4)},
          "DEEPAKNTR": {"2026-10-09": (6.3, 3.0)}, "BAJFINANCE": {"2026-09-30": (-5.2, 2.2)}}


def sessions(n=130):
    d, out = AS_OF.date(), []
    while len(out) < n:
        if d.weekday() < 5 and d <= datetime(2026, 11, 13).date():
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def make_prices():
    rnd = random.Random(7)
    days = sessions()
    px = {}
    for s, base in BASE_PX.items():
        c = base * (0.88 + 0.1 * rnd.random())
        v0 = rnd.randint(4, 60) * 10 ** rnd.choice([4, 5])
        rows = []
        drift = rnd.uniform(-0.0004, 0.0012)
        for d in days:
            ds = d.isoformat()
            ev = EVENTS.get(s, {}).get(ds)
            r = ev[0] / 100 if ev else rnd.gauss(drift, 0.012)
            r = max(min(r, 0.038), -0.038) if not ev else r
            c *= 1 + r
            vm = ev[1] if ev else math.exp(rnd.gauss(0, 0.28))
            rows.append({"d": ds, "c": round(c, 2), "v": int(v0 * vm)})
        k = base / rows[-1]["c"]
        for r in rows:
            r["c"] = round(r["c"] * k, 2)
        px[s] = rows
    return px


def ts(day, hh, mm=0):
    return (AS_OF - timedelta(days=day)).replace(hour=hh, minute=mm).strftime("%d-%b-%Y %H:%M:%S")


def F(sym, desc, text, day, hh, mm=0, pdf=True):
    return {"symbol": sym, "desc": desc, "attchmntText": text, "an_dt": ts(day, hh, mm),
            "attchmntFile": f"https://nsearchives.nseindia.com/corporate/{sym}_{day}{hh}{mm}.pdf" if pdf else ""}


CO = {h: n for h, n in [("RELIANCE", "Reliance Industries Limited"), ("HDFCBANK", "HDFC Bank Limited"),
      ("INFY", "Infosys Limited"), ("BHARTIARTL", "Bharti Airtel Limited"), ("LT", "Larsen & Toubro Limited"),
      ("BAJFINANCE", "Bajaj Finance Limited"), ("SUNPHARMA", "Sun Pharmaceutical Industries Limited"),
      ("TITAN", "Titan Company Limited"), ("MARUTI", "Maruti Suzuki India Limited"),
      ("ULTRACEMCO", "UltraTech Cement Limited"), ("POLYCAB", "Polycab India Limited"),
      ("DIXON", "Dixon Technologies (India) Limited"), ("PERSISTENT", "Persistent Systems Limited"),
      ("TRENT", "Trent Limited"), ("DEEPAKNTR", "Deepak Nitrite Limited"), ("IEX", "Indian Energy Exchange Limited"),
      ("KAYNES", "Kaynes Technology India Limited"), ("CDSL", "Central Depository Services (India) Limited")]}


def inf(sym, rest):
    return f"{CO[sym]} has informed the Exchange regarding {rest}"


def raw_filings():
    R = []
    R += [F("POLYCAB", "Financial Result Updates", inf("POLYCAB", "Unaudited Financial Results (Standalone and Consolidated) for the quarter and half year ended September 30, 2026."), 0, 13, 42),
          F("HDFCBANK", "Financial Result Updates", inf("HDFCBANK", "Unaudited Financial Results (Standalone and Consolidated) for the quarter ended September 30, 2026."), 3, 16, 5),
          F("TRENT", "Outcome of Board Meeting", inf("TRENT", "outcome of the Board Meeting held on November 12, 2026 wherein the Board approved the Unaudited Financial Results for the quarter ended September 30, 2026."), 1, 14, 10),
          F("DIXON", "Change in Directors/ Key Managerial Personnel/ Auditor/ Compliance Officer/ Share Transfer Agent", inf("DIXON", "resignation of Mr. Saurabh Gupta as Chief Financial Officer and appointment of Ms. Ananya Krishnan as Chief Financial Officer and Key Managerial Personnel of the Company with effect from December 1, 2026."), 1, 21, 15),
          F("IEX", "Litigation/ Dispute/ Regulatory Action", inf("IEX", "receipt of an order from the Central Electricity Regulatory Commission directing implementation of market coupling for the day-ahead market in a phased manner beginning January 2027. The Company is evaluating legal remedies."), 1, 21, 2),
          F("LT", "Press Release", inf("LT", "the press release titled 'L&T wins a mega order for a 765 kV transmission project'. As per the Company's classification, a mega order is valued above Rs. 7,000 crore."), 0, 9, 40),
          F("KAYNES", "Acquisition", inf("KAYNES", "execution of definitive agreements to acquire 100% stake in a Malaysian printed-circuit-board assembler for a consideration of Rs. 640 crore, subject to regulatory approvals."), 3, 19, 10),
          F("BAJFINANCE", "Credit Rating", inf("BAJFINANCE", "S&P Global Ratings has revised the outlook on the Company's long-term issuer credit rating to Positive from Stable; rating affirmed at BBB-."), 0, 12, 5),
          F("DEEPAKNTR", "Disclosure under SEBI Takeover Regulations", inf("DEEPAKNTR", "disclosure received from a Promoter Group entity under Regulation 29(2) for acquisition of 4,10,000 equity shares through open market purchases."), 2, 18, 30),
          F("SUNPHARMA", "Press Release", inf("SUNPHARMA", "receipt of USFDA approval for a specialty dermatology product; the product addresses a US market of approximately USD 450 million."), 5, 8, 15),
          F("ULTRACEMCO", "Updates", inf("ULTRACEMCO", "commencement of commercial production at its 3.35 mtpa brownfield clinker capacity expansion in Chhattisgarh, taking total grey cement capacity to 192.3 mtpa."), 3, 11, 0),
          F("TITAN", "Dividend", inf("TITAN", "declaration of an Interim Dividend of Rs. 6 per equity share; Record Date fixed as November 24, 2026."), 6, 17, 0),
          F("CDSL", "Board Meeting Intimation", inf("CDSL", "a meeting of the Board of Directors scheduled on November 18, 2026, inter alia, to consider and approve the financial results for the quarter ended September 30, 2026."), 2, 10, 0),
          F("BHARTIARTL", "Allotment of Securities", inf("BHARTIARTL", "allotment of listed, unsecured, rated, redeemable non-convertible debentures aggregating Rs. 1,000 crore on a private placement basis."), 3, 19, 0),
          F("RELIANCE", "Analysts/Institutional Investor Meet/Con. Call Updates", inf("RELIANCE", "transcript of the Earnings Conference Call held on October 17, 2026."), 6, 9, 30),
          F("PERSISTENT", "Change in Directors/ Key Managerial Personnel/ Auditor/ Compliance Officer/ Share Transfer Agent", inf("PERSISTENT", "appointment of Mr. Vikram Rao as an Independent Director of the Company for a term of five years."), 4, 16, 0),
          F("INFY", "Press Release", inf("INFY", "the press release titled 'Infosys collaborates with a European bank on AI-first core modernisation'."), 2, 7, 45),
          F("MARUTI", "Updates", inf("MARUTI", "production volumes for the month of October 2026."), 6, 15, 0),
          F("POLYCAB", "Credit Rating", inf("POLYCAB", "CRISIL has reaffirmed the long-term rating at CRISIL AA+/Stable."), 5, 15, 0),
          F("KAYNES", "Pledge of shares", inf("KAYNES", "disclosure by a promoter regarding release of pledge on 1,20,000 equity shares."), 5, 18, 0)]
    routine = [
        ("Trading Window-XBRL", "closure of trading window"), ("Certificate under SEBI (Depositories and Participants) Regulations, 2018", "Certificate under Regulation 74 (5) of SEBI (DP) Regulations, 2018"),
        ("Copy of Newspaper Publication", "copies of newspaper publication of the financial results"), ("Analysts/Institutional Investor Meet/Con. Call Updates", "schedule of meeting with institutional investors"),
        ("Allotment of Securities", "allotment of equity shares under the Employee Stock Option Scheme"), ("Postal Ballot", "notice of postal ballot and e-voting"),
        ("Loss of Share Certificates", "loss of share certificates"), ("Analysts/Institutional Investor Meet/Con. Call Updates", "participation in an investor conference"),
        ("Compliances-Certificate under Reg. 74 (5) of SEBI (DP) Regulations, 2018", "compliance certificate"), ("Statement of deviation(s) or variation(s) under Reg. 32", "statement of deviation"),
    ]
    rnd = random.Random(3)
    syms = list(CO)
    for i in range(34):
        s = syms[rnd.randrange(len(syms))]
        d, t = routine[rnd.randrange(len(routine))]
        R.append(F(s, d, inf(s, t + "."), rnd.randint(0, 6), rnd.randint(9, 21), rnd.randint(0, 59), pdf=rnd.random() > 0.4))
    for i, r in enumerate(R):
        r["seq_id"] = str(104800000 + i)
    return R


def _q(rev_q, opm_q, other=0.015, dep=0.018, intr=0.006, tax=0.25):
    rows = {"Sales": [], "Expenses": [], "Operating Profit": [], "OPM %": [], "Other Income": [],
            "Interest": [], "Depreciation": [], "Profit before tax": [], "Tax %": [], "Net Profit": []}
    for r, m in zip(rev_q, opm_q):
        op = r * m / 100
        oi, dp, it = r * other, r * dep, r * intr
        pbt = op + oi - dp - it
        rows["Sales"].append(round(r)); rows["Expenses"].append(round(r - op)); rows["Operating Profit"].append(round(op))
        rows["OPM %"].append(round(m)); rows["Other Income"].append(round(oi)); rows["Interest"].append(round(it))
        rows["Depreciation"].append(round(dp)); rows["Profit before tax"].append(round(pbt)); rows["Tax %"].append(round(tax * 100))
        rows["Net Profit"].append(round(pbt * (1 - tax)))
    return {"cols": QCOLS, "rows": rows}


def _bank_q(nii, ppop, prov):
    rows = {"Revenue": [], "Interest": [], "Expenses": [], "Financing Profit": [], "Financing Margin %": [],
            "Other Income": [], "Depreciation": [], "Profit before tax": [], "Tax %": [], "Net Profit": []}
    for r, p, pv in zip(nii, ppop, prov):
        pbt = p - pv
        rows["Revenue"].append(round(r)); rows["Interest"].append(round(r * 0.52)); rows["Expenses"].append(round(r * 0.48 - p * 0.2))
        rows["Financing Profit"].append(round(p)); rows["Financing Margin %"].append(round(p / r * 100))
        rows["Other Income"].append(round(r * 0.2)); rows["Depreciation"].append(0)
        rows["Profit before tax"].append(round(pbt)); rows["Tax %"].append(24); rows["Net Profit"].append(round(pbt * 0.76))
    return {"cols": QCOLS, "rows": rows}


def _series(start, growth, n):
    out, v = [], start
    for g in growth[:n]:
        out.append(round(v))
        v *= 1 + g
    return out


def make_page(name, about, q, annual_rev, annual_opm, pat_margin, equity, debt, cfo_conv, cwip, days, ratios, docs=None):
    pl = {"Sales": annual_rev, "Operating Profit": [round(r * m / 100) for r, m in zip(annual_rev, annual_opm)],
          "OPM %": annual_opm, "Other Income": [round(r * 0.012) for r in annual_rev],
          "Net Profit": [round(r * m / 100) for r, m in zip(annual_rev, pat_margin)]}
    pat = pl["Net Profit"]
    cfo = [round(p * c) for p, c in zip(pat[:6], cfo_conv)]
    cfi = [round(-0.55 * x - 40) for x in cfo]
    bcols = YCOLS[:6]
    return {"name": name, "about": about, "basis": "consolidated",
            "url": f"https://www.screener.in/company/{name.split()[0].upper()}/consolidated/",
            "ratios": ratios,
            "tables": {"quarters": q,
                       "profit-loss": {"cols": YCOLS, "rows": pl},
                       "balance-sheet": {"cols": bcols, "rows": {"Equity Capital": [equity[0] * 0.02] * 6,
                                                                 "Reserves": equity, "Borrowings": debt, "CWIP": cwip}},
                       "cash-flow": {"cols": bcols, "rows": {"Cash from Operating Activity": cfo,
                                                             "Cash from Investing Activity": cfi}},
                       "ratios": {"cols": bcols, "rows": {k: v for k, v in days.items()}}},
            "docs": docs or {"annual_reports": [], "concalls": []}}


def pages():
    poly = make_page(
        "Polycab India Ltd", "Polycab manufactures wires and cables and fast-moving electrical goods (fans, lights, switches) and runs an EPC business.",
        _q([5498, 5226, 6986, 5906, 6478, 7636, 8340, 8210, 9420], [12.0, 13.1, 16.1, 13.6, 16.5, 13.4, 14.6, 13.8, 14.9]),
        [8792, 12204, 14108, 18039, 22408, 28360, 33606], [14.1, 11.0, 13.1, 13.8, 13.7, 14.6, 14.3],
        [10.0, 7.5, 9.1, 10.0, 9.1, 9.6, 9.5], [5212, 6052, 7166, 8784, 10343, 12460], [190, 169, 129, 180, 234, 610],
        [1.38, 0.23, 1.30, 0.67, 1.02, 0.71], [200, 240, 410, 614, 1100, 1980],
        {"Debtor Days": [45, 37, 40, 42, 44, 51], "Inventory Days": [115, 100, 108, 113, 112, 121],
         "Days Payable": [60, 45, 62, 70, 72, 68], "Cash Conversion Cycle": [100, 92, 86, 85, 84, 104],
         "Working Capital Days": [78, 69, 62, 59, 58, 71], "ROCE %": [21, 20, 27, 31, 30, 29]},
        {"Market Cap": 130100, "Current Price": 8650, "Stock P/E": 45.6, "ROCE": 29.4, "ROE": 22.1, "Dividend Yield": 0.4})
    hdfc = {"name": "HDFC Bank Ltd", "about": "", "basis": "consolidated", "ratios": {},
            "tables": {"quarters": _bank_q([76000, 77500, 78800, 80100, 81400, 82900, 84600, 85200, 87700],
                                           [25200, 26100, 27000, 27400, 27900, 28800, 29600, 29900, 31400],
                                           [2700, 3150, 3190, 3800, 4050, 3600, 3550, 3900, 3700])}}
    trent = {"name": "Trent Ltd", "about": "", "basis": "consolidated", "ratios": {},
             "tables": {"quarters": _q([4157, 4657, 4217, 4883, 4818, 5220, 4845, 5600, 5480],
                                       [16.2, 18.1, 15.3, 16.7, 16.9, 18.4, 15.9, 16.4, 15.1], other=0.02, dep=0.05, intr=0.025)}}
    asian = make_page(
        "Asian Paints Ltd", "Asian Paints makes decorative and industrial paints, waterproofing and home-decor products in India and 14 other markets.",
        _q([8028, 8550, 8359, 8939, 8513, 9104, 8730, 9301, 8815], [17.1, 18.9, 18.3, 19.4, 17.2, 18.6, 17.9, 19.0, 17.6], other=0.025, dep=0.035, intr=0.006),
        [21713, 29101, 34489, 35495, 33797, 35260, 35850], [21.9, 16.9, 18.8, 21.4, 18.2, 18.3, 18.0],
        [14.6, 10.7, 12.6, 15.3, 10.9, 11.3, 11.0], [15200, 15736, 17222, 19058, 19300, 20080], [1003, 1421, 2134, 2522, 2610, 2480],
        [1.04, 0.36, 1.06, 1.06, 1.27, 1.15], [560, 1300, 1800, 2400, 2100, 900],
        {"Debtor Days": [33, 32, 30, 33, 37, 38], "Inventory Days": [135, 136, 119, 112, 117, 119],
         "Days Payable": [118, 101, 96, 96, 101, 102], "Cash Conversion Cycle": [50, 67, 53, 49, 53, 55],
         "Working Capital Days": [24, 40, 36, 33, 38, 39], "ROCE %": [37, 29, 34, 37, 28, 27]},
        {"Market Cap": 238700, "Current Price": 2490, "Stock P/E": 60.4, "ROCE": 26.9, "ROE": 20.2, "Dividend Yield": 1.0})
    eternal = make_page(
        "Eternal Ltd", "Eternal runs Zomato (food delivery), Blinkit (quick commerce), District (going-out) and Hyperpure (B2B supplies).",
        _q([4799, 5405, 5833, 7167, 13590, 15620, 16980, 18420, 20110], [0.6, 1.1, 0.4, -0.2, -1.1, 0.4, 0.9, 1.4, 1.9], other=0.03, dep=0.04, intr=0.004),
        [1994, 4192, 7079, 12114, 20243, 54360, 71130], [-15.0, -21.0, -10.0, 0.4, 0.7, 0.4, 0.9],
        [-41.0, -29.0, -13.6, 2.9, 2.6, 1.0, 1.3], [8300, 16750, 19400, 20700, 29760, 31200], [0, 0, 0, 0, 1350, 1600],
        [-3.0, -1.2, -0.7, 2.1, 1.9, 1.1], [0, 0, 20, 90, 180, 420],
        {"Debtor Days": [12, 14, 15, 13, 11, 9], "Inventory Days": [0, 0, 2, 4, 9, 14],
         "Days Payable": [20, 22, 25, 28, 30, 31], "Cash Conversion Cycle": [-8, -8, -8, -11, -10, -8],
         "Working Capital Days": [-30, -20, -15, -12, -10, -6], "ROCE %": [-20, -8, -6, 1, 3, 2]},
        {"Market Cap": 287300, "Current Price": 296, "Stock P/E": 310, "ROCE": 2.4, "ROE": 1.9, "Dividend Yield": 0})
    hal = make_page(
        "Hindustan Aeronautics Ltd", "HAL designs, builds and maintains military aircraft, helicopters and aero-engines, mainly for India's armed forces.",
        _q([5976, 6957, 13700, 4347, 6629, 7699, 14760, 4819, 7310], [27.0, 29.4, 33.2, 23.8, 26.9, 30.1, 32.6, 22.4, 27.8], other=0.06, dep=0.05, intr=0.001),
        [22882, 24620, 26928, 30381, 30981, 33410, 34600], [25.0, 25.2, 26.6, 28.1, 31.2, 30.4, 30.9],
        [14.0, 20.5, 21.5, 25.0, 27.0, 26.3, 26.7], [17700, 20070, 23530, 28830, 33980, 39120], [0, 0, 0, 0, 0, 0],
        [3.4, 3.0, 1.3, 1.67, 0.17, 0.58], [1100, 1300, 1450, 1650, 1900, 2300],
        {"Debtor Days": [139, 83, 71, 65, 70, 112], "Inventory Days": [630, 500, 410, 380, 402, 430],
         "Days Payable": [110, 90, 70, 75, 72, 66], "Cash Conversion Cycle": [659, 493, 411, 370, 400, 476],
         "Working Capital Days": [-10, -40, -60, -75, -38, 12], "ROCE %": [27, 30, 30, 34, 36, 33]},
        {"Market Cap": 301500, "Current Price": 4510, "Stock P/E": 34.2, "ROCE": 33.1, "ROE": 24.8, "Dividend Yield": 0.8})
    return {"POLYCAB": poly, "HDFCBANK": hdfc, "TRENT": trent, "ASIANPAINT": asian, "ETERNAL": eternal, "HAL": hal}


def _src(page, calls):
    s = {"PL": {"title": "Annual P&L (reported)", "url": page["url"] + "#profit-loss"},
         "QR": {"title": "Quarterly results (reported)", "url": page["url"] + "#quarters"},
         "BS": {"title": "Balance sheet (reported)", "url": page["url"] + "#balance-sheet"},
         "CF": {"title": "Cash flow (reported)", "url": page["url"] + "#cash-flows"},
         "AR": {"title": "Annual Report FY26", "url": page["url"] + "#documents"}}
    for i, q in enumerate(calls, 1):
        s[f"T{i}"] = {"title": f"{q} earnings call transcript", "url": page["url"] + "#documents"}
    return s


CALLS = ["Q3 FY26", "Q4 FY26", "Q1 FY27", "Q2 FY27"]

TRANSCRIPTS = {
    "POLYCAB": [
        ["We remain confident of the Project Spring targets: we aim to grow revenue at 1.5 times the industry and deliver wires & cables EBITDA margin of 11 to 13 percent through FY30.",
         "FMEG will reach EBITDA breakeven in the next two to three quarters as fans and lights scale; switchgear continues to lead.",
         "Analysts pressed on the working capital build: inventory went up because we pre-bought copper ahead of the price increase, it will normalise by March."],
        ["Export revenue was soft this quarter because of the US tariff overhang; we expect exports to be 6 to 8 percent of revenue over time.",
         "Capex for FY27 will be Rs 1,600 to 1,800 crore, mainly for the cables capacity at Halol and the new EHV plant.",
         "Cable demand from power transmission, data centres and real estate remains very strong; we are running at high utilisation."],
        ["We delivered 39 percent revenue growth; wires & cables margin was 13.6 percent, at the top end of our guided band.",
         "FMEG EBITDA turned positive at 0.8 percent; we expect FMEG to stay profitable for the full year.",
         "On working capital, receivable days increased due to EPC project billing; this is temporary and linked to the BharatNet project."],
        ["Working capital days rose to 71 versus 58 last year; we expect it to come back toward 60 days by the end of the year as EPC collections come in.",
         "We are raising our aspiration: revenue for Project Spring will now be ahead of the 1.5x industry target.",
         "Wires & cables EBITDA margin for the quarter was 14.1 percent; we continue to guide 11 to 13 percent as a sustainable band."]],
    "ASIANPAINT": [
        ["Demand remained subdued in urban markets; we expect a gradual recovery and hope to return to double-digit volume growth by Q4.",
         "We guide for PBIT margin of 18 to 20 percent for the year; raw material prices are benign.",
         "Analysts focused on competitive intensity from new entrants and our dealer-incentive spend."],
        ["Volume growth was 1.8 percent for the quarter, value growth was negative due to down-trading to economy emulsions.",
         "We are investing behind brands and the network; we will protect market share even if margins are at the lower end of the band.",
         "The white cement and VAM backward integration projects are on schedule for commissioning in FY27."],
        ["Volume growth recovered to 3.9 percent; rural is ahead of urban. Value-volume gap remains wide because of mix.",
         "We maintain the PBIT margin guidance of 18 to 20 percent and expect low to mid single-digit value growth this year.",
         "Industrial coatings and home decor continue to grow faster than decorative paints."],
        ["We now expect high single-digit volume growth for the second half; value growth will lag volume by 4 to 5 percentage points.",
         "Capex intensity will come down after the VAM project; FY28 capex should be about half of FY27.",
         "Margins this quarter were impacted by higher advertising and promotion and price cuts in select categories."]],
}


def research_sample(sym, page, llm_mode=True):
    nums = research.numbers(page)
    q = nums["quarters"]
    srcs = _src(page, CALLS)
    chunks = []
    for i, paras in enumerate(TRANSCRIPTS.get(sym, []), 1):
        chunks += chunk_pages(paras, f"T{i}", srcs[f"T{i}"]["title"],
                              page_numbers=[3 + i] * len(paras))
    for c in chunks:
        c["id"] = c["id"]
    base = {"symbol": sym, "name": page["name"], "about": page["about"], "basis": "consolidated",
            "as_of": "2026-11-14", "numbers": nums, "sources": srcs, "chunks": chunks, "extracts": []}
    tr, ca, ba = nums["trajectory"], nums["cash"], nums["balance"]
    if not llm_mode:
        return {**base, "mode": "numbers_only", "analysis": research.heuristic_view(nums, [])}
    if sym == "POLYCAB":
        a = {"verdict": f"Growth is beating every promise (revenue {q[-1]['rev_yoy']:+.0f}% YoY), but working capital is quietly eating the cash: CFO was {ca['conversion'][-1]:.2f}× PAT in FY26.",
             "ledger": [
                 {"said_in": "Q3 FY26", "promise": "Grow faster than 1.5× the industry", "target": "1.5× industry", "horizon": "through FY30",
                  "delivered": f"Revenue +{q[-4]['rev_yoy']:.0f}%, +{q[-3]['rev_yoy']:.0f}%, +{q[-2]['rev_yoy']:.0f}%, +{q[-1]['rev_yoy']:.0f}% YoY over the next four quarters", "verdict": "delivered", "src": ["T1:p4", "QR"]},
                 {"said_in": "Q3 FY26", "promise": "Wires & cables EBITDA margin in an 11–13% band", "target": "11–13%", "horizon": "sustainable",
                  "delivered": f"Group OPM {q[-4]['opm']}–{max(x['opm'] for x in q[-4:])}% in the last four quarters; segment above the band twice", "verdict": "delivered", "src": ["T3:p6", "T4:p7", "QR"]},
                 {"said_in": "Q3 FY26", "promise": "FMEG at EBITDA breakeven within 2–3 quarters", "target": "breakeven", "horizon": "2–3 quarters",
                  "delivered": "Turned positive (0.8%) two quarters later, per Q1 FY27 call", "verdict": "delivered", "src": ["T1:p4", "T3:p6"]},
                 {"said_in": "Q3 FY26", "promise": "Inventory build will normalise by March", "target": "normal WC", "horizon": "Mar 2026",
                  "delivered": f"Working-capital days went the other way: {ba['wc_days'][-2]:.0f} → {ba['wc_days'][-1]:.0f}", "verdict": "missed", "src": ["T1:p4", "BS"]},
                 {"said_in": "Q4 FY26", "promise": "FY27 capex of ₹1,600–1,800 cr", "target": "₹1,600–1,800 cr", "horizon": "FY27",
                  "delivered": f"CWIP up to ₹{ba['cwip'][-1]:,.0f} cr from ₹{ba['cwip'][-2]:,.0f} cr; on track at H1", "verdict": "too_early", "src": ["T2:p5", "BS"]},
                 {"said_in": "Q1 FY27", "promise": "Receivables spike is temporary (EPC billing)", "target": "≈ 60 WC days", "horizon": "Mar 2027",
                  "delivered": "Still 71 days a quarter later; target now restated for year-end", "verdict": "walked_back", "src": ["T3:p6", "T4:p7"]}],
             "guidance_drift": "Growth aspiration raised (above 1.5× industry); margin band held at 11–13% despite running above it; working-capital normalisation date pushed out twice.",
             "narrative": [
                 {"claim": "Margins are structurally higher because of mix and scale", "numbers": f"OPM {tr['opm'][-4]}% → {tr['opm'][-2]}% over three years", "agree": True, "src": ["T3:p6", "PL"]},
                 {"claim": "The working-capital build is temporary", "numbers": f"Cash conversion cycle {ba['ccc'][-2]:.0f} → {ba['ccc'][-1]:.0f} days; CFO/PAT {ca['conversion'][-2]:.2f} → {ca['conversion'][-1]:.2f}", "agree": False, "src": ["T1:p4", "T3:p6", "CF"]},
                 {"claim": "Exports will be 6–8% of revenue", "numbers": "No segment disclosure yet to test it; exports were called soft in Q4 FY26", "agree": False, "src": ["T2:p5"]},
                 {"claim": "Demand from transmission and data centres is strong", "numbers": f"Five straight quarters of 17%+ YoY revenue growth", "agree": True, "src": ["T2:p5", "QR"]}],
             "guidance_now": [{"metric": "Revenue growth", "target": "> 1.5× industry", "horizon": "FY30", "src": ["T4:p7"]},
                              {"metric": "W&C EBITDA margin", "target": "11–13%", "horizon": "sustainable", "src": ["T4:p7"]},
                              {"metric": "Capex", "target": "₹1,600–1,800 cr", "horizon": "FY27", "src": ["T2:p5"]},
                              {"metric": "Working-capital days", "target": "≈ 60", "horizon": "Mar 2027", "src": ["T4:p7"]}],
             "business": {"what": "India's largest wires & cables maker, adding consumer electricals (fans, lights, switchgear) and an EPC arm.",
                          "segments": [{"name": "Wires & cables", "share": "≈ 88%"}, {"name": "FMEG", "share": "≈ 8%"}, {"name": "EPC & others", "share": "≈ 4%"}], "src": ["AR"]},
             "bull": [{"point": f"Revenue compounding {tr['rev_cagr_3y']}% a year (3y) with margins holding — scale, not price, is driving it", "src": ["PL", "QR"]},
                      {"point": "FMEG crossed breakeven on schedule: management delivered the hard promise", "src": ["T3:p6"]},
                      {"point": f"Near debt-free (D/E {ba['de'][-1]:.2f}) while funding ₹1,600 cr+ capex", "src": ["BS", "T2:p5"]}],
             "bear": [{"point": f"Profit isn't turning into cash: CFO/PAT {ca['conversion'][-1]:.2f}× in FY26", "src": ["CF"]},
                      {"point": "Working-capital fix has been 'next quarter' for three calls", "src": ["T1:p4", "T3:p6", "T4:p7"]},
                      {"point": f"Paying {page['ratios']['Stock P/E']}× earnings for a margin running above management's own sustainable band", "src": ["T4:p7", "QR"]}],
             "watch": ["Working-capital days at Q3 FY27 (claimed path back to ≈ 60)", "W&C margin vs the 11–13% band", "Export share once disclosed"]}
    else:
        a = {"verdict": "Management has guided recovery for four calls; volumes are improving but value growth and margins keep landing at the bottom of the band.",
             "ledger": [
                 {"said_in": "Q3 FY26", "promise": "Double-digit volume growth by Q4", "target": "≥ 10% volume", "horizon": "Q4 FY26",
                  "delivered": "Volume grew 1.8% in Q4 FY26", "verdict": "missed", "src": ["T1:p4", "T2:p5"]},
                 {"said_in": "Q3 FY26", "promise": "PBIT margin of 18–20%", "target": "18–20%", "horizon": "FY26",
                  "delivered": f"Operating margin {q[-4]['opm']}%, {q[-3]['opm']}%, {q[-2]['opm']}%, {q[-1]['opm']}% — bottom of the band", "verdict": "partly", "src": ["T1:p4", "QR"]},
                 {"said_in": "Q1 FY27", "promise": "Low to mid single-digit value growth this year", "target": "3–6%", "horizon": "FY27",
                  "delivered": f"Revenue {q[-2]['rev_yoy']:+.1f}% and {q[-1]['rev_yoy']:+.1f}% YoY in H1", "verdict": "delivered", "src": ["T3:p6", "QR"]},
                 {"said_in": "Q2 FY27", "promise": "High single-digit volume growth in H2", "target": "7–9% volume", "horizon": "H2 FY27",
                  "delivered": "Not yet testable", "verdict": "too_early", "src": ["T4:p7"]},
                 {"said_in": "Q4 FY26", "promise": "Backward-integration projects commission in FY27", "target": "on schedule", "horizon": "FY27",
                  "delivered": f"CWIP fell to ₹{ba['cwip'][-1]:,.0f} cr from ₹{ba['cwip'][-2]:,.0f} cr — consistent with assets being capitalised", "verdict": "partly", "src": ["T2:p5", "BS"]}],
             "guidance_drift": "Volume target moved from 'double digit by Q4 FY26' to 'high single digit in H2 FY27'; margin band unchanged but defended with spend.",
             "narrative": [
                 {"claim": "Weakness is cyclical urban demand", "numbers": f"Revenue CAGR {tr['rev_cagr_3y']}% (3y) while volumes stayed positive: the gap is price/mix, not just demand", "agree": False, "src": ["T2:p5", "PL"]},
                 {"claim": "Will protect share even at lower-end margins", "numbers": f"OPM down {abs(tr.get('opm_change_3y_bps', 0))} bps over 3 years", "agree": True, "src": ["T2:p5", "PL"]},
                 {"claim": "Capex intensity will fall after VAM", "numbers": "CWIP already falling; FY28 test pending", "agree": True, "src": ["T4:p7", "BS"]}],
             "guidance_now": [{"metric": "Volume growth", "target": "high single digit", "horizon": "H2 FY27", "src": ["T4:p7"]},
                              {"metric": "PBIT margin", "target": "18–20%", "horizon": "FY27", "src": ["T3:p6"]},
                              {"metric": "Capex", "target": "FY28 ≈ half of FY27", "horizon": "FY28", "src": ["T4:p7"]}],
             "business": {"what": "India's largest decorative paints company, extending into industrial coatings, waterproofing and home decor.",
                          "segments": [{"name": "Decorative India", "share": "≈ 84%"}, {"name": "International", "share": "≈ 10%"}, {"name": "Industrial & home decor", "share": "≈ 6%"}], "src": ["AR"]},
             "bull": [{"point": f"Cash machine intact: 5-year CFO/PAT {ca['conversion_5y']}×", "src": ["CF", "PL"]},
                      {"point": "Volumes have turned up two quarters running; rural leading", "src": ["T3:p6", "T4:p7"]},
                      {"point": "Backward integration should lift gross margin once capitalised", "src": ["T2:p5"]}],
             "bear": [{"point": "Recovery has been guided and pushed out across four calls", "src": ["T1:p4", "T4:p7"]},
                      {"point": "Value lags volume by 4–5 pts: down-trading and price cuts are structural, not one-off", "src": ["T4:p7"]},
                      {"point": f"{page['ratios']['Stock P/E']}× earnings for flat revenue", "src": ["PL"]}],
             "watch": ["Volume vs the H2 'high single digit' promise", "Gap between value and volume growth", "A&P spend as % of sales"]}
    return {**base, "mode": "sample", "analysis": a}


def write_sample():
    pf = settings.load_portfolio()
    rules = settings.load_rules()
    hold = {h["symbol"]: h for h in pf["holdings"]}
    px = make_prices()
    from .sources.announcements import normalize_nse
    anns = [normalize_nse(r) for r in raw_filings()]
    moves = {(s, st["d"]): st["ret"] for s, rows in px.items() for st in al.day_stats(rows) if st["ret"] is not None}
    triage.triage(anns, hold, moves)
    P = pages()
    for a in anns:
        if a["category"] == "results" and a["subtype"] == "results" and a["symbol"] in P:
            a["card"] = {"type": "results", **results.headline(P[a["symbol"]], None)}
            a["line"] = results.summary_line(a["card"])
        if a["category"] == "management_change" and a["symbol"] == "DIXON":
            a["card"] = {"type": "people", "changes": [
                {"person": "Ananya Krishnan", "role": "Chief Financial Officer", "change": "appointed", "effective": "1 Dec 2026",
                 "replaces": "Saurabh Gupta",
                 "profile": "Chartered accountant with 19 years in finance; previously CFO of a listed consumer-durables maker and earlier in corporate finance at a global electronics OEM.",
                 "prior_roles": ["CFO, listed consumer-durables company (2019–2026)", "Head of FP&A, global electronics OEM", "Audit, Big Four firm"],
                 "web": {"bio": "Sample bio: led two acquisitions and a QIP as CFO; known for working-capital discipline.", "confidence": "medium", "sources": []},
                 "linkedin_search": "https://www.linkedin.com/search/results/people/?keywords=Ananya%20Krishnan%20Dixon"},
                {"person": "Saurabh Gupta", "role": "Chief Financial Officer", "change": "resigned", "effective": "30 Nov 2026",
                 "reason": "to pursue opportunities outside the company", "profile": None, "prior_roles": [], "web": None,
                 "linkedin_search": "https://www.linkedin.com/search/results/people/?keywords=Saurabh%20Gupta%20Dixon"}]}
            a["line"] = "CFO Saurabh Gupta exits 30 Nov; Ananya Krishnan, ex-CFO of a listed consumer-durables maker, takes over 1 Dec."
    one = {("LT", "press_release"): "Mega order (>₹7,000 cr) for a 765 kV transmission project; L&T's 'mega' band is its largest order class.",
           ("IEX", "litigation"): "CERC orders phased market coupling in the day-ahead market from Jan 2027 — directly threatens IEX's price-discovery moat. Company weighing legal options.",
           ("KAYNES", "M&A"): "Buying 100% of a Malaysian PCB assembler for ₹640 cr (all-cash, pending approvals): first overseas manufacturing base.",
           ("BAJFINANCE", "credit_rating"): "S&P lifts outlook to Positive (rating affirmed BBB-): a step toward cheaper offshore borrowing.",
           ("DEEPAKNTR", "insider_trading"): "Promoter group bought 4.1 lakh shares on market — insiders adding after the stock's slide.",
           ("SUNPHARMA", "press_release"): "USFDA nod for a specialty dermatology product addressing a ~$450 mn US market."}
    for a in anns:
        k = (a["symbol"], a["category"])
        if k in one and "card" not in a:
            a["line"] = one[k]
    portfolio = []
    for s, hd in hold.items():
        rows = px[s]
        portfolio.append({**hd, "last": rows[-1]["c"], "chg": round((rows[-1]["c"] / rows[-2]["c"] - 1) * 100, 2),
                          "series": [[r["d"], r["c"], r["v"]] for r in rows]})
    snap = {"meta": {"as_of": AS_OF.strftime("%Y-%m-%dT%H:%M:%S+05:30"), "source": "sample", "window_days": 7,
                     "health": {"prices": "sample", "announcements": "sample", "llm": False}, "rules": rules,
                     "models": {"fast": settings.MODEL_FAST, "smart": settings.MODEL_SMART}, "provider": "gemini",
                     "research": ["POLYCAB", "ASIANPAINT", "ETERNAL", "HAL"],
                     "usage": {"calls": {"fast": 0, "smart": 0}, "cache_hits": 0, "tokens_in": 0, "tokens_out": 0}},
            "portfolio": portfolio, "announcements": anns,
            "alerts": al.price_alerts(px, rules) + al.filing_alerts(anns, rules)}
    out = settings.WEB_DATA
    (out / "research").mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, ensure_ascii=False))
    for s in ["POLYCAB", "ASIANPAINT"]:
        (out / "research" / f"{s}.json").write_text(json.dumps(research_sample(s, P[s]), ensure_ascii=False))
    for s in ["ETERNAL", "HAL"]:
        (out / "research" / f"{s}.json").write_text(json.dumps(research_sample(s, P[s], llm_mode=False), ensure_ascii=False))
    tiers = {t: sum(1 for a in anns if a["tier"] == t) for t in ("top", "glance", "routine")}
    print(f"sample written: {len(anns)} filings {tiers}, {len(snap['alerts'])} alerts")
    return snap
