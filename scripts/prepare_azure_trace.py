#!/usr/bin/env python3
"""Rebuild data/azure2021/azure2021_short.csv.gz from the original trace.

Source  : Azure Functions Invocation Trace 2021 (Microsoft, CC-BY 4.0)
          https://github.com/Azure/AzurePublicDataset
          file data/AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar
          SHA-256 8bb5d1c82e89e467062b6582996232df24edfebadbaf3287a8c985ca178ba92d

Steps
  1. download the .rar  (git clone --depth 1 https://github.com/Azure/AzurePublicDataset)
  2. extract AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt
       unrar x AzureFunctionsInvocationTraceForTwoWeeksJan2021.rar
     or  pip install unrar-cffi  and run this script with --rar
  3. python scripts/prepare_azure_trace.py --txt <path-to-txt>

Transformations (documented in DATASET.md)
  arrival_s  = end_timestamp - duration   (clipped at 0), rounded to 0.1 ms
  keep only invocations with duration <= 1 s (short-task regime, 87.4 %)
  func_key   = CRC32("<app>:<func>") & 0x7fffffff   (hashed identifiers kept hashed)
"""
import argparse
import hashlib
import os
import zlib

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPECTED_RAR_SHA256 = "8bb5d1c82e89e467062b6582996232df24edfebadbaf3287a8c985ca178ba92d"


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--txt", help="extracted AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt")
    g.add_argument("--rar", help="original .rar archive (needs unrar-cffi)")
    ap.add_argument("--max-duration", type=float, default=1.0)
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "azure2021", "azure2021_short.csv.gz"))
    a = ap.parse_args()

    if a.rar:
        h = hashlib.sha256(open(a.rar, "rb").read()).hexdigest()
        print("sha256:", h, "(matches)" if h == EXPECTED_RAR_SHA256 else "(DIFFERENT from paper)")
        from unrar.cffi import rarfile
        rf = rarfile.RarFile(a.rar)
        name = rf.namelist()[0]
        tmp = os.path.join(os.path.dirname(a.out), name)
        with open(tmp, "wb") as f:
            f.write(rf.read(name))
        a.txt = tmp

    df = pd.read_csv(a.txt)
    print("raw invocations:", len(df))
    df["arrival_s"] = (df.end_timestamp - df.duration).clip(lower=0).round(4)
    df = df[df.duration <= a.max_duration].copy()
    df["duration_s"] = df.duration
    df["func_key"] = [zlib.crc32(f"{x}:{y}".encode()) & 0x7FFFFFFF for x, y in zip(df.app, df.func)]
    out = df[["arrival_s", "duration_s", "func_key"]].sort_values("arrival_s", kind="stable")
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    out.to_csv(a.out, index=False, compression="gzip")
    print(f"kept {len(out)} invocations ({len(out)/len(df.index)*100:.1f} % of filtered set) -> {a.out}")


if __name__ == "__main__":
    main()
