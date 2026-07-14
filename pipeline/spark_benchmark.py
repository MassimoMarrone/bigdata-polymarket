"""Is Spark the right tool for this dataset? Measure it instead of assuming.

The brief lists Spark among the suggested tools ("for scalable preprocessing and
analysis of LARGE-SCALE longitudinal datasets"). Our dataset is not large-scale:
~59k post-contract pairs and ~95k price snapshots, tens of megabytes. The claim we
want to test is that Spark's distributed machinery costs more than it saves at this
size — and, more usefully, to find the size at which that flips.

Both engines run the SAME workload: the daily aggregation the project actually
performs (posts per contract-day + mean sentiment, joined to the daily price), which
is the input to the lead/lag analysis. Data is replicated by a scale factor to
simulate larger inputs, keeping the shape of the computation identical.

Run: python3 pipeline/spark_benchmark.py
"""
from __future__ import annotations

import os
import time
from pathlib import Path

os.environ.setdefault("JAVA_HOME", str(Path.home() / "jdk"))

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
BENCH = PROC / "_bench"

SCALES = (1, 10, 50, 200)  # x59k pairs -> up to ~11.7M rows


def materialise(scale: int) -> tuple[Path, Path]:
    """Replicate the real data `scale` times, on disk, so both engines read the same files."""
    import duckdb

    BENCH.mkdir(parents=True, exist_ok=True)
    posts_out = BENCH / f"posts_x{scale}.parquet"
    prices_out = BENCH / f"prices_x{scale}.parquet"
    if posts_out.exists() and prices_out.exists():
        return posts_out, prices_out

    con = duckdb.connect()
    for src, dst in ((PROC / "posts.parquet", posts_out),
                     (PROC / "prices.parquet", prices_out)):
        con.execute(f"""
            COPY (
                SELECT * FROM read_parquet('{src}'), range({scale})
            ) TO '{dst}' (FORMAT PARQUET)
        """)
    return posts_out, prices_out


def duckdb_run(posts: Path, prices: Path) -> tuple[float, int]:
    import duckdb

    con = duckdb.connect()
    t = time.perf_counter()
    n = con.execute(f"""
        WITH social AS (
            SELECT market_id, date_trunc('day', published_at) AS day,
                   count(*) AS volume
            FROM read_parquet('{posts}')
            GROUP BY 1, 2
        ), price AS (
            SELECT market_id, date_trunc('day', timestamp) AS day,
                   avg(price) AS price
            FROM read_parquet('{prices}')
            WHERE outcome IN ('Yes', 'Over')
            GROUP BY 1, 2
        )
        SELECT count(*) FROM price LEFT JOIN social USING (market_id, day)
    """).fetchone()[0]
    return time.perf_counter() - t, n


def spark_run(posts: Path, prices: Path) -> tuple[float, int]:
    from pyspark.sql import SparkSession, functions as F

    spark = (SparkSession.builder
             .appName("bench").master("local[*]")
             .config("spark.driver.memory", "4g")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")

    t = time.perf_counter()
    social = (spark.read.parquet(str(posts))
              .withColumn("day", F.to_date("published_at"))
              .groupBy("market_id", "day").agg(F.count("*").alias("volume")))
    price = (spark.read.parquet(str(prices))
             .filter(F.col("outcome").isin("Yes", "Over"))
             .withColumn("day", F.to_date("timestamp"))
             .groupBy("market_id", "day").agg(F.avg("price").alias("price")))
    n = price.join(social, ["market_id", "day"], "left").count()
    elapsed = time.perf_counter() - t
    spark.stop()
    return elapsed, n


def main() -> None:
    print(f"{'scala':>6s} {'righe post':>12s} {'DuckDB':>10s} {'Spark':>10s} {'rapporto':>10s}")
    for scale in SCALES:
        posts, prices = materialise(scale)
        import duckdb
        n_rows = duckdb.connect().execute(
            f"SELECT count(*) FROM read_parquet('{posts}')").fetchone()[0]

        d_t, d_n = duckdb_run(posts, prices)
        s_t, s_n = spark_run(posts, prices)
        assert d_n == s_n, f"risultati diversi! duckdb={d_n} spark={s_n}"

        ratio = s_t / d_t
        print(f"{scale:5d}x {n_rows:12,d} {d_t:9.2f}s {s_t:9.2f}s {ratio:9.1f}x")


if __name__ == "__main__":
    main()
