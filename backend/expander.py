"""Keyboard monitoring and text expansion logic using pynput."""

from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from pynput import keyboard

SNIPPETS_PATH = Path.home() / ".textexpander" / "snippets.json"
RESET_KEYS = {keyboard.Key.space, keyboard.Key.enter, keyboard.Key.tab}
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
MARKDOWN_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
FORMATTING_RE = re.compile(r"\*\*.+?\*\*|\*(?!\*).+?(?<!\*)\*(?!\*)|\[.+?\]\(.+?\)")


def load_snippets() -> List[Dict]:
    if not SNIPPETS_PATH.exists():
        SNIPPETS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNIPPETS_PATH.write_text("[]")
        return []
    return json.loads(SNIPPETS_PATH.read_text())


def save_snippets(snippets: List[Dict]) -> None:
    SNIPPETS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNIPPETS_PATH.write_text(json.dumps(snippets, indent=2))


def _has_formatting(text: str) -> bool:
    return bool(FORMATTING_RE.search(text))


def _markdown_to_html(text: str) -> str:
    """Convert markdown bold, italic, and links to HTML."""
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = MARKDOWN_BOLD_RE.sub(r"<b>\1</b>", html)
    html = MARKDOWN_ITALIC_RE.sub(r"<i>\1</i>", html)
    html = MARKDOWN_LINK_RE.sub(r'<a href="\2">\1</a>', html)
    html = html.replace("\n", "<br>")
    return html


def _set_clipboard_rich(html: str, plain: str) -> None:
    """Put both HTML and plain-text representations on the macOS pasteboard."""
    # Use osascript to set clipboard with rich text via NSPasteboard
    script = """
use framework "AppKit"
use scripting additions

set theHTML to "%s"
set thePlain to "%s"

set pb to current application's NSPasteboard's generalPasteboard()
pb's clearContents()

set htmlData to (current application's NSString's stringWithString:theHTML)'s dataUsingEncoding:(current application's NSUTF8StringEncoding)
pb's setData:htmlData forType:"public.html"
pb's setString:thePlain forType:(current application's NSPasteboardTypeString)
""" % (html.replace("\\", "\\\\").replace('"', '\\"'),
       plain.replace("\\", "\\\\").replace('"', '\\"'))
    subprocess.run(["osascript", "-l", "AppleScript", "-e", script],
                   capture_output=True, timeout=5)


def _get_plain_text(text: str) -> str:
    """Strip markdown formatting to plain text."""
    text = MARKDOWN_BOLD_RE.sub(r"\1", text)
    text = MARKDOWN_ITALIC_RE.sub(r"\1", text)
    return MARKDOWN_LINK_RE.sub(r"\1", text)


class Expander:
    def __init__(self) -> None:
        self._buffer = ""
        self._listener: Optional[keyboard.Listener] = None
        self._controller = keyboard.Controller()
        self._running = False
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._buffer = ""
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        # Reset buffer on space/enter/tab
        if key in RESET_KEYS:
            self._buffer = ""
            return

        # Handle backspace
        if key == keyboard.Key.backspace:
            self._buffer = self._buffer[:-1]
            return

        # Only care about character keys
        try:
            char = key.char
        except AttributeError:
            return

        if char is None:
            return

        self._buffer += char
        self._check_expansion()

    def _check_expansion(self) -> None:
        snippets = load_snippets()
        for snippet in snippets:
            abbr = snippet["abbreviation"]
            if self._buffer.endswith(abbr):
                expansion = snippet["expansion"]
                self._expand(abbr, expansion)
                break

    def _expand(self, abbreviation: str, expansion: str) -> None:
        # Delete the abbreviation by sending backspaces
        for _ in range(len(abbreviation)):
            self._controller.press(keyboard.Key.backspace)
            self._controller.release(keyboard.Key.backspace)
            time.sleep(0.02)

        time.sleep(0.05)

        if _has_formatting(expansion):
            # Rich text path: set clipboard and paste
            html = _markdown_to_html(expansion)
            plain = _get_plain_text(expansion)
            _set_clipboard_rich(html, plain)
            time.sleep(0.05)
            # Cmd+V to paste
            self._controller.press(keyboard.Key.cmd)
            self._controller.press("v")
            self._controller.release("v")
            self._controller.release(keyboard.Key.cmd)
        else:
            # Plain text path: type character by character
            for char in expansion:
                self._controller.type(char)
                time.sleep(0.02)

        self._buffer = ""
