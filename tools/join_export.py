#!/usr/bin/env python3
"""Reassemble chunked Studio exports saved by the MCP as tool-result files.

Each chunk was returned as "@@<TAG><n>@@" + data + "@@END@@" + padding, which forces the MCP
to save it to a file instead of the conversation. This finds the newest file for each tag
and writes the joined data.

usage: join_export.py <results_dir> <TAG> <count> <out_file>
"""
import os, sys, glob

results, tag, count, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4]
files = sorted(glob.glob(os.path.join(results, "*.txt")), key=os.path.getmtime)
parts = {}
for f in files:
    with open(f, encoding="utf-8", errors="replace") as fh:
        head = fh.read(16)
    for n in range(1, count + 1):
        marker = f"@@{tag}{n}@@"
        if head.startswith(marker):
            data = open(f, encoding="utf-8").read()
            assert "@@END@@" in data, f"{f}: chunk truncated"
            parts[n] = data[len(marker):data.index("@@END@@")]
missing = [n for n in range(1, count + 1) if n not in parts]
assert not missing, f"missing chunks {missing}"
with open(out, "w", encoding="utf-8") as fh:
    fh.write("".join(parts[n] for n in range(1, count + 1)))
print(out, sum(len(p) for p in parts.values()), "bytes")
