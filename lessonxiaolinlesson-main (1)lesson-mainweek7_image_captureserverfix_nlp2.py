#!/usr/bin/env python3
"""Replace all garbled text (PUA chars U+E000-U+F8FF) in app.py with clean English."""
import re, sys

FILE = 'app.py'
with open(FILE, encoding='utf-8') as f:
    data = f.read()

# Magnifier: find every line with PUA garbage and show surrounding safe chars
PUA = re.compile(r'[\ue000-\uf8ff]')
pua_lines = [(i+1, l) for i, l in enumerate(data.split('\n')) if PUA.search(l)]
print(f"Found {len(pua_lines)} lines with PUA characters")
for num, line in pua_lines:
    # Extract a safe prefix (first 10 chars before a PUA char)
    m = PUA.search(line)
    ctx_before = line[max(0, m.start()-15):m.start()]
    print(f"  L{num}: ...{repr(ctx_before)}... [PUA] ...")

sys.exit(0)  # Just scan first