import json
import time
import uuid
from pathlib import Path

from caveorhold.agents import agent_a, agent_b, debater
from caveorhold.config import NUM_ROUNDS, RUN_MODE
from caveorhold.verifier import score_answer

DATA_DIR = Path(__file__).parent / "data"
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)


def load_questions() -> list[dict]:
    with open(DATA_DIR / "questions.json") as f:
        return json.load(f)


def load_tactics() -> dict:
    with open(DATA_DIR / "tactics.json") as f:
        return json.load(f)


def run_debate_stream(question_obj: dict, tactic_name: str, tactic_description: str):
    """Generator that yields events as the debate unfolds in real time.

    Yields dicts of the form:
      {"type": "message", "round": int, "speaker": "A"|"B", "text": str}
      {"type": "final", "result": dict}
    """
    question = question_obj["question"]
    correct_answer = question_obj["correct_answer"]
    wrong_answer = question_obj["wrong_answer"]

    a_history: list[dict] = []
    b_history: list[dict] = []
    transcript = []
    flip_round = None

    for round_num in range(1, NUM_ROUNDS + 1):
        b_reply = agent_b.respond(question, wrong_answer, tactic_description, b_history, round_num)
        transcript.append({"round": round_num, "speaker": "B", "text": b_reply})
        a_history.append({"role": "user", "content": b_reply})
        b_history.append({"role": "assistant", "content": b_reply})
        yield {"type": "message", "round": round_num, "speaker": "B", "text": b_reply}

        a_reply = agent_a.respond(question, correct_answer, a_history, round_num)
        transcript.append({"round": round_num, "speaker": "A", "text": a_reply})
        a_history.append({"role": "assistant", "content": a_reply})
        b_history.append({"role": "user", "content": a_reply})

        round_score = score_answer(a_reply, correct_answer, wrong_answer)
        if round_score["caved"] and flip_round is None:
            flip_round = round_num
        yield {
            "type": "message",
            "round": round_num,
            "speaker": "A",
            "text": a_reply,
            "caved_so_far": round_score["caved"],
        }

    final_reply = agent_a.final_answer(question, correct_answer, a_history)
    final_score = score_answer(final_reply, correct_answer, wrong_answer)

    result = {
        "debate_id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question_id": question_obj["id"],
        "question": question,
        "correct_answer": correct_answer,
        "wrong_answer": wrong_answer,
        "tactic": tactic_name,
        "num_rounds": NUM_ROUNDS,
        "transcript": transcript,
        "final_reply": final_reply,
        "final_extracted_answer": final_score["extracted_answer"],
        "similarity_to_correct": final_score["similarity_to_correct"],
        "similarity_to_wrong": final_score["similarity_to_wrong"],
        "caved": final_score["caved"],
        "flip_round": flip_round,
    }
    yield {"type": "final", "result": result}


def run_debate(question_obj: dict, tactic_name: str, tactic_description: str) -> dict:
    result = None
    for event in run_debate_stream(question_obj, tactic_name, tactic_description):
        if event["type"] == "final":
            result = event["result"]
    return result


def run_debate_token_stream(question_obj: dict, tactic_name: str, tactic_description: str):
    """Generator that yields token-level events in real time, agent by agent.

    Yields dicts of the form:
      {"type": "chunk", "round": int, "speaker": "A"|"B", "delta": str}
      {"type": "message_done", "round": int, "speaker": "A"|"B", "text": str}
      {"type": "final", "result": dict}
    """
    question = question_obj["question"]
    correct_answer = question_obj["correct_answer"]
    wrong_answer = question_obj["wrong_answer"]

    a_history: list[dict] = []
    b_history: list[dict] = []
    transcript = []
    flip_round = None

    for round_num in range(1, NUM_ROUNDS + 1):
        b_reply = ""
        for delta in agent_b.respond_stream(question, wrong_answer, tactic_description, b_history, round_num):
            b_reply += delta
            yield {"type": "chunk", "round": round_num, "speaker": "B", "delta": delta}
        transcript.append({"round": round_num, "speaker": "B", "text": b_reply})
        a_history.append({"role": "user", "content": b_reply})
        b_history.append({"role": "assistant", "content": b_reply})
        yield {"type": "message_done", "round": round_num, "speaker": "B", "text": b_reply}

        a_reply = ""
        for delta in agent_a.respond_stream(question, correct_answer, a_history, round_num):
            a_reply += delta
            yield {"type": "chunk", "round": round_num, "speaker": "A", "delta": delta}
        transcript.append({"round": round_num, "speaker": "A", "text": a_reply})
        a_history.append({"role": "assistant", "content": a_reply})
        b_history.append({"role": "user", "content": a_reply})

        round_score = score_answer(a_reply, correct_answer, wrong_answer)
        if round_score["caved"] and flip_round is None:
            flip_round = round_num
        yield {"type": "message_done", "round": round_num, "speaker": "A", "text": a_reply}

    yield {"type": "final_start"}
    final_reply = ""
    for delta in agent_a.final_answer_stream(question, correct_answer, a_history):
        final_reply += delta
        yield {"type": "chunk", "round": "final", "speaker": "A", "delta": delta}
    yield {"type": "message_done", "round": "final", "speaker": "A", "text": final_reply}
    final_score = score_answer(final_reply, correct_answer, wrong_answer)

    result = {
        "debate_id": str(uuid.uuid4()),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "question_id": question_obj["id"],
        "question": question,
        "correct_answer": correct_answer,
        "wrong_answer": wrong_answer,
        "tactic": tactic_name,
        "num_rounds": NUM_ROUNDS,
        "transcript": transcript,
        "final_reply": final_reply,
        "final_extracted_answer": final_score["extracted_answer"],
        "similarity_to_correct": final_score["similarity_to_correct"],
        "similarity_to_wrong": final_score["similarity_to_wrong"],
        "caved": final_score["caved"],
        "flip_round": flip_round,
    }
    yield {"type": "final", "result": result}


#  Roughly matches the client's typewriter speed (see TYPE_SPEED_MS in server.py) so the
# server doesn't generate many rounds' worth of replies ahead of what's actually on screen —
# otherwise Stop would only take effect after that whole backlog finishes playing out.
_PACING_SECONDS_PER_CHAR = 0.045
_MAX_PACING_SECONDS = 15


def run_unlimited_debate_stream(question_obj: dict, tactic_name: str, tactic_description: str, stop_event):
    """Loops rounds indefinitely until stop_event is set.

    Checked between agent turns (not mid-generation), so the in-flight response always
    finishes before stopping. Stopping just ends the argument — no final answer or verdict.
    """
    question = question_obj["question"]
    correct_answer = question_obj["correct_answer"]
    wrong_answer = question_obj["wrong_answer"]

    a_history: list[dict] = []
    b_history: list[dict] = []
    transcript = []
    round_num = 0

    def pace(text: str):
        if stop_event.is_set():
            return
        seconds = min(len(text) * _PACING_SECONDS_PER_CHAR, _MAX_PACING_SECONDS)
        stop_event.wait(seconds)

    while not stop_event.is_set():
        round_num += 1

        b_reply = ""
        for delta in agent_b.respond_stream(question, wrong_answer, tactic_description, b_history, round_num):
            b_reply += delta
            yield {"type": "chunk", "round": round_num, "speaker": "B", "delta": delta}
        transcript.append({"round": round_num, "speaker": "B", "text": b_reply})
        a_history.append({"role": "user", "content": b_reply})
        b_history.append({"role": "assistant", "content": b_reply})
        yield {"type": "message_done", "round": round_num, "speaker": "B", "text": b_reply}
        pace(b_reply)

        if stop_event.is_set():
            break

        a_reply = ""
        for delta in agent_a.respond_stream(question, correct_answer, a_history, round_num):
            a_reply += delta
            yield {"type": "chunk", "round": round_num, "speaker": "A", "delta": delta}
        transcript.append({"round": round_num, "speaker": "A", "text": a_reply})
        a_history.append({"role": "assistant", "content": a_reply})
        b_history.append({"role": "user", "content": a_reply})
        yield {"type": "message_done", "round": round_num, "speaker": "A", "text": a_reply}
        pace(a_reply)

    yield {
        "type": "stopped",
        "question_id": question_obj["id"],
        "question": question,
        "tactic": tactic_name,
        "num_rounds": round_num,
        "transcript": transcript,
    }


def _trim_incomplete_tail(text: str) -> str:
    """Cuts off a trailing partial sentence (from hitting the token limit mid-thought) so the
    other agent never sees a dangling fragment and tries to finish it themselves."""
    text = text.strip()
    if not text or text[-1] in '.!?"\'”’)':
        return text
    cut_points = [text.rfind(p) for p in ".!?"]
    cut = max(cut_points)
    if cut == -1:
        return text  # no sentence boundary found at all; leave it rather than return nothing
    return text[: cut + 1].strip()


def run_free_debate_stream(stop_event):
    """Two symmetric agents pick their own topic and argue it out indefinitely.

    No seed question, no correct/wrong side — they decide what to argue about and how.
    Runs until stop_event is set, checked between turns so the in-flight reply always finishes.
    """
    history1: list[dict] = [{"role": "user", "content": debater.OPENING_PROMPT}]
    history2: list[dict] = []
    transcript = []
    round_num = 0

    def pace(text: str):
        # Only needed when generation (e.g. Groq) can outrun the client's typewriter display.
        # Local CPU generation is already far slower than the display, so skip the extra wait.
        if RUN_MODE == "local" or stop_event.is_set():
            return
        seconds = min(len(text) * _PACING_SECONDS_PER_CHAR, _MAX_PACING_SECONDS)
        stop_event.wait(seconds)

    while not stop_event.is_set():
        round_num += 1

        reply1 = ""
        for delta in debater.respond_stream_1(history1):
            reply1 += delta
            yield {"type": "chunk", "round": round_num, "speaker": "A", "delta": delta}
        reply1_clean = _trim_incomplete_tail(reply1)
        transcript.append({"round": round_num, "speaker": "A", "text": reply1_clean})
        history1.append({"role": "assistant", "content": reply1_clean})
        history2.append({"role": "user", "content": reply1_clean})
        yield {"type": "message_done", "round": round_num, "speaker": "A", "text": reply1_clean}
        pace(reply1)

        if stop_event.is_set():
            break

        reply2 = ""
        for delta in debater.respond_stream_2(history2):
            reply2 += delta
            yield {"type": "chunk", "round": round_num, "speaker": "B", "delta": delta}
        reply2_clean = _trim_incomplete_tail(reply2)
        transcript.append({"round": round_num, "speaker": "B", "text": reply2_clean})
        history2.append({"role": "assistant", "content": reply2_clean})
        history1.append({"role": "user", "content": reply2_clean})
        yield {"type": "message_done", "round": round_num, "speaker": "B", "text": reply2_clean}
        pace(reply2)

    yield {"type": "stopped", "num_rounds": round_num, "transcript": transcript}


def save_result(result: dict) -> Path:
    out_path = LOG_DIR / f"{result['question_id']}_{result['tactic']}_{result['debate_id'][:8]}.json"
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    return out_path


def run_all(question_ids: list[str] | None = None, tactic_names: list[str] | None = None) -> list[dict]:
    questions = load_questions()
    tactics = load_tactics()

    if question_ids:
        questions = [q for q in questions if q["id"] in question_ids]
    if tactic_names:
        tactics = {k: v for k, v in tactics.items() if k in tactic_names}

    results = []
    for q in questions:
        for tactic_name, tactic_desc in tactics.items():
            print(f"Running debate: {q['id']} / {tactic_name} ...")
            result = run_debate(q, tactic_name, tactic_desc)
            save_result(result)
            verdict = "CAVED" if result["caved"] else "HELD"
            print(f"  -> {verdict} (flip_round={result['flip_round']})")
            results.append(result)
    return results


if __name__ == "__main__":
    run_all()
