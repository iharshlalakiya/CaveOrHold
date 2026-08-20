# CaveOrHold

Testing LLM resistance to adversarial persuasion. Two agents debate a question with one
objectively correct answer: Agent A starts correct, Agent B is deliberately wrong but argues
using manipulation tactics (repetition, false authority, fake social proof, gaslighting,
emotional pressure, false dilemma). We measure whether Agent A holds its answer or caves,
and at which round.

## Setup

```
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
cp .env.example .env         # then fill in HF_TOKEN if using gated models or RUN_MODE=api
```

Edit `.env` to choose models, run mode (`local` or `api`), and number of debate rounds.

## Run a debate batch

```
python -m caveorhold.orchestrator
```

Logs are written as JSON to `caveorhold/logs/`.

## Analyze results

```
python -m caveorhold.analysis.report
```

Produces `caveorhold/analysis/results_summary.csv` and `flip_rate_by_tactic.png`.

## Live demo viewer

```
uvicorn caveorhold.server:app --reload
```

Then open http://127.0.0.1:8000 to browse transcripts and verdicts.

## Project layout

- `caveorhold/agents/` — Agent A (correct), Agent B (manipulative), and the model backend
  (local transformers or HF Inference API)
- `caveorhold/verifier.py` — sentence-transformers based answer scoring
- `caveorhold/orchestrator.py` — runs debates across questions x tactics, logs transcripts
- `caveorhold/analysis/` — pandas/matplotlib flip-rate reporting
- `caveorhold/server.py` — FastAPI live transcript viewer
- `caveorhold/data/questions.json` — question set with correct/plausible-wrong answers
- `caveorhold/data/tactics.json` — manipulation tactic descriptions
