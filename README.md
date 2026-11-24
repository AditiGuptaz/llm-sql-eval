# LLM-SQL-EVAL

How well can LLMs turn plain-English questions into correct SQL?

This project tests 5 models on 20 hard questions about IPL cricket data (2021–2024). Each model gets the database schema and a question, writes a SQL query, and I run that query against the real database. If its answer matches the answer from my hand-written query, it scores a point.

This method is called **execution accuracy**, the same metric used by text-to-SQL benchmarks like Spider and BIRD. I compare the results, not the SQL text, because two very different queries can both be correct.

## Results

Latest run (temperature 0, one attempt per question):

| Model | Score |
|---|---|
| Grok 4.5 | 17/20 (85%) |
| GPT-5.6 Terra | 16/20 (80%) |
| Claude Sonnet 5 | 16/20 (80%) |
| MiniMax M3 | 15/20 (75%) |
| Kimi K3 | 12/20 (60%) |

In an earlier run with the same setup, the scores were 18, 14, 14, 16 and 8 (full results in `eval_results_run1.csv`). Kimi moved by 4 questions between runs. With 20 questions, one question is worth 5 points, so gaps of 1–2 questions between models are within run-to-run noise. Grok came first in both runs.

## What I learned

I re-ran every failed query from the latest run against the database and sorted the 24 failures by cause:

| Cause | Count | What happened |
|---|---|---|
| My answer key vs cricket rules | 8 | Questions 10 and 11 (economy, bowling average). My gold query counts byes and leg-byes against the bowler. Real cricket doesn't. The 4 models that answered used the real rule and named the right player (SP Narine, AD Russell), just with a different number |
| Rounding | 6 | Models used `ROUND(x, 2)` and returned 64.71 when the gold answer was 64.7059. Right answer, marked wrong by my evaluator |
| Empty response | 5 | Kimi and MiniMax returned nothing at all |
| SQL cut off mid-query | 3 | e.g. a query ending in `ORDER BY win_percentage DESC,` |
| Defensible alternative | 1 | One model excluded wides from "balls faced", which is arguably more correct |
| **Actually wrong** | **1** | MiniMax wrote `extras_type != 'wides'` with no NULL check. In SQL, a comparison with NULL is never true, so every normal delivery was dropped and the strike rate came out as 34,700. That's exactly the trap the question was designed to catch |

So only **1 of 24 failures** was a real SQL mistake. Most of the rest came from my grader, my answer key, or the response budget.

The empty and cut-off responses (8 in total, all from Kimi and MiniMax) look like the `max_tokens=800` limit running out. Models that "think" before answering use up the budget before they finish writing the SQL. A query cut off mid-line is what hitting the limit looks like. I haven't confirmed this with a higher limit yet.

The main lesson: building a fair grader is as hard as the task being graded. When every model fails the same question, check the answer key first.

## The questions

20 questions, split into two difficulty levels:

- **Hard (1–8):** 1–2 traps each
- **Brutal (9–20):** 3 or more traps stacked together

The traps are things that commonly trip up text-to-SQL models:

- NULL handling (`extras_type IS NULL OR ...`)
- cricket rules: wides and no-balls aren't legal balls, and run outs aren't credited to the bowler
- ratios: strike rate, economy, average, percentages
- minimum thresholds with `HAVING`
- subqueries, window functions and team logic (team1 / team2 / winner)
- phases of play: powerplay (overs 0–5) and death overs (15–19)

Example: *"Which bowler bowled the most legal deliveries (exclude wides and no-balls)?"* Gold answer: YS Chahal, 1391.

## How it works

```
Kaggle CSVs ─► db.py ─► SQLite DB ─► schema.sql + golden_hard.csv
                                              │
           for each model, for each question  ▼
   prompt (schema + question) ─► LLM ─► SQL ─► run on DB ─► compare to gold ─► score
```

| File | What it does |
|---|---|
| `db.py` | Builds `ipl_2021_2024.db` from the Kaggle CSVs, keeping only 2021–2024 (279 matches, 67,303 deliveries) |
| `schema_extractor.py` | Saves the `CREATE TABLE` statements to `schema.sql`, which is all the model is told about the database. It has an optional rename mode to test whether models read the schema or rely on memorized Kaggle column names |
| `golden_dataset_generator.py` | The 20 questions and their hand-written gold SQL. Run it directly to check that all 20 queries work |
| `make_golden_dataset.py` | Runs each gold query once and saves the answers as JSON in `golden_hard.csv`, so the answer key is fixed |
| `first_test.py` | Smoke test: one question, one model, prints the raw output |
| `main.py` | The eval loop: calls each model through OpenRouter, cleans the reply, runs the SQL, scores it, and writes `eval_results.csv` |
| `evaluator.py` | Decides whether two results match |
| `model_openrouter_slug.py` | The list of models under test |

### How the evaluator decides "correct"

- column names are ignored, only values matter
- numbers are compared as numbers (`24395` = `24395.0`), rounded to 4 decimals
- row order is ignored, except for the one question that asks for a specific order
- one extra or missing column is allowed. For "who scored the most?", returning just the name or the name plus the count are both accepted

I used plain Python and pandas rather than an eval framework, so I could control exactly what counts as correct. LangChain (`ChatOpenRouter`) is only used to call the models.

## Run it yourself

**Requires Python 3.11+.** The macOS system Python (3.9) won't work, because `langchain-openrouter` needs a newer version.

```bash
conda create -n llm-sql-eval python=3.12 -y
conda activate llm-sql-eval
pip install -r requirements.txt
```

Create a `.env` file with your OpenRouter key:
```
OPENROUTER_API_KEY=sk-or-...
```

Download the [IPL complete dataset](https://www.kaggle.com/datasets/patrickb1912/ipl-complete-dataset-20082020) from Kaggle and put `matches.csv` and `deliveries.csv` in a `data/` folder.

Then run these in order. Use `python`, not `python3`, so you stay inside the conda environment:

```bash
python db.py                          # build the database
python schema_extractor.py            # save schema.sql
python golden_dataset_generator.py    # check the 20 gold queries (should say 20/20 passed)
python make_golden_dataset.py         # save gold answers to golden_hard.csv
python first_test.py                  # optional: one cheap API call
python main.py                        # full eval: 100 API calls, uses OpenRouter credits
```

## Known limitations and next steps

- Only 20 questions and one run per model. I plan to run several times and report the average and spread.
- Numeric comparison is stricter than intended. Next step: compare within a tolerance so rounded answers aren't marked wrong.
- Questions 10 and 11 are ambiguous about byes and leg-byes. I'll either reword them or update the gold queries to match real cricket rules.
- Try a higher `max_tokens` to check whether the empty responses are caused by the token limit.
- The "one extra column" leniency could in rare cases let a row with an extra wrong value pass.
- Run with the renamed schema to measure how much models rely on memorized Kaggle column names.

## Tech

Python · SQLite · pandas · LangChain (`ChatOpenRouter`) · OpenRouter
