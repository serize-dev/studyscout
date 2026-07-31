"""Models & provider — pick Wintermute's brain. Radio sets, never dropdowns."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import RadioButton, RadioSet, Static

PROVIDERS = [("Anthropic (direct)", "anthropic"),
             ("OpenRouter", "openrouter"), ("OpenAI (direct)", "openai")]

CATALOG = {
    "anthropic": [
        ("Opus 4.8 — strongest ($5/$25)", "claude-opus-4-8"),
        ("Sonnet 5 — near-Opus, cheaper ($3/$15)", "claude-sonnet-5"),
        ("Haiku 4.5 — fastest & cheapest ($1/$5)", "claude-haiku-4-5"),
        ("Fable 5 — most capable, pricey ($10/$50)", "claude-fable-5"),
    ],
    "openrouter": [
        ("Claude Opus 4.8", "anthropic/claude-opus-4.8"),
        ("Claude Sonnet 5", "anthropic/claude-sonnet-5"),
        ("GPT-4o", "openai/gpt-4o"),
    ],
    "openai": [("GPT-4o", "gpt-4o"), ("GPT-4o mini — cheap", "gpt-4o-mini"), ("GPT-4.1", "gpt-4.1")],
}


class ModelsScreen(ModalScreen):
    BINDINGS = [("escape", "dismiss", "close")]

    def __init__(self, engine):
        super().__init__()
        self.engine = engine
        self._loading = True

    def compose(self) -> ComposeResult:
        cfg = self.engine.cfg
        prov = cfg.provider()
        with Vertical(id="models-box"):
            yield Static(Text.from_markup("[#ffb000 b]MODELS · PROVIDER[/]"), classes="modal-title")
            yield Static(Text.from_markup(
                "[dim]Wintermute drafts outreach, judges fit, and preps you. Opus 4.8 for the "
                "sharpest calls; Sonnet 5 to save tokens.[/]"), classes="modal-help")
            with VerticalScroll():
                yield Static(Text.from_markup("\n[#33ff88]Provider[/]"))
                with RadioSet(id="prov"):
                    for label, value in PROVIDERS:
                        yield RadioButton(label, value=(value == prov))
                yield Static(Text.from_markup("[#33ff88]Wintermute model[/]"))
                yield from self._model_set(prov, cfg.model_for("consigliere"))
            yield Static(id="models-status", classes="modal-help")
            yield Static(Text.from_markup("[dim]changes save instantly · esc close[/]"), classes="modal-help")

    def _model_set(self, prov: str, current: str):
        vals = [v for _l, v in CATALOG[prov]]
        cur = current if current in vals else vals[0]
        with RadioSet(id="model"):
            for label, value in CATALOG[prov]:
                yield RadioButton(label, value=(value == cur))

    def on_mount(self) -> None:
        self._loading = False
        self._status()

    def _status(self) -> None:
        cfg = self.engine.cfg
        live = "●" if self.engine.ai_ready else "○"
        col = "#33ff88" if self.engine.ai_ready else "#ff5555"
        self.query_one("#models-status", Static).update(Text.from_markup(
            f"  active: [{col}]{live}[/] [b]{cfg.provider()}[/]  ·  [#ffb000]{cfg.model_for('consigliere')}[/]"))

    def _suffix(self, prov: str) -> str:
        return {"openrouter": "_openrouter", "openai": "_openai"}.get(prov, "")

    async def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if self._loading or event.index < 0:
            return
        cfg = self.engine.cfg
        if event.radio_set.id == "prov":
            prov = PROVIDERS[event.index][1]
            cfg.set("ai.provider", prov)
            # rebuild the model list for the new provider (mount-after-remove
            # must await — remove_children is async; see boards_screen lesson)
            self._loading = True
            old = self.query_one("#model", RadioSet)
            parent = old.parent
            await old.remove()
            new_set = RadioSet(id="model")
            await parent.mount(new_set)
            vals = [v for _l, v in CATALOG[prov]]
            cur = cfg.model_for("consigliere")
            cur = cur if cur in vals else vals[0]
            await new_set.mount(*[RadioButton(label, value=(value == cur))
                                  for label, value in CATALOG[prov]])
            self._loading = False
        else:
            prov = cfg.provider()
            cfg.set(f"ai.consigliere_model{self._suffix(prov)}",
                    CATALOG[prov][event.index][1])
        try:
            cfg.save()
            self.engine.reload_brain()
        except Exception as exc:  # noqa: BLE001
            self.notify(f"save failed: {exc}", severity="error")
            return
        self._status()
