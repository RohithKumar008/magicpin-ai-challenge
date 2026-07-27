import json
import ssl
from urllib import request as urlrequest
from bot.config import LLM_PROVIDER, LLM_API_KEY, LLM_MODEL, OLLAMA_URL

TIMEOUT = 45

def _ctx():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.0, max_tokens: int = 1500) -> str:
    if LLM_PROVIDER == "openai":
        return _call_openai(system_prompt, user_prompt, temperature, max_tokens)
    elif LLM_PROVIDER == "anthropic":
        return _call_anthropic(system_prompt, user_prompt, temperature, max_tokens)
    elif LLM_PROVIDER == "deepseek":
        return _call_deepseek(system_prompt, user_prompt, temperature, max_tokens)
    elif LLM_PROVIDER == "ollama":
        return _call_ollama(system_prompt, user_prompt, temperature, max_tokens)
    elif LLM_PROVIDER == "gemini":
        return _call_gemini(system_prompt, user_prompt, temperature, max_tokens)
    elif LLM_PROVIDER == "nvidia":
        return _call_nvidia(system_prompt, user_prompt, temperature, max_tokens)
    else:
        return _call_openai(system_prompt, user_prompt, temperature, max_tokens)

def _call_openai_compat(base_url: str, system: str, user: str, temp: float, max_tok: int, model: str = None) -> str:
    import socket
    m = model or LLM_MODEL or "gpt-4o-mini"
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": m, "temperature": temp, "max_tokens": max_tok,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]
    }).encode()
    req = urlrequest.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    )
    resp = urlrequest.urlopen(req, timeout=25, context=_ctx())
    data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]

def _call_openai(system: str, user: str, temp: float, max_tok: int) -> str:
    return _call_openai_compat("https://api.openai.com/v1", system, user, temp, max_tok)

AVAILABLE_NVIDIA = [
    "meta/llama-3.2-3b-instruct",
]

def _call_nvidia(system: str, user: str, temp: float, max_tok: int) -> str:
    model = LLM_MODEL or "meta/llama-3.2-3b-instruct"
    return _call_openai_compat(
        base_url="https://integrate.api.nvidia.com/v1",
        system=system, user=user, temp=temp, max_tok=max_tok,
        model=model
    )

def _call_anthropic(system: str, user: str, temp: float, max_tok: int) -> str:
    model = LLM_MODEL or "claude-3-5-sonnet-20241022"
    body = json.dumps({
        "model": model, "max_tokens": max_tok, "temperature": temp,
        "messages": [{"role": "user", "content": user}],
        "system": system
    }).encode()
    req = urlrequest.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={"x-api-key": LLM_API_KEY, "Content-Type": "application/json", "anthropic-version": "2023-06-01"}
    )
    resp = urlrequest.urlopen(req, timeout=TIMEOUT, context=_ctx())
    data = json.loads(resp.read().decode())
    return data["content"][0]["text"]

def _call_deepseek(system: str, user: str, temp: float, max_tok: int) -> str:
    model = LLM_MODEL or "deepseek-chat"
    body = json.dumps({
        "model": model, "temperature": temp, "max_tokens": max_tok,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]
    }).encode()
    req = urlrequest.Request(
        "https://api.deepseek.com/v1/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {LLM_API_KEY}", "Content-Type": "application/json"}
    )
    resp = urlrequest.urlopen(req, timeout=TIMEOUT, context=_ctx())
    data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]

def _call_gemini(system: str, user: str, temp: float, max_tok: int) -> str:
    model = LLM_MODEL or "gemini-2.0-flash"
    full = f"{system}\n\n{user}"
    body = json.dumps({
        "contents": [{"parts": [{"text": full}]}],
        "generationConfig": {"temperature": temp, "maxOutputTokens": max_tok}
    }).encode()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={LLM_API_KEY}"
    req = urlrequest.Request(url, data=body, headers={"Content-Type": "application/json"})
    resp = urlrequest.urlopen(req, timeout=TIMEOUT, context=_ctx())
    data = json.loads(resp.read().decode())
    return data["candidates"][0]["content"]["parts"][0]["text"]

def _call_ollama(system: str, user: str, temp: float, max_tok: int) -> str:
    model = LLM_MODEL or "llama3"
    full = f"{system}\n\n{user}"
    body = json.dumps({"model": model, "prompt": full, "stream": False, "options": {"temperature": temp}}).encode()
    req = urlrequest.Request(f"{OLLAMA_URL}/api/generate", data=body, headers={"Content-Type": "application/json"})
    resp = urlrequest.urlopen(req, timeout=60, context=_ctx())
    data = json.loads(resp.read().decode())
    return data["response"]
