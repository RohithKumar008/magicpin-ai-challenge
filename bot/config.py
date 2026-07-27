import os

LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
TEAM_NAME = os.environ.get("TEAM_NAME", "Team Vera")
TEAM_MEMBERS = os.environ.get("TEAM_MEMBERS", "you").split(",")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "team@example.com")
BOT_VERSION = os.environ.get("BOT_VERSION", "1.0.0")
