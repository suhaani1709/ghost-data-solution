"""OpenRouter chat client with a committed response cache (stdlib only).

Every request is keyed by SHA-256 of (logical model, messages, parameters) and
its answer is stored in code/llm_cache/<key>.json. A cached answer is always
reused, so a run whose prompts are all cached makes no network call and is
byte-for-byte reproducible without a key. Cache misses call OpenRouter when
OPENROUTER_API_KEY is set (environment, or the repo-root .env file, which is
never committed); otherwise LLMUnavailable is raised and callers fall back to
the deterministic rules.

Free models are rate-limited and sometimes busy upstream: 429 / 5xx answers
are retried with backoff, then the next model in MODELS is tried. The model
that answered is stored with the answer. Live calls are appended to
code/llm_cache/usage_log.jsonl (time, model, tokens); per-run counters are in
Client.usage. The key itself is never written anywhere.

ClaudeCodeClient has the same interface and cache, but the model is Claude
(Sonnet by default) run through Claude Code's headless mode (`claude -p`) on
the user's Claude subscription. Each call is one stateless completion: the
system prompt replaces Claude Code's own, and no tools, MCP servers or project
files are loaded, so the model sees only what the caller sends.
"""
import base64
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(__file__).resolve().parents[1] / "llm_cache"
# Free OpenRouter models, first = preferred. All three accept text and images.
MODELS = ("nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-31b-it:free",
          "google/gemma-4-26b-a4b-it:free")
RETRY_WAITS = (20, 45, 90)          # seconds, per model, on 429 / 5xx
PAUSE = 3                           # seconds between live calls


class LLMUnavailable(RuntimeError):
    """No cached answer and no way to get a live one."""


def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    env = REPO_ROOT / ".env"
    if not key and env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "OPENROUTER_API_KEY":
                key = value.strip().strip('"').strip("'")
    return key


def image_part(path) -> dict:
    data = base64.b64encode(Path(path).read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def extract_json(text: str):
    """The first JSON object or array in a model answer (code fences allowed)."""
    text = re.sub(r"```(?:json)?", "", text or "")
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in model answer")
    return json.JSONDecoder().raw_decode(text[min(starts):])[0]


class Client:
    def __init__(self, offline=False, cache_dir=CACHE_DIR):
        self.offline = offline
        self.cache_dir = Path(cache_dir)
        self.usage = Counter()          # calls / cache_hits / failures / tokens per model
        self.models_used = Counter()
        self._last_call = 0.0

    def _key(self, messages, params):
        blob = json.dumps({"model": MODELS[0], "messages": messages, "params": params},
                          sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def chat(self, messages: list[dict], purpose: str, max_tokens: int = 4000) -> str:
        """Answer text for `messages` (cache first). Raises LLMUnavailable."""
        params = {"temperature": 0, "max_tokens": max_tokens}
        key = self._key(messages, params)
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            entry = json.loads(path.read_text(encoding="utf-8"))
            self.usage["cache_hits"] += 1
            self._count(entry, live=False)
            return entry["answer"]
        token = None if self.offline else api_key()
        if not token:
            raise LLMUnavailable(f"no cached answer for {purpose} and no API key / offline")
        entry = self._call(token, messages, params, purpose)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")
        with open(self.cache_dir / "usage_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: entry[k] for k in ("created_at", "purpose", "model", "usage")},
                                sort_keys=True) + "\n")
        self._count(entry, live=True)
        return entry["answer"]

    def _count(self, entry, live):
        u = entry.get("usage") or {}
        m = entry["model"]
        self.models_used[m] += 1
        self.usage[f"{'live' if live else 'cached'}_calls"] += 1
        self.usage[f"{m}|prompt_tokens"] += u.get("prompt_tokens", 0)
        self.usage[f"{m}|completion_tokens"] += u.get("completion_tokens", 0)

    def _call(self, token, messages, params, purpose):
        last = None
        for model in MODELS:
            for wait in RETRY_WAITS + (None,):
                time.sleep(max(0.0, PAUSE - (time.time() - self._last_call)))
                self._last_call = time.time()
                body = json.dumps({"model": model, "messages": messages, **params}).encode("utf-8")
                req = urllib.request.Request(ENDPOINT, data=body, headers={
                    "Authorization": f"Bearer {token}", "Content-Type": "application/json",
                    "X-Title": "ghost-data-deletion-audit"})
                try:
                    with urllib.request.urlopen(req, timeout=300) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    data = {"error": {"code": e.code, "message": e.read().decode("utf-8", "replace")[:300]}}
                except (urllib.error.URLError, TimeoutError) as e:
                    data = {"error": {"code": "network", "message": str(e)[:300]}}
                err = data.get("error")
                answer = None if err else (data.get("choices") or [{}])[0].get("message", {}).get("content")
                if answer:
                    return {"created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "purpose": purpose, "model": data.get("model", model),
                            "usage": data.get("usage") or {}, "answer": answer}
                self.usage["failures"] += 1
                last = err or {"code": "empty", "message": "empty answer"}
                code = str(last.get("code"))
                log.warning("LLM %s on %s: %s %s", purpose, model, code, str(last.get("message"))[:120])
                if wait is None or not (code in ("429", "network", "empty") or code.startswith("5")):
                    break
                time.sleep(wait)
        raise LLMUnavailable(f"{purpose}: every model failed, last error {last}")


class ClaudeCodeClient(Client):
    """Claude via `claude -p` (Claude Code headless mode); same cache and usage counters."""

    FLAGS = ("--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
             "--exclude-dynamic-system-prompt-sections", "--no-session-persistence",
             "--output-format", "json")
    TEXT_ONLY = ("--tools", "", "--max-turns", "1")
    # Image input: the only tool is Read, inside a temp dir that holds just the image copy.
    READ_IMAGE = ("--tools", "Read", "--allowedTools", "Read", "--max-turns", "3")

    def __init__(self, model: str = "sonnet", offline: bool = False, cache_dir=CACHE_DIR,
                 timeout: int = 300):
        super().__init__(offline=offline, cache_dir=cache_dir)
        self.model = model
        self.timeout = timeout

    def _key(self, messages, params):
        blob = json.dumps({"backend": "claude-code", "model": self.model, "messages": messages,
                           "params": params}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    @staticmethod
    def render(messages: list[dict]) -> tuple[str, str]:
        """(system prompt, transcript) for a stateless `claude -p` call."""
        system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        turns = [f"### {m['role'].upper()}\n{m['content']}" for m in messages if m["role"] != "system"]
        return system, "\n\n".join(turns) + "\n\n### ASSISTANT\n"

    def _image_key(self, system, image_path, max_tokens):
        digest = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
        blob = json.dumps({"backend": "claude-code", "model": self.model, "system": system,
                           "image_sha256": digest, "params": {"max_tokens": max_tokens}}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def chat_image(self, system: str, image_path, purpose: str, max_tokens: int = 4000) -> str:
        """Answer for one image (Claude reads it with the Read tool). Cached by image content."""
        name = Path(image_path).name
        prompt = (f"Read the image file {name} in the current directory with the Read tool, then "
                  "answer as the system prompt instructs. Reply with the JSON only.")
        return self._cached(self._image_key(system, image_path, max_tokens), purpose,
                            lambda: self._run_cli(system, prompt, purpose, self.READ_IMAGE, [image_path]))

    def chat(self, messages: list[dict], purpose: str, max_tokens: int = 4000) -> str:
        system, prompt = self.render(messages)
        return self._cached(self._key(messages, {"max_tokens": max_tokens}), purpose,
                            lambda: self._run_cli(system, prompt, purpose, self.TEXT_ONLY, []))

    def _cached(self, key, purpose, run):
        path = self.cache_dir / f"{key}.json"
        if path.is_file():
            entry = json.loads(path.read_text(encoding="utf-8"))
            self.usage["cache_hits"] += 1
            self._count(entry, live=False)
            return entry["answer"]
        if self.offline or shutil.which("claude") is None:
            raise LLMUnavailable(f"no cached answer for {purpose} and Claude Code is unavailable / offline")
        entry = run()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                        encoding="utf-8")
        with open(self.cache_dir / "usage_log.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: entry[k] for k in ("created_at", "purpose", "model", "usage")},
                                sort_keys=True) + "\n")
        self._count(entry, live=True)
        return entry["answer"]

    def _run_cli(self, system, prompt, purpose, tool_flags, files):
        cmd = ["claude", "-p", "--model", self.model, "--system-prompt", system, *self.FLAGS, *tool_flags]
        last = None
        for wait in RETRY_WAITS + (None,):
            stderr = ""
            with tempfile.TemporaryDirectory() as empty:       # no CLAUDE.md / project context
                for f in files:
                    shutil.copy(f, Path(empty) / Path(f).name)
                try:
                    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                          cwd=empty, timeout=self.timeout)
                    stderr = proc.stderr
                    data = json.loads(proc.stdout or "{}")
                except (subprocess.TimeoutExpired, ValueError) as e:
                    data = {"is_error": True, "result": str(e)[:300]}
            answer = data.get("result")
            if answer and not data.get("is_error"):
                u = data.get("usage") or {}
                models = list((data.get("modelUsage") or {}).keys())
                return {"created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "purpose": purpose, "model": models[0] if models else self.model,
                        "usage": {"prompt_tokens": u.get("input_tokens", 0)
                                  + u.get("cache_creation_input_tokens", 0)
                                  + u.get("cache_read_input_tokens", 0),
                                  "completion_tokens": u.get("output_tokens", 0),
                                  "cache_read_tokens": u.get("cache_read_input_tokens", 0),
                                  "cost_usd_equivalent": data.get("total_cost_usd", 0)},
                        "answer": answer}
            self.usage["failures"] += 1
            last = str(data.get("result") or stderr or data)[:200]
            log.warning("Claude Code %s failed: %s", purpose, last)
            if wait is None:
                break
            time.sleep(wait)
        raise LLMUnavailable(f"{purpose}: Claude Code failed, last error {last}")
