"""Local TextExpander client — syncs snippets from remote API and runs keyboard expansion."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import requests
from pynput import keyboard

# --- Config ---

CONFIG_DIR = Path.home() / ".textexpander"
CONFIG_PATH = CONFIG_DIR / "config.json"
CACHE_PATH = CONFIG_DIR / "snippets.json"
SYNC_INTERVAL = 30  # seconds

# Set this to your deployed Railway URL (or override via env var)
SERVER_URL = os.environ.get("TEXTEXPANDER_URL", "https://textexpander-production.up.railway.app")

RESET_KEYS = {keyboard.Key.space, keyboard.Key.enter, keyboard.Key.tab}
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
MARKDOWN_ITALIC_RE = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
FORMATTING_RE = re.compile(r"\*\*.+?\*\*|\*(?!\*).+?(?<!\*)\*(?!\*)|\[.+?\]\(.+?\)")


# --- Config management ---

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


# --- Snippet management ---

def load_cached_snippets() -> list[dict]:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return []


def save_cached_snippets(snippets: list[dict]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_PATH.write_text(json.dumps(snippets, indent=2))


def sync_snippets(api_key: str) -> list[dict] | None:
    """Fetch snippets from the remote API. Returns None on failure."""
    try:
        resp = requests.get(
            f"{SERVER_URL}/api/snippets",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            snippets = resp.json()
            save_cached_snippets(snippets)
            return snippets
        else:
            print(f"  Sync failed (HTTP {resp.status_code})")
    except requests.RequestException as e:
        print(f"  Sync error: {e}")
    return None


def check_paused(api_key: str) -> bool | None:
    """Check if user has paused expansion. Returns None on failure."""
    try:
        resp = requests.get(
            f"{SERVER_URL}/api/me",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json().get("paused", False)
    except requests.RequestException:
        pass
    return None


# --- Rich text helpers (macOS) ---

def _has_formatting(text: str) -> bool:
    return bool(FORMATTING_RE.search(text))


def _markdown_to_html(text: str) -> str:
    html = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = MARKDOWN_BOLD_RE.sub(r"<b>\1</b>", html)
    html = MARKDOWN_ITALIC_RE.sub(r"<i>\1</i>", html)
    html = MARKDOWN_LINK_RE.sub(r'<a href="\2">\1</a>', html)
    html = html.replace("\n", "<br>")
    return html


def _set_clipboard_rich(html: str, plain: str) -> None:
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
    text = MARKDOWN_BOLD_RE.sub(r"\1", text)
    text = MARKDOWN_ITALIC_RE.sub(r"\1", text)
    return MARKDOWN_LINK_RE.sub(r"\1", text)


# --- Keyboard expansion ---

class Expander:
    def __init__(self) -> None:
        self._buffer = ""
        self._listener: keyboard.Listener | None = None
        self._controller = keyboard.Controller()
        self._snippets: list[dict] = []
        self._lock = threading.Lock()

    def set_snippets(self, snippets: list[dict]) -> None:
        with self._lock:
            self._snippets = list(snippets)

    def start(self) -> None:
        self._listener = keyboard.Listener(on_press=self._on_press)
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    def _on_press(self, key) -> None:
        if key in RESET_KEYS:
            # Check for expansion before clearing — trigger on space/enter/tab
            if self._buffer and self._check_expansion(triggered_by_reset=True):
                return
            self._buffer = ""
            return

        if key == keyboard.Key.backspace:
            self._buffer = self._buffer[:-1]
            return

        try:
            char = key.char
        except AttributeError:
            return

        if char is None:
            return

        self._buffer += char
        self._check_expansion()

    def _check_expansion(self, triggered_by_reset=False) -> bool:
        with self._lock:
            snippets = list(self._snippets)

        for snippet in snippets:
            abbr = snippet["abbreviation"]
            if self._buffer.endswith(abbr):
                self._expand(abbr, snippet["expansion"], delete_trailing=triggered_by_reset)
                return True
        return False

    def _expand(self, abbreviation: str, expansion: str, delete_trailing: bool = False) -> None:
        # Delete the trailing space/enter/tab that triggered the expansion
        if delete_trailing:
            self._controller.press(keyboard.Key.backspace)
            self._controller.release(keyboard.Key.backspace)
            time.sleep(0.02)

        for _ in range(len(abbreviation)):
            self._controller.press(keyboard.Key.backspace)
            self._controller.release(keyboard.Key.backspace)
            time.sleep(0.02)

        time.sleep(0.05)

        if _has_formatting(expansion):
            html = _markdown_to_html(expansion)
            plain = _get_plain_text(expansion)
            _set_clipboard_rich(html, plain)
            time.sleep(0.05)
            self._controller.press(keyboard.Key.cmd)
            self._controller.press("v")
            self._controller.release("v")
            self._controller.release(keyboard.Key.cmd)
        else:
            for char in expansion:
                self._controller.type(char)
                time.sleep(0.02)

        self._buffer = ""


# --- Auth flow ---

def authenticate() -> str:
    """Open browser for auth and prompt user to paste their API key."""
    print(f"\nOpening browser to sign in at {SERVER_URL} ...")
    webbrowser.open(f"{SERVER_URL}/auth/device")
    print()
    api_key = input("Paste your API key here: ").strip()
    if not api_key:
        print("No API key provided. Exiting.")
        sys.exit(1)
    return api_key


# --- Main ---

def main():
    config = load_config()
    api_key = config.get("api_key")

    if not api_key:
        api_key = authenticate()
        config["api_key"] = api_key
        save_config(config)
        print("API key saved.\n")

    # Initial sync
    print("Syncing snippets...")
    snippets = sync_snippets(api_key)
    if snippets is None:
        snippets = load_cached_snippets()
        if snippets:
            print(f"  Using {len(snippets)} cached snippets.")
        else:
            print("  No cached snippets. Will retry on next sync.")
    else:
        print(f"  Loaded {len(snippets)} snippets.")

    # Start expander
    expander = Expander()
    expander.set_snippets(snippets)
    is_paused = False
    paused_status = check_paused(api_key)
    if paused_status:
        is_paused = True
        print("\nTextExpander is paused (toggle on in the web dashboard).\n")
    else:
        expander.start()
        print("\nTextExpander is running. Press Ctrl+C to stop.\n")

    # Background sync loop
    try:
        while True:
            time.sleep(SYNC_INTERVAL)
            updated = sync_snippets(api_key)
            if updated is not None:
                expander.set_snippets(updated)

            paused_status = check_paused(api_key)
            if paused_status is not None:
                if paused_status and not is_paused:
                    expander.stop()
                    is_paused = True
                    print("  Expansion paused.")
                elif not paused_status and is_paused:
                    expander.start()
                    is_paused = False
                    print("  Expansion resumed.")
    except KeyboardInterrupt:
        print("\nStopping...")
        expander.stop()


if __name__ == "__main__":
    main()
