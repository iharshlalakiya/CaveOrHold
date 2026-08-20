"""Thin wrapper around a local transformers pipeline, the HF Inference API, or Groq."""
import json
import threading
import time
import requests
from caveorhold.config import HF_TOKEN, GROQ_API_KEY, RUN_MODE, DEVICE

_local_pipelines = {}
_local_models = {}  # model_name -> (model, tokenizer), used for streamed generation


def _get_local_pipeline(model_name: str):
    if model_name not in _local_pipelines:
        from transformers import pipeline
        _local_pipelines[model_name] = pipeline(
            "text-generation",
            model=model_name,
            device_map=DEVICE if DEVICE != "cpu" else None,
            token=HF_TOKEN or None,
        )
    return _local_pipelines[model_name]


def _get_local_model_and_tokenizer(model_name: str):
    if model_name not in _local_models:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        tokenizer = AutoTokenizer.from_pretrained(model_name, token=HF_TOKEN or None)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            token=HF_TOKEN or None,
            device_map=DEVICE if DEVICE != "cpu" else None,
        )
        if DEVICE == "cpu":
            model.to("cpu")
        _local_models[model_name] = (model, tokenizer)
    return _local_models[model_name]


def generate(model_name: str, messages: list[dict], max_new_tokens: int = 200) -> str:
    """messages: list of {"role": "system"|"user"|"assistant", "content": str}"""
    if RUN_MODE == "groq":
        return _generate_groq(model_name, messages, max_new_tokens)
    if RUN_MODE == "api":
        return _generate_api(model_name, messages, max_new_tokens)
    return _generate_local(model_name, messages, max_new_tokens)


def _generate_local(model_name: str, messages: list[dict], max_new_tokens: int) -> str:
    pipe = _get_local_pipeline(model_name)
    output = pipe(
        messages,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=0.7,
        pad_token_id=pipe.tokenizer.eos_token_id,
    )
    generated = output[0]["generated_text"]
    if isinstance(generated, list):
        return generated[-1]["content"].strip()
    return str(generated).strip()


def _generate_api(model_name: str, messages: list[dict], max_new_tokens: int) -> str:
    url = f"https://api-inference.huggingface.co/models/{model_name}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_new_tokens,
        "temperature": 0.7,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"].strip()


def _generate_groq(model_name: str, messages: list[dict], max_new_tokens: int) -> str:
    if not GROQ_API_KEY:
        raise RuntimeError("RUN_MODE=groq requires GROQ_API_KEY to be set in .env")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_new_tokens,
        "temperature": 0.7,
        "reasoning_effort": "low",
    }
    max_retries = 5
    for attempt in range(max_retries):
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("retry-after", 2 ** attempt))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    resp.raise_for_status()


def generate_stream(model_name: str, messages: list[dict], max_new_tokens: int = 200):
    """Yields text chunks as they're generated. Falls back to one chunk for non-streaming backends."""
    if RUN_MODE == "groq":
        yield from _generate_groq_stream(model_name, messages, max_new_tokens)
    elif RUN_MODE == "local":
        yield from _generate_local_stream(model_name, messages, max_new_tokens)
    else:
        yield generate(model_name, messages, max_new_tokens)


def _generate_local_stream(model_name: str, messages: list[dict], max_new_tokens: int):
    from transformers import TextIteratorStreamer

    model, tokenizer = _get_local_model_and_tokenizer(model_name)
    inputs = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
    )
    if DEVICE != "cpu":
        inputs = {k: v.to(DEVICE) for k, v in inputs.items()}

    streamer = TextIteratorStreamer(tokenizer, skip_prompt=True, skip_special_tokens=True)
    generation_kwargs = dict(
        **inputs,
        max_new_tokens=max_new_tokens,
        do_sample=True,
        temperature=0.7,
        pad_token_id=tokenizer.eos_token_id,
        streamer=streamer,
    )
    thread = threading.Thread(target=model.generate, kwargs=generation_kwargs, daemon=True)
    thread.start()
    for token_text in streamer:
        if token_text:
            yield token_text
    thread.join()


def _generate_groq_stream(model_name: str, messages: list[dict], max_new_tokens: int):
    if not GROQ_API_KEY:
        raise RuntimeError("RUN_MODE=groq requires GROQ_API_KEY to be set in .env")
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_new_tokens,
        "temperature": 0.7,
        "reasoning_effort": "low",
        "stream": True,
    }
    max_retries = 5
    for attempt in range(max_retries):
        resp = requests.post(url, headers=headers, json=payload, timeout=60, stream=True)
        if resp.status_code == 429:
            retry_after = float(resp.headers.get("retry-after", 2 ** attempt))
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        for raw_line in resp.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            line = raw_line.decode("utf-8")
            if not line.startswith("data: "):
                continue
            payload_str = line[len("data: "):]
            if payload_str.strip() == "[DONE]":
                return
            chunk = json.loads(payload_str)
            choices = chunk.get("choices")
            if not choices:
                continue
            delta = choices[0].get("delta", {}).get("content")
            if delta:
                yield delta
        return
    resp.raise_for_status()
