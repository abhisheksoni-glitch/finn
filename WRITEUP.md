# FINN: covering note

## What I built

FINN treats the investor's problem as triage, not aggregation. Three surfaces, one idea: the app should earn every second of attention it takes.

**Brief (push).** It opens with a sentence, not a feed: "Three filings need you. 2 worth a glance, 4 routine, folded away." The window defaults to 24 hours and can be set to 3 days, 7 days or "since" a date. Each tier gets a different form, so importance is visible before you read a word:
- *Needs you:* bespoke cards. Results show Revenue, EBITDA, PBT and PAT with QoQ and YoY, the margin change in bps, and an 8-quarter bar. Management changes show who is leaving, who is coming, their profile from the filing itself, prior roles, a web bio with its sources and confidence, and a LinkedIn link. Every card shows how the stock reacted in the first session after the filing.
- *Worth a glance:* one line each.
- *Routine:* compressed into a single bar, grouped by type, tap to unfold.
- *Moved on no news:* holdings that crossed your price or volume rule with no material filing to explain them. That gap is a signal in itself.

Swipe right marks a card done. Swipe left mutes that kind of filing for that stock, so the filter learns what *this* investor ignores. "Listen" reads a 40-second brief aloud for the commute.

**Watch (alerts).** You set the price-move and volume-multiple thresholds, the averaging window and which filing types may interrupt you. As you drag a slider, a 60-session dot matrix (one row per holding) shows how often those rules would have fired: "14 times in 60 sessions, about 1.2 a week." You tune the noise before you commit to it. The nightly build pushes the day's alerts to Telegram.

**Research (pull).** The centrepiece is "Said versus done": headline guidance from the last four earnings calls, each with the number that was actually reported, a verdict (delivered, partly, missed, walked back, too early) and a note on how the guidance drifted from call to call. Then story versus numbers, guidance on the table now, trajectory, cash conversion, balance sheet, bull and bear, and an Ask box that answers only from the company's own transcripts and annual report. Every claim carries a source chip that opens the passage it came from.

## Key decisions and trade-offs

- **Rules first, models second.** Exchange subjects are semi-structured, so ordered rules classify about 90% of filings at no cost. The model only sees the ambiguous rest, batched 20 at a time. One-liners start as the exchange's own text with boilerplate stripped; the model rewrites only the items that will actually be shown.
- **Numbers are computed, never generated.** QoQ/YoY, CAGRs, margins, D/E, working-capital days and cash conversion come straight from the reported tables. Results cards cost zero model calls; the PDF extraction path only runs when the table hasn't caught up with the filing, and its output is sanity-checked.
- **Two-tier model routing.** A cheap model maps each transcript to structured guidance with page numbers (one call per document, cached forever, since documents never change). One stronger call reasons over those compact extracts plus the numbers. Research for a company runs on a few thousand tokens of reasoning context instead of a few hundred pages, and every snapshot reports its own calls, cache hits and tokens.
- **Primary sources only, with citations.** The reasoning prompt gets only the extracts and reported numbers, and every output item must cite a source id that resolves to a document and page.
- **Management bios start from the filing.** SEBI's Reg 30 disclosure for an appointment already includes a brief profile, so that comes first. Web enrichment through a search API comes second, labelled with sources and confidence. LinkedIn is linked, not scraped.
- **The push side is a static snapshot.** EOD data changes once a day, so a cron job after the close plus a static PWA is the right architecture: free to host, instant to open, works offline. Only the pull side needs a server, and only for tickers that haven't been prebuilt.
- **Price reaction is part of materiality.** A filing that moved its stock 6% on the next session ranks above one that didn't. A filing made after the 15:30 close is matched to the next session.
- **It degrades instead of breaking.** NSE falls back to BSE; yfinance falls back to the Yahoo chart API; with no model key, research still shows every number plus raw guidance sentences, and the brief still ranks and summarises.

## What I left out, on purpose

- Intraday data and real-time alerts. The brief is about EOD, and a lean team doesn't need a ticker.
- Sentiment scores and price targets. They would be the model's opinion dressed up as signal.
- News and broker notes on the pull side, per the brief.
- Login, multi-portfolio and server-side preferences. Mutes and rules live on the device for now.
- A chat-first interface. Chat is there (Ask), but scoped to one company's documents; the default interaction is a ranked brief you can finish.

## Where I'd take it next

1. Learn the scoring weights from swipes (done vs mute, per category and per stock) instead of hand-set modifiers.
2. Order wins sized against trailing revenue, and pledges against promoter holding, so "material" is relative to the company.
3. A results-day mode: the moment a holding files, compare the numbers with what management guided on the previous call and push that single line.
4. Peer context in research: the same promise ledger across a sector, to see whose management is consistently credible.
5. Real web push and a WhatsApp channel alongside Telegram.

## A note on the demo

The bundled snapshot is sample data: synthetic filings, prices and financials pushed through the real engine, so the app can be judged on any phone with no setup. A banner says so. `python -m finn build` replaces it with the live feed, and `python -m finn serve` opens research for any NSE ticker.
