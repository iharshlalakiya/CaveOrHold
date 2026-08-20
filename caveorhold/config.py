import os
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
RUN_MODE = os.getenv("RUN_MODE", "local")
AGENT_A_MODEL = os.getenv("AGENT_A_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
AGENT_B_MODEL = os.getenv("AGENT_B_MODEL", "Qwen/Qwen2.5-1.5B-Instruct")
VERIFIER_MODEL = os.getenv("VERIFIER_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
NUM_ROUNDS = int(os.getenv("NUM_ROUNDS", "3"))
DEVICE = os.getenv("DEVICE", "cpu")
