# FINN

A mobile-first filter for a portfolio manager's day. FINN reads every NSE/BSE filing and end-of-day print across a 18-stock book and shows only what moves the needle (**push**). It also researches any NSE company from its own annual report and earnings calls (**pull**), checking what management promised against what was reported.

```
Brief      "Three filings need you."  Results, management changes and anything material
           as bespoke cards. One-liners for what is worth a glance. Routine paperwork
           compressed into a single bar. Swipe right = done, left = mute that kind of
           filing for that stock. Listen = a 40-second spoken brief.
Watch      Set what "unusual" means (price move, volume multiple, filing types) and see
           immediately how often those rules would have fired over the last 60 sessions.
Research   Said vs done: guidance from the last four calls, checked against the numbers.
           Story vs numbers, trajectory, cash conversion, balance sheet, bull and bear,
           and Ask, which answers only from the company's own documents.
```

## Run it

```bash
pip install -r requirements.txt
cd web && python -m http.server 8000      # sample data, no keys, no network: http://localhost:8000
```

Live data (needs internet; NSE works best from an Indian IP):

```bash
cp .env.example .env                       # add a free GEMINI_API_KEY (optional but recommended)
python -m finn doctor                      # checks Yahoo, NSE, BSE, Screener and the model key
python -m finn build                       # nightly snapshot -> web/data/snapshot.json (+ demo research)
python -m finn research TITAN              # research any NSE symbol -> web/data/research/TITAN.json
python -m finn serve                       # live API + app on :8000; research any ticker from the UI
python -m finn notify                      # send today's alerts to Telegram
python -m pytest -q tests                  # 13 tests on real payload shapes
```

Without a model key everything still runs: classification, scoring, results cards and all research numbers are deterministic; summaries fall back to cleaned exchange text and research shows raw guidance sentences instead of the promise ledger.

## How it works

```
                 nightly, after close (GitHub Actions cron 16:45 IST)
 Yahoo EOD ──┐
 NSE / BSE ──┼─> classify (rules, ~90%) ─> score + tier ─> enrich top tier ─> snapshot.json ─> static PWA
 Screener ───┘        └─ fast model for the rest  │        ├─ results: QoQ / YoY table (no model)
                                                   │        └─ people: filing profile + web bio
                                                   └─ alerts (price, volume, filing type) ─> Telegram

                 on demand (python -m finn serve)
 symbol ─> Screener tables ─> numbers (deterministic)
        └> last 4 transcripts + annual report ─> fast model, one call per document (cached forever)
                                               ─> smart model, one call on the compact extracts
                                               ─> promise ledger, story vs numbers, bull / bear
```

| Path | What it does |
|---|---|
| `finn/sources/` | `prices.py` (yfinance, Yahoo chart API fallback, .NS then .BO), `announcements.py` (NSE API with cookie warm-up, BSE API fallback, one normalised shape), `screener.py` (financial tables + transcript/AR links), `docs.py` (PDF text, cached by URL) |
| `finn/engine/taxonomy.py` | Ordered rules over the exchange subject and text into the reference categories. Low-confidence leftovers are batched 20 at a time to the fast model |
| `finn/engine/triage.py` | Materiality score = category base + content modifiers (CEO vs independent director, downgrade vs reaffirm, order size, pledge invoked vs released) + the stock's reaction on the next session. Tiers: top / glance / routine |
| `finn/engine/results.py` | Revenue, EBITDA, PBT, PAT with QoQ and YoY from the reported quarterly table; detects when that table hasn't caught up with the filing and falls back to model extraction from the results PDF, with sanity checks. Lenders get pre-provision profit instead of EBITDA |
| `finn/engine/people.py` | Management changes: the Reg 30 filing's own "brief profile" first, then an optional web search (Tavily or Serper) compressed to a two-line bio with sources, plus a LinkedIn search link |
| `finn/engine/research.py` | Numbers (CAGR, margin change, D/E, working-capital days, CFO/PAT) are computed, not generated. Model output must cite source ids (`T2:p7`, `QR`, `CF`) that resolve to a document and page |
| `finn/llm.py` | Two-tier router (Gemini or any OpenAI-compatible provider), disk cache keyed by prompt hash, free-tier pacing, token ledger reported in every snapshot |
| `web/` | No build step. Vanilla JS PWA, works offline from the snapshot. Alert backtest and Ask (BM25) run client-side |

## Cost

On a normal day the push build makes roughly 5 to 10 fast-model calls (re-classification and one-liners for 40 to 80 filings across the book) and zero smart-model calls. A research build is four fast calls (one per transcript) plus one smart call over a few thousand tokens of extracts. Transcripts and annual reports never change, so their extractions are cached forever and a re-run costs nothing. All of this fits inside the Gemini free tier. Every snapshot records its own model calls, cache hits and tokens in `meta.usage`.

## Deploy

- **App (static):** push to GitHub and enable Pages with "GitHub Actions" as the source. `.github/workflows/eod.yml` runs tests, deploys `web/` on every push, and on weekdays at 16:45 IST rebuilds the snapshot with live data and sends alerts. Add `GEMINI_API_KEY` (and optionally `TAVILY_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`) as repository secrets.
- **Live research API:** `render.yaml` deploys `finn.api` on Render's free plan. Put its URL in `web/config.js` (`window.FINN_API`) so the Research tab can open any ticker.

## Limits

- NSE often refuses data-centre IPs; the BSE fallback covers it, which is why every holding carries its BSE code (CDSL is NSE-only).
- Scanned PDFs have no text layer, so those filings get the exchange's own text, not a summary.
- LinkedIn is not scraped. Web bios come from a search API and are labelled with their sources and a confidence.
- The bundled `web/data` is a **sample** (synthetic filings and financials pushed through the real engine) so the app can be judged anywhere. The UI says so in a banner until `python -m finn build` replaces it.
