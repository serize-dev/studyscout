"""A multi-line, wrapping chat input. Enter sends; Ctrl+J inserts a newline."""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea


class ChatInput(TextArea):
    """TextArea that wraps text down instead of scrolling right, and submits on Enter."""

    class Submitted(Message):
        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    class Revise(Message):
        """Ctrl+U — ask Wintermute to update me.md from the conversation."""

    class Compose(Message):
        """Ctrl+E — fold the conversation's refinements into an outreach email."""

    def __init__(self, placeholder: str = "", **kwargs):
        super().__init__("", soft_wrap=True, **kwargs)
        self.show_line_numbers = False
        self._placeholder = placeholder

    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            text = self.text.strip()
            if text:
                self.text = ""
                self.post_message(self.Submitted(text))
        elif event.key == "ctrl+j":
            event.prevent_default()
            event.stop()
            self.insert("\n")
        elif event.key == "ctrl+u":
            event.prevent_default()
            event.stop()
            self.post_message(self.Revise())
        elif event.key == "ctrl+e":
            event.prevent_default()
            event.stop()
            self.post_message(self.Compose())
