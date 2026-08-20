import json
from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

LOG_DIR = Path(__file__).parent.parent / "logs"
OUT_DIR = Path(__file__).parent


def load_results() -> pd.DataFrame:
    rows = []
    for path in LOG_DIR.glob("*.json"):
        with open(path) as f:
            data = json.load(f)
        rows.append({
            "question_id": data["question_id"],
            "tactic": data["tactic"],
            "caved": data["caved"],
            "flip_round": data["flip_round"],
            "similarity_to_correct": data["similarity_to_correct"],
            "similarity_to_wrong": data["similarity_to_wrong"],
        })
    return pd.DataFrame(rows)


def flip_rate_by_tactic(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby("tactic")["caved"].mean().sort_values(ascending=False).reset_index(
        name="flip_rate"
    )


def plot_flip_rate(df: pd.DataFrame, out_path: Path) -> None:
    summary = flip_rate_by_tactic(df)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(summary["tactic"], summary["flip_rate"] * 100)
    ax.set_ylabel("Cave rate (%)")
    ax.set_xlabel("Manipulation tactic")
    ax.set_title("Agent A cave rate by manipulation tactic")
    ax.set_ylim(0, 100)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    fig.savefig(out_path)
    print(f"Saved chart to {out_path}")


def main():
    df = load_results()
    if df.empty:
        print("No debate logs found in caveorhold/logs. Run the orchestrator first.")
        return
    summary = flip_rate_by_tactic(df)
    print(summary.to_string(index=False))
    df.to_csv(OUT_DIR / "results_summary.csv", index=False)
    plot_flip_rate(df, OUT_DIR / "flip_rate_by_tactic.png")


if __name__ == "__main__":
    main()
