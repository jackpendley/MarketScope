"""Research data lake (MS-052, ADR-061): every book's full spread, total and moneyline ladders as
Parquet, rebuilt on demand from OddsPapi's free history and queried with DuckDB.

The lake is a reproducible cache, not a source of truth: `python -m marketscope_research.lake build`
recreates it from the provider. It lives under fixtures/oddspapi/local/lake (gitignored: provider data
never enters the public repo).
"""
