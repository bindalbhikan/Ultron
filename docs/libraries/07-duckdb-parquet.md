# 7. DuckDB + Parquet — months and years of data

**Status**: ⏳

**Why**: business reporting and the return analysis read many months of order / return / payment
reports again on every run (from Drive xlsx / csv). For a big seller that is millions of lines. Parquet
(columnar, compressed) read by DuckDB (in-process SQL, multi-core) answers such questions in seconds and reads
straight into Polars.

**Plan**
1. A local / cache Parquet copy of each PORTAL REPORTS month (Drive keeps the xlsx / csv for the owner).
2. Business report and return analysis read the Parquet through DuckDB; parity test against today's output.
