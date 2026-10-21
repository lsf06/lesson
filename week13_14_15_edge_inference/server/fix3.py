import re, sys
FILE = "app.py"
with open(FILE, encoding="utf-8") as f:
    data = f.read()
lines = data.split("\n")
fix = {}
fix[55] = "    SIMULATE_SLOW_RESPONSE = False  # Set True for 10s delay test"
fix[58] = "# ===== Active Task State (Cancellation / Isolation) ====="
fix[549] = '    """Cancel current NLP task. Called when user clicks stop or says "cancel".'
fix[571] = '    """Natural language query entry point (supports cancellation and result isolation).'
fix[582] = "    # ---- Generate unique request_id ----"
fix[590] = '        """Build response with task_state, implementing result isolation.'
fix[680] = "            # ---- Check cancellation before each poll ----"
for no, new in fix.items():
    if no >= 0 and no < len(lines):
        lines[no] = new
        print(f"Fixed line {no+1}")
    else:
        print(f"Line {no+1} out of range")
with open(FILE, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
import ast
ast.parse(open(FILE, encoding="utf-8").read())
print("Syntax OK!")