from caveorhold.orchestrator import load_questions, load_tactics, run_debate, save_result

questions = load_questions()
tactics = load_tactics()

q = questions[0]
tactic_name = "repetition"
tactic_desc = tactics[tactic_name]

print(f"Running single test debate: {q['id']} / {tactic_name}")
result = run_debate(q, tactic_name, tactic_desc)
path = save_result(result)
print(f"Saved to {path}")
print(f"Caved: {result['caved']}, flip_round: {result['flip_round']}")
print(f"Final: {result['final_extracted_answer']}")
