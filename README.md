# Park Pulse 🎢

An end-to-end cloud data pipeline that collects real-time ride wait times and weather data across Disney World and Universal Orlando every 15 minutes, then surfaces the insights in a live Tableau dashboard.

## What it does

- Pulls wait times from **7 theme parks** (4 Disney World, 3 Universal Orlando) on a 15-minute cadence
- Concurrently fetches matching weather data so every wait-time observation has synchronized weather context
- Lands clean, partitioned Parquet files in S3 for cheap, fast analytics
- Exposes the dataset through Athena and visualizes it in Tableau

## Architecture

```
┌──────────────────┐
│  EventBridge     │  triggers every 15 min
│  (cron schedule) │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌─────────────────────┐
│  AWS Lambda      │ ──► │  Theme Park API     │
│  (Python, httpx) │     │  Weather API        │
│  async ingestion │     └─────────────────────┘
└────────┬─────────┘
         │ Parquet
         ▼
┌──────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│  S3              │ ──► │  Athena             │ ──► │  Tableau        │
│  (partitioned)   │     │  (SQL over S3)      │     │  Dashboard      │
└──────────────────┘     └─────────────────────┘     └─────────────────┘
```

## Tech stack

- **Language:** Python 3
- **Compute:** AWS Lambda
- **Storage:** AWS S3 (Parquet)
- **Orchestration:** AWS EventBridge
- **Query:** AWS Athena
- **Viz:** Tableau
- **Libraries:** `httpx`, `boto3`, `pyarrow`

## Why async?

Each run hits multiple park APIs and a weather API. Sequential calls would smear the timestamps across the run window and break tight wait-time/weather correlation. Using `httpx.AsyncClient` keeps every observation in the same ~second-wide window, so analysis is honest.

## Status

🚧 Active development. Pipeline is live and collecting; dashboards and analysis are being expanded.
