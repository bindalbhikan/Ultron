# 7. DuckDB + Parquet — months and years of data

**Status**: ⏳ not started (22 Nov 2026). Before it: every report already reads the saved PORTAL REPORTS (owner,
22 Nov 2026: rebuilds never ask the portals for new files), so a Parquet copy per month is the next speed step.

**Why**: business reporting and the return analysis read many months of order / return / payment
reports again on every run (from Drive xlsx / csv). For a big seller that is millions of lines. Parquet
(columnar, compressed) read by DuckDB (in-process SQL, multi-core) answers such questions in seconds and reads
straight into Polars.

**Plan**
1. A local / cache Parquet copy of each PORTAL REPORTS month (Drive keeps the xlsx / csv for the owner).
2. Business report and return analysis read the Parquet through DuckDB; parity test against today's output.
