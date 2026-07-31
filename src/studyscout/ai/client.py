"""Async LLM wrapper — Anthropic / OpenRouter / OpenAI. Lazy; runs dark w/o a key."""

from __future__ import annotations

from ..config import Config

OPENAI_COMPAT = {
    "openrouter": ("https://openrouter.ai/api/v1/chat/completions",
                   {"X-Title": "StudyScout", "HTTP-Referer": "https://localhost/studyscout"}),
    "openai": ("https://api.openai.com/v1/chat/completions", {}),
}


def load_site(cfg: Config, limit: int = 6000) -> str:
    """The site profile (site.md) Wintermute pitches with."""
    return cfg.me_text(limit)


class BrainError(RuntimeError):
    pass


def system_blocks(stable: str, volatile: str = "") -> list[dict]:
    """Split a system prompt for prompt caching: the stable prefix (persona +
    site profile) gets a cache breakpoint; per-study/dossier context follows.
    Anthropic serves the prefix from cache (~90% cheaper) on repeat calls.
    """
    blocks = [{"type": "text", "text": stable,
               "cache_control": {"type": "ephemeral"}}]
    if volatile.strip():
        blocks.append({"type": "text", "text": volatile})
    return blocks


def _system_text(system) -> str:
    """Flatten block-style system prompts for OpenAI-compatible providers."""
    if isinstance(system, str):
        return system
    return "\n\n".join(b.get("text", "") for b in system if isinstance(b, dict))


class Brain:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.provider = cfg.provider()
        self._key = cfg.api_key()
        self._client = None
        self.model = cfg.model_for("consigliere")
        self.max_tokens = int(cfg.get("ai.max_tokens", 2048))

    @property
    def enabled(self) -> bool:
        return bool(self._key) and bool(self.cfg.get("ai.enabled", True))

    def _anthropic(self):
        if self._client is None:
            try:
                from anthropic import AsyncAnthropic
            except Exception as exc:  # pragma: no cover
                raise BrainError(f"anthropic SDK unavailable: {exc}")
            self._client = AsyncAnthropic(api_key=self._key)
        return self._client

    @staticmethod
    def _is_fable(model: str) -> bool:
        return (model or "").startswith("claude-fable")

    async def _complete_anthropic(self, system, user, model, max_tokens, history):
        msgs = list(history or []) + [{"role": "user", "content": user}]
        client = self._anthropic()
        try:
            if self._is_fable(model):
                # Fable 5: thinking is always on and counts against max_tokens,
                # so give it headroom; safety classifiers can decline a benign
                # request, so opt into the server-side Opus 4.8 fallback.
                resp = await client.beta.messages.create(
                    model=model, max_tokens=max(max_tokens, 8192),
                    system=system, messages=msgs,
                    betas=["server-side-fallback-2026-06-01"],
                    fallbacks=[{"model": "claude-opus-4-8"}])
            else:
                resp = await client.messages.create(
                    model=model, max_tokens=max_tokens, system=system, messages=msgs)
        except Exception as exc:
            raise BrainError(str(exc))
        if getattr(resp, "stop_reason", None) == "refusal":
            raise BrainError("Model declined this request (safety refusal) — try rephrasing.")
        return "".join(b.text for b in resp.content if getattr(b, "type", None) == "text").strip()

    async def _complete_openai(self, system, user, model, max_tokens, history):
        import httpx
        url, extra = OPENAI_COMPAT[self.provider]
        msgs = [{"role": "system", "content": _system_text(system)}] + list(history or []) + [{"role": "user", "content": user}]
        headers = {"Authorization": f"Bearer {self._key}", **extra}
        try:
            async with httpx.AsyncClient(timeout=60) as c:
                r = await c.post(url, headers=headers,
                                 json={"model": model, "messages": msgs, "max_tokens": max_tokens})
            if r.status_code != 200:
                raise BrainError(f"{self.provider} {r.status_code}: {r.text[:160]}")
            return (r.json()["choices"][0]["message"]["content"] or "").strip()
        except BrainError:
            raise
        except Exception as exc:
            raise BrainError(str(exc))

    async def complete(self, system: str, user: str, *, model=None, max_tokens=None, history=None) -> str:
        if not self._key:
            raise BrainError("No API key set — Wintermute is dark.")
        model = model or self.model
        max_tokens = max_tokens or self.max_tokens
        if self.provider in OPENAI_COMPAT:
            return await self._complete_openai(system, user, model, max_tokens, history)
        return await self._complete_anthropic(system, user, model, max_tokens, history)

    def _web_search_tool_type(self, model: str) -> str:
        """Pick the web_search tool version the model supports."""
        m = (model or "").lower()
        if any(tag in m for tag in ("opus-4", "sonnet-5", "sonnet-4-6", "fable")):
            return "web_search_20260209"
        return "web_search_20250305"

    async def web_hunt(self, system: str, user: str, max_searches: int = 5) -> str:
        """Let Claude search the live web (Anthropic server-side web_search tool).

        Returns the model's final text. Anthropic-only — the tool isn't exposed
        the same way on OpenRouter/OpenAI.
        """
        if self.provider != "anthropic":
            raise BrainError("Sponsor intel needs the Anthropic provider (web_search tool). "
                             "Switch provider in Models.")
        client = self._anthropic()
        model = self.model
        tools = [{"type": self._web_search_tool_type(model), "name": "web_search",
                  "max_uses": max(1, int(max_searches))}]
        messages = [{"role": "user", "content": user}]
        parts: list[str] = []
        # Server-side tools can stop with pause_turn mid-hunt (several searches +
        # thinking = a long turn). Feed the partial turn back and continue, else
        # the reply comes back half-cooked. (Lesson imported from ICEbreaker.)
        for _round in range(8):
            try:
                if self._is_fable(model):
                    resp = await client.beta.messages.create(
                        model=model, max_tokens=16000, system=system,
                        messages=messages, tools=tools,
                        betas=["server-side-fallback-2026-06-01"],
                        fallbacks=[{"model": "claude-opus-4-8"}])
                else:
                    resp = await client.messages.create(
                        model=model, max_tokens=8000, system=system,
                        messages=messages, tools=tools)
            except Exception as exc:
                raise BrainError(str(exc))
            stop = getattr(resp, "stop_reason", None)
            if stop == "refusal":
                raise BrainError("Model declined this request (safety refusal) — try rephrasing.")
            parts.extend(b.text for b in resp.content
                         if getattr(b, "type", None) == "text")
            if stop != "pause_turn":
                break
            messages = messages + [{"role": "assistant", "content": resp.content}]
        return "".join(parts).strip()

    async def ping(self) -> tuple[bool, str]:
        if not self._key:
            return False, "no key set"
        try:
            await self.complete("Reply with: ok", "ping", max_tokens=5)
            return True, f"connected · {self.provider}:{self.model}"
        except BrainError as exc:
            msg = str(exc)
            if "401" in msg or "authentication" in msg.lower() or "invalid x-api-key" in msg.lower():
                msg = "401 — key rejected. Check the key (and for a stale env var)."
            return False, msg
