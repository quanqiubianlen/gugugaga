"""Temporary: repair truncated conversation JSON."""
import json

path = r"C:\coding\agent\conversations\65b67f509200.json"

with open(path, "r", encoding="utf-8") as f:
    lines = f.readlines()

# The last complete message ends at line 612 (0-indexed: 611)
# Lines 613-622 are the incomplete message
fixed = lines[:612]  # keep lines 0-611

# Fix the last line: change '    },' to '    }'
last_line = fixed[-1]
fixed[-1] = last_line.replace("    },\n", "    }\n")

# Close the messages array and JSON object
fixed.append("  ]\n")
fixed.append("}\n")

with open(path, "w", encoding="utf-8") as f:
    f.writelines(fixed)

# Verify
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

print(f"OK - {len(data['messages'])} messages preserved, file is valid JSON.")

