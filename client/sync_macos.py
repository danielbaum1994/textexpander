"""Sync TextExpander snippets to macOS/iOS text replacements via the system database."""

from __future__ import annotations

import json
import os
import plistlib
import sqlite3
import subprocess
import sys
import time
import uuid
import webbrowser
from pathlib import Path

import requests

# --- Config (reused from expander.py) ---

CONFIG_DIR = Path.home() / ".textexpander"
CONFIG_PATH = CONFIG_DIR / "config.json"

SERVER_URL = os.environ.get("TEXTEXPANDER_URL", "https://textexpander-production.up.railway.app")

TEXT_REPLACEMENTS_DB = Path.home() / "Library" / "KeyboardServices" / "TextReplacements.db"

LAUNCHD_LABEL = "com.textexpander.sync"
LAUNCHD_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"


# --- Config management ---

def load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def save_config(config: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config, indent=2))


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


# --- API ---

def fetch_snippets(api_key: str) -> list[dict]:
    """Fetch snippets from the remote API."""
    resp = requests.get(
        f"{SERVER_URL}/api/snippets",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


# --- macOS Text Replacements DB ---

def read_macos_replacements(conn: sqlite3.Connection) -> dict[str, dict]:
    """Read z-prefixed text replacements from the macOS database.

    Returns {shortcut: {pk, phrase, was_deleted}} for all z-prefixed entries.
    """
    cursor = conn.execute(
        "SELECT Z_PK, ZSHORTCUT, ZPHRASE, ZWASDELETED FROM ZTEXTREPLACEMENTENTRY "
        "WHERE ZSHORTCUT LIKE 'm%'"
    )
    entries = {}
    for pk, shortcut, phrase, was_deleted in cursor:
        entries[shortcut] = {"pk": pk, "phrase": phrase, "was_deleted": was_deleted}
    return entries


def get_next_pk(conn: sqlite3.Connection) -> int:
    """Get the next available Z_PK value."""
    row = conn.execute("SELECT MAX(Z_PK) FROM ZTEXTREPLACEMENTENTRY").fetchone()
    return (row[0] or 0) + 1


def insert_replacement(conn: sqlite3.Connection, pk: int, shortcut: str, phrase: str) -> None:
    """Insert a new text replacement entry."""
    conn.execute(
        "INSERT INTO ZTEXTREPLACEMENTENTRY "
        "(Z_PK, Z_ENT, Z_OPT, ZWASDELETED, ZNEEDSSAVETOCLOUD, ZSHORTCUT, ZPHRASE, ZUNIQUENAME, ZTIMESTAMP) "
        "VALUES (?, 1, 1, 0, 1, ?, ?, ?, ?)",
        (pk, shortcut, phrase, str(uuid.uuid4()).upper(), time.time()),
    )


def update_replacement(conn: sqlite3.Connection, pk: int, phrase: str) -> None:
    """Update an existing text replacement's phrase."""
    conn.execute(
        "UPDATE ZTEXTREPLACEMENTENTRY SET ZPHRASE=?, ZNEEDSSAVETOCLOUD=1, ZTIMESTAMP=? WHERE Z_PK=?",
        (phrase, time.time(), pk),
    )


def soft_delete_replacement(conn: sqlite3.Connection, pk: int) -> None:
    """Mark a text replacement as deleted (for CloudKit sync)."""
    conn.execute(
        "UPDATE ZTEXTREPLACEMENTENTRY SET ZWASDELETED=1, ZNEEDSSAVETOCLOUD=1, ZTIMESTAMP=? WHERE Z_PK=?",
        (time.time(), pk),
    )


def undelete_replacement(conn: sqlite3.Connection, pk: int, phrase: str) -> None:
    """Restore a previously soft-deleted entry."""
    conn.execute(
        "UPDATE ZTEXTREPLACEMENTENTRY SET ZWASDELETED=0, ZPHRASE=?, ZNEEDSSAVETOCLOUD=1, ZTIMESTAMP=? WHERE Z_PK=?",
        (phrase, time.time(), pk),
    )


# --- Sync logic ---

def sync(api_key: str) -> None:
    """Sync snippets from the API to macOS text replacements."""
    print("Fetching snippets from API...")
    snippets = fetch_snippets(api_key)
    print(f"  Found {len(snippets)} snippets on server.")

    if not TEXT_REPLACEMENTS_DB.exists():
        print(f"\nError: Text replacements database not found at {TEXT_REPLACEMENTS_DB}")
        print("Make sure you have macOS text replacements enabled.")
        sys.exit(1)

    conn = sqlite3.connect(str(TEXT_REPLACEMENTS_DB))
    try:
        existing = read_macos_replacements(conn)
        next_pk = get_next_pk(conn)

        # Build lookup from API snippets (only m-prefixed abbreviations)
        api_snippets = {s["abbreviation"]: s["expansion"] for s in snippets if s["abbreviation"].startswith("m")}

        added = 0
        updated = 0
        deleted = 0
        restored = 0

        # Add or update entries from API
        for abbr, expansion in api_snippets.items():
            if abbr in existing:
                entry = existing[abbr]
                if entry["was_deleted"]:
                    # Previously deleted, restore it
                    undelete_replacement(conn, entry["pk"], expansion)
                    restored += 1
                    print(f"  Restored: {abbr}")
                elif entry["phrase"] != expansion:
                    update_replacement(conn, entry["pk"], expansion)
                    updated += 1
                    print(f"  Updated:  {abbr}")
            else:
                insert_replacement(conn, next_pk, abbr, expansion)
                next_pk += 1
                added += 1
                print(f"  Added:    {abbr}")

        # Soft-delete entries not in API (only z-prefixed, non-deleted ones)
        for abbr, entry in existing.items():
            if abbr not in api_snippets and not entry["was_deleted"]:
                soft_delete_replacement(conn, entry["pk"])
                deleted += 1
                print(f"  Deleted:  {abbr}")

        conn.commit()

        # Summary
        total_changes = added + updated + deleted + restored
        if total_changes == 0:
            print("\nAlready in sync. No changes needed.")
        else:
            print(f"\nSync complete: {added} added, {updated} updated, {deleted} deleted, {restored} restored.")

    finally:
        conn.close()


# --- launchd scheduling ---

def install_schedule() -> None:
    """Install a launchd plist to run sync every 12 hours."""
    python_path = sys.executable
    script_path = str(Path(__file__).resolve())

    plist = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [python_path, script_path],
        "StartInterval": 43200,  # 12 hours in seconds
        "StandardOutPath": str(CONFIG_DIR / "sync.log"),
        "StandardErrorPath": str(CONFIG_DIR / "sync.log"),
        "RunAtLoad": True,
    }

    LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)

    # Unload existing if present
    if LAUNCHD_PLIST.exists():
        subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], capture_output=True)

    with open(LAUNCHD_PLIST, "wb") as f:
        plistlib.dump(plist, f)

    subprocess.run(["launchctl", "load", str(LAUNCHD_PLIST)], check=True)
    print(f"Scheduled sync installed at {LAUNCHD_PLIST}")
    print("Sync will run every 12 hours and on login.")
    print(f"Logs: {CONFIG_DIR / 'sync.log'}")


# --- Main ---

def main():
    config = load_config()
    api_key = config.get("api_key")

    if not api_key:
        api_key = authenticate()
        config["api_key"] = api_key
        save_config(config)
        print("API key saved.\n")

    if "--install-schedule" in sys.argv:
        install_schedule()
        print()

    sync(api_key)


if __name__ == "__main__":
    main()
