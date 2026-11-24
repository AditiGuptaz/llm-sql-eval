"""
Runs each gold query in golden_dataset_generator.py once and saves
the 20 questions + correct answers to golden_hard.csv (read by main.py).

Run:  python make_golden_dataset.py
Output: golden_hard.csv
"""

import csv, json, sqlite3
from golden_dataset_generator import GOLDEN          # <-- reads the HARD generator

DB = "ipl_2021_2024.db"

# Only #12 (top team per season, ordered) is row-order-sensitive in the hard set.
ORDER_SENSITIVE_IDS = {12}

conn = sqlite3.connect(DB); cur = conn.cursor()

rows_out = []
for g in GOLDEN:
    cur.execute(g["sql"])
    cols = [d[0] for d in cur.description]
    data = cur.fetchall()
    rows_out.append({
        "id": g["id"],
        "difficulty": g["diff"],
        "question": g["q"],
        "gold_sql": " ".join(g["sql"].split()),
        "gold_result_json": json.dumps({"columns": cols,
                                        "rows": [list(r) for r in data]},
                                       ensure_ascii=False),
        "n_rows": len(data),
        "order_sensitive": str(g["id"] in ORDER_SENSITIVE_IDS).upper(),
    })
conn.close()

with open("golden_hard.csv", "w", newline="", encoding="utf-8") as f:  
    w = csv.DictWriter(f, fieldnames=["id","difficulty","question","gold_sql",
                                      "gold_result_json","n_rows","order_sensitive"])
    w.writeheader(); w.writerows(rows_out)

print(f"Wrote golden_hard.csv with {len(rows_out)} rows")