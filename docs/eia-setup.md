# EIA API setup

1. Request an EIA API key from the U.S. Energy Information Administration.
2. Copy `.env.example` to `.env` and set `EIA_API_KEY` for Docker Compose, or export `OILSIGNAL_EIA_API_KEY` for direct Python execution.
3. Confirm the current EIA v2 petroleum route, frequency, data columns, and facets you need. `examples/eia-series.example.json` is intentionally a placeholder and does not claim current route IDs.
4. Construct an `EIASeriesRequest` and call `EIAClient.fetch`.
5. Map the response into OilSignal `Observation` records, retaining the request URL/route, series ID, observation date, fetch time, and raw payload hash.

The repository's automated tests do not make network calls and do not require an EIA key.
