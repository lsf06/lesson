with open(r"d:\lesson\xiaolin\lesson-main (1)\lesson-main\esp32_firmware\v6_log.txt","r",encoding="utf-8") as f:
    lines = f.readlines()
print(f"Total lines: {len(lines)}")
for l in lines[-20:]:
    print(l.rstrip())