# Kerala Vegetable Price Shocks: design

Status: approved direction (Joe delegated the problem choice on 2026-11-01). Author: Claude, for Joe Kanjirathingal.

## Why

Kerala grows a small share of the vegetables it eats and buys most of its tomato, onion and potato through
wholesale markets supplied from Tamil Nadu, Karnataka and Maharashtra. When a price shock hits a producing
region (rain damage, heat, a glut), it reaches Kerala markets later, and households, hotels and cooperatives
pay for it. The questions a real buyer, farmer or planner asks:

1. **Will prices spike in the next two weeks?** (an early warning someone can act on: stock up, contract early)
2. **How fast and how fully does a shock in a producing state reach Kerala**, and do prices fall as fast as
   they rise? (asymmetric price transmission, "rockets and feathers")
3. **Where is the money lost?** How far apart are prices in markets close to each other on the same day?

## Goals

- A reproducible pipeline from raw public data to every number on the site, with reconciliation tests.
- Real scraping: news coverage of price shocks (to date and label causes) and historical weather for the
  producing districts.
- One ML model that earns its place: a 14-day spike classifier, compared honestly with simple rules.
- A literature section that places the methods and results against published work.
- A new case-study site with interactive Flourish charts, built with the design skills Joe named.

## Non-goals

- Retail (shop) prices: the open data is wholesale. Say so; do not imply retail numbers.
- Real-time production service or alerts.
- Claiming causality from observational data.

## Anti-goals (failure even if it "works")

- Bypassing CAPTCHAs or scraping against robots.txt or terms. Agmarknet and the Consumer Affairs price
  portal are CAPTCHA-gated, so they are not scraped; the same Agmarknet data comes from India Data Portal.
- A model that only looks good because of leakage or a random split.
- Invented numbers, synthetic data presented as real, or a generic "AI-looking" site.

## Data

| Source | What | Access |
|---|---|---|
| India Data Portal (ISB), "Agriculture Marketing", ODC-By | Agmarknet daily mandi records: date, market, lat/long, commodity, variety, arrivals, min/max/modal price. 22.6M rows (2021 onward) + 3.9M rows (new source, to Oct 2025) | Open CSV download |
| Open-Meteo historical archive | Daily rainfall and max temperature at producing-district coordinates | Free API, no key |
| News (Google News RSS search, then article pages) | Dated coverage of TOP price shocks and stated causes | Scrapling, robots.txt respected, rate-limited |

Scope: tomato, onion, potato (the TOP crops of national price policy, best covered in the literature), with
Kerala markets as destination and the main producing hubs as origin (e.g. Kolar, Lasalgaon/Nashik, Agra,
plus Tamil Nadu and Karnataka markets that supply Kerala). Final hub list is chosen from the data
(arrival volumes), not assumed.

## Method

1. **Ingest and clean** (DuckDB/Parquet): unify the two source schemas, normalise units (Rs/quintal,
   tonnes), drop impossible prices, deduplicate, flag stale or repeated reports. Data tests reconcile row
   counts and check ranges, as in Retail Analytics Lab.
2. **Series**: daily arrival-weighted modal price per commodity for Kerala and for each origin hub; gaps
   handled explicitly (no silent interpolation in evaluation).
3. **Transmission**: lead-lag by cross-correlation and Granger tests; asymmetric error-correction or
   threshold model for rises vs falls; report lag in days and pass-through share with uncertainty.
4. **Dispersion**: same-day price spread among markets within a radius, over time and by commodity.
5. **Spike early warning**: label = Kerala (or national) price 14 days ahead is at least 30% above today.
   Features known at prediction time only: price momentum and volatility, origin-hub arrivals and their
   trend, origin-hub prices, seasonality, rainfall and heat anomalies at origin, news intensity. Models:
   rule baselines (momentum threshold, seasonal rule), logistic regression, gradient boosting. Rolling-origin
   chronological evaluation; precision, recall, PR-AUC, warning lead time; calibration. Threshold chosen on
   validation, reported once on a held-out final period.
6. **News scraping**: monthly RSS queries per crop; parse titles, dates, sources; classify stated cause with a
   transparent keyword lexicon (rain/flood, heat/drought, pest/disease, glut, export/policy, transport/strike),
   checked on a hand-labelled sample. Used for event dating, a feature, and the site's timeline.
7. **Literature**: 8–12 papers on Indian TOP price volatility, transmission and ML forecasting, with what each
   found and how this project compares.

## Website

- New design, not the previous purple Three.js page. Use the requested skills: Anthropic frontend-design,
  Impeccable (anti-slop rules and critique), Taste Skill, Hallmark (theme, sloplint at eight widths) and
  Interface Design ("Data & Analysis" direction). Follow their shared bans: no purple gradients, no
  Inter-only type, no eyebrow labels on every heading, no coloured word in headlines, no nested cards.
- Charts made in Flourish (Joe's account, public on the free plan) and embedded; each chart also has a
  static fallback image and a data table link for accessibility and if Flourish is down.
- Deployed on Vercel, linked from the portfolio; resume and portfolio updated once results exist.

## Left to the builder

Exact hub list, thresholds after looking at the data (documented), model family details, chart types,
theme choice within the skills' rules.
