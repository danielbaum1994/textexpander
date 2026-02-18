import React, { useState, useEffect, useRef } from "react";

const LINK_RE = /\[([^\]]+)\]\(([^)]+)\)/g;
const BOLD_RE = /\*\*(.+?)\*\*/g;
const ITALIC_RE = /(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g;
const HAS_FORMATTING_RE = /\*\*.+?\*\*|\*(?!\*).+?(?<!\*)\*(?!\*)|\[.+?\]\(.+?\)/;

function getToken() {
  return localStorage.getItem("token");
}

function getUser() {
  try {
    return JSON.parse(localStorage.getItem("user"));
  } catch {
    return null;
  }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function renderExpansion(text, keyPrefix = "") {
  // Process bold, italic, and links into React elements (recursive for nesting)
  const TOKEN_RE = /(\*\*(.+?)\*\*|\[([^\]]+)\]\(([^)]+)\)|(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*))/g;
  const parts = [];
  let lastIndex = 0;
  let match;
  while ((match = TOKEN_RE.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }
    const key = keyPrefix + match.index;
    if (match[2] !== undefined) {
      // Bold: **text** — recurse to handle links/italic inside
      parts.push(<strong key={key}>{renderExpansion(match[2], key + "b")}</strong>);
    } else if (match[3] !== undefined) {
      // Link: [text](url)
      parts.push(
        <a key={key} href={match[4]} target="_blank" rel="noopener noreferrer">
          {match[3]}
        </a>
      );
    } else if (match[5] !== undefined) {
      // Italic: *text* — recurse to handle links inside
      parts.push(<em key={key}>{renderExpansion(match[5], key + "i")}</em>);
    }
    lastIndex = TOKEN_RE.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }
  return parts.length > 0 ? parts : text;
}

function LoginPage() {
  return (
    <div className="login-container">
      <div className="login-card">
        <h1>TextExpander</h1>
        <p>Sign in to manage your text snippets</p>
        <a href="/auth/google" className="google-btn">
          <svg width="18" height="18" viewBox="0 0 18 18">
            <path d="M16.51 8H8.98v3h4.3c-.18 1-.74 1.48-1.6 2.04v2.01h2.6a7.8 7.8 0 0 0 2.38-5.88c0-.57-.05-.66-.15-1.18z" fill="#4285F4"/>
            <path d="M8.98 17c2.16 0 3.97-.72 5.3-1.94l-2.6-2.01c-.71.48-1.63.77-2.7.77-2.08 0-3.84-1.4-4.47-3.29H1.83v2.07A8 8 0 0 0 8.98 17z" fill="#34A853"/>
            <path d="M4.51 10.52a4.8 4.8 0 0 1 0-3.04V5.41H1.83a8 8 0 0 0 0 7.18l2.68-2.07z" fill="#FBBC05"/>
            <path d="M8.98 3.58c1.17 0 2.23.4 3.06 1.2l2.3-2.3A8 8 0 0 0 1.83 5.4L4.5 7.49c.64-1.9 2.4-3.3 4.48-3.9z" fill="#EA4335"/>
          </svg>
          Sign in with Google
        </a>
      </div>
    </div>
  );
}

export default function App() {
  const [token, setToken] = useState(getToken);
  const [user, setUser] = useState(getUser);
  const [snippets, setSnippets] = useState([]);
  const [paused, setPaused] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [showSetup, setShowSetup] = useState(false);
  const [showSync, setShowSync] = useState(false);
  const [abbr, setAbbr] = useState("");
  const [expansion, setExpansion] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [showLinkInput, setShowLinkInput] = useState(false);
  const [linkUrl, setLinkUrl] = useState("");
  const [selection, setSelection] = useState(null);
  const textareaRef = useRef(null);

  const fetchSnippets = () => {
    if (!token) return;
    fetch("/api/snippets", { headers: authHeaders() })
      .then((r) => {
        if (r.status === 401) { handleSignOut(); return []; }
        return r.json();
      })
      .then(setSnippets)
      .catch(console.error);
  };

  const fetchMe = () => {
    if (!token) return;
    fetch("/api/me", { headers: authHeaders() })
      .then((r) => r.json())
      .then((data) => { setPaused(!!data.paused); setApiKey(data.api_key || ""); })
      .catch(console.error);
  };

  const togglePaused = async () => {
    const newPaused = !paused;
    setPaused(newPaused);
    await fetch("/api/me/paused", {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ paused: newPaused }),
    });
  };

  useEffect(() => {
    fetchSnippets();
    fetchMe();
  }, [token]);

  const handleSignOut = () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    setToken(null);
    setUser(null);
    setSnippets([]);
  };

  if (!token) {
    return <LoginPage />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!abbr || !expansion) return;

    if (editingId) {
      await fetch(`/api/snippets/${editingId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ abbreviation: abbr, expansion }),
      });
      setEditingId(null);
    } else {
      await fetch("/api/snippets", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ abbreviation: abbr, expansion }),
      });
    }
    setAbbr("");
    setExpansion("");
    fetchSnippets();
  };

  const handleEdit = (snippet) => {
    setEditingId(snippet.id);
    setAbbr(snippet.abbreviation);
    setExpansion(snippet.expansion);
  };

  const handleDelete = async (id) => {
    await fetch(`/api/snippets/${id}`, { method: "DELETE", headers: authHeaders() });
    fetchSnippets();
  };

  const handleCancel = () => {
    setEditingId(null);
    setAbbr("");
    setExpansion("");
  };

  // Wrap selected text (or insert at cursor) with markdown markers
  const wrapSelection = (before, after) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    const selected = expansion.slice(start, end);
    const wrapped = before + (selected || "text") + after;
    const newExpansion = expansion.slice(0, start) + wrapped + expansion.slice(end);
    setExpansion(newExpansion);
    setTimeout(() => {
      ta.focus();
      if (selected) {
        // Select the wrapped text
        ta.setSelectionRange(start, start + wrapped.length);
      } else {
        // Select the placeholder "text" so user can type over it
        ta.setSelectionRange(start + before.length, start + before.length + 4);
      }
    }, 0);
  };

  const handleBold = () => wrapSelection("**", "**");
  const handleItalic = () => wrapSelection("*", "*");

  const handleTextareaKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "b") {
      e.preventDefault();
      handleBold();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === "i") {
      e.preventDefault();
      handleItalic();
    }
  };

  const handleLinkClick = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    const start = ta.selectionStart;
    const end = ta.selectionEnd;
    if (start === end) {
      setSelection({ start, end, text: "" });
    } else {
      setSelection({ start, end, text: expansion.slice(start, end) });
    }
    setLinkUrl("");
    setShowLinkInput(true);
  };

  const handleLinkSubmit = () => {
    if (!linkUrl) return;
    const sel = selection;
    const linkText = sel.text || linkUrl;
    const markdown = `[${linkText}](${linkUrl})`;
    const before = expansion.slice(0, sel.start);
    const after = expansion.slice(sel.end);
    setExpansion(before + markdown + after);
    setShowLinkInput(false);
    setLinkUrl("");
    setSelection(null);
    setTimeout(() => {
      const ta = textareaRef.current;
      if (ta) {
        const cursor = sel.start + markdown.length;
        ta.focus();
        ta.setSelectionRange(cursor, cursor);
      }
    }, 0);
  };

  const handleLinkCancel = () => {
    setShowLinkInput(false);
    setLinkUrl("");
    setSelection(null);
    textareaRef.current?.focus();
  };

  const hasFormatting = HAS_FORMATTING_RE.test(expansion);

  return (
    <div className="container">
      <header>
        <div><h1>Snippy Dashboard</h1><p className="subheader">A Daniel Baum creation</p></div>
        <div className="header-right">
          <label className="toggle" title={paused ? "Expansion paused" : "Expansion active"}>
            <input type="checkbox" checked={!paused} onChange={togglePaused} />
            <span className="toggle-slider" />
            <span className="toggle-label">{paused ? "Off" : "On"}</span>
          </label>
          <button className="setup-btn" onClick={() => { setShowSync(!showSync); setShowSetup(false); }}>Sync to iPhone</button>
          <button className="setup-btn" onClick={() => { setShowSetup(!showSetup); setShowSync(false); }}>Setup</button>
          <span className="user-name">{user?.name}</span>
          <button className="sign-out" onClick={handleSignOut}>Sign out</button>
        </div>
      </header>

      {showSync && (
        <div className="setup-panel">
          <h2>Sync Snippets to iPhone</h2>
          <p>Use the macOS built-in text replacement system (syncs to iOS/iPad via iCloud). Only snippets with <strong>m-prefixed</strong> abbreviations (e.g. <code>msig</code>, <code>mblurb</code>) are synced to your phone. Note: hyperlinks, bold, and other formatting are not supported — mobile snippets are plain text only.</p>
          <div className="setup-steps">
            <div className="setup-step">
              <span className="step-num">1</span>
              <div className="step-content">
                <p><strong>Run the sync script</strong> — open Terminal and paste this command:</p>
                <code className="setup-code" onClick={(e) => {navigator.clipboard.writeText(e.currentTarget.textContent)}}>
                  {"python3 ~/textexpander/client/sync_macos.py"}
                </code>
                <p>Sign in when prompted (same as the desktop setup). Your snippets will be added to System Settings {">"} Keyboard {">"} Text Replacements.</p>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">2</span>
              <div className="step-content">
                <p><strong>Set up automatic syncing</strong> — paste this once and it will automatically sync your snippets every 12 hours in the background:</p>
                <code className="setup-code" onClick={(e) => {navigator.clipboard.writeText(e.currentTarget.textContent)}}>
                  {"python3 ~/textexpander/client/sync_macos.py --install-schedule"}
                </code>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">3</span>
              <div className="step-content">
                <p><strong>Manual sync</strong> — run the command from Step 1 anytime you want an immediate sync after adding or removing snippets.</p>
              </div>
            </div>
          </div>
          <p className="setup-done">Once synced, your snippets will appear on your iPhone, iPad, and Mac in any app that supports text replacements.</p>
          <p className="setup-note">Tip: click any grey box to copy it to your clipboard.</p>
        </div>
      )}

      {showSetup && (
        <div className="setup-panel">
          <h2>Get Snippy on Your Mac</h2>
          <p>Once set up, your snippets will auto-expand as you type anywhere on your Mac. Takes about 3 minutes.</p>
          <div className="setup-steps">
            <div className="setup-step">
              <span className="step-num">1</span>
              <div className="step-content">
                <p><strong>Open Terminal</strong> — press <kbd>Cmd</kbd> + <kbd>Space</kbd>, type <strong>Terminal</strong>, and hit Enter.</p>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">2</span>
              <div className="step-content">
                <p><strong>Paste this command</strong> — click the box below to copy it, then paste into Terminal with <kbd>Cmd</kbd> + <kbd>V</kbd> and hit Enter.</p>
                <code className="setup-code" onClick={(e) => {navigator.clipboard.writeText(e.currentTarget.textContent)}}>
                  {"pip3 install pynput requests && git clone https://github.com/danielbaum1994/textexpander.git ~/textexpander 2>/dev/null; python3 ~/textexpander/client/expander.py"}
                </code>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">3</span>
              <div className="step-content">
                <p><strong>Sign in</strong> — a browser tab will open. Sign in with Google, and {"you'll"} see an API key. Copy it.</p>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">4</span>
              <div className="step-content">
                <p><strong>Paste the key</strong> — go back to Terminal, paste the API key, and hit Enter. {"You'll"} see {"\""}Snippy is running.{"\""}</p>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">5</span>
              <div className="step-content">
                <p><strong>Allow keyboard access</strong> — this is the important part! macOS needs to trust Python to read your keystrokes.</p>
                <ol className="setup-substeps">
                  <li>Open <strong>System Settings</strong> {">"} <strong>Privacy & Security</strong> {">"} <strong>Accessibility</strong></li>
                  <li>Click the <strong>+</strong> button (unlock with your password if needed)</li>
                  <li>Press <kbd>Cmd</kbd> + <kbd>Shift</kbd> + <kbd>G</kbd> to open the path bar, then paste this path:</li>
                </ol>
                <code className="setup-code" onClick={(e) => {navigator.clipboard.writeText(e.currentTarget.textContent)}}>
                  {"/Library/Developer/CommandLineTools/Library/Frameworks/Python3.framework/Versions/3.9/Resources/Python.app"}
                </code>
                <ol className="setup-substeps" start={4}>
                  <li>Click <strong>Open</strong> to add it</li>
                  <li>Make sure its toggle is <strong>on</strong></li>
                </ol>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">6</span>
              <div className="step-content">
                <p><strong>Restart Snippy</strong> — go back to Terminal and run the command from Step 2 again. Your snippets should now expand!</p>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">7</span>
              <div className="step-content">
                <p><strong>Keep it running</strong> — paste this final command so Snippy stays active even after you close Terminal:</p>
                <code className="setup-code" onClick={() => {navigator.clipboard.writeText("nohup python3 ~/textexpander/client/expander.py > ~/.textexpander/expander.log 2>&1 &")}}>
                  {"nohup python3 ~/textexpander/client/expander.py > ~/.textexpander/expander.log 2>&1 &"}
                </code>
              </div>
            </div>
          </div>
          <p className="setup-done">{"That's"} it! Try typing one of your snippet abbreviations anywhere to test it.</p>
          <h3 className="troubleshooting-heading">Troubleshooting</h3>
          <div className="setup-steps">
            <div className="setup-step">
              <span className="step-num">8</span>
              <div className="step-content">
                <p><strong>Snippets stopped expanding?</strong> — macOS occasionally revokes keyboard access after a system update. Open <strong>System Settings</strong> {">"} <strong>Privacy & Security</strong> {">"} <strong>Accessibility</strong> and check that Python has its toggle <strong>on</strong>. Then run the command from Step 7 again to restart Snippy.</p>
              </div>
            </div>
            <div className="setup-step">
              <span className="step-num">9</span>
              <div className="step-content">
                <p><strong>Still not working?</strong> — The macOS update may have changed the Python binary entirely, so the old entry {"won't"} work. Remove any existing Python entry from Accessibility, then repeat Steps 5 and 6 to re-add it and restart.</p>
              </div>
            </div>
          </div>
          <p className="setup-note">Tip: click any grey box to copy it to your clipboard.</p>
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <input
          type="text"
          placeholder="Abbreviation (e.g. zhello)"
          value={abbr}
          onChange={(e) => setAbbr(e.target.value)}
        />
        <textarea
          ref={textareaRef}
          placeholder="Expansion text"
          value={expansion}
          onChange={(e) => setExpansion(e.target.value)}
          onKeyDown={handleTextareaKeyDown}
          rows={3}
        />
        {showLinkInput && (
          <div className="link-popover">
            <span className="link-popover-label">
              {selection?.text
                ? <>Link "<strong>{selection.text}</strong>" to:</>
                : "Insert link:"}
            </span>
            <input
              type="url"
              placeholder="https://example.com"
              value={linkUrl}
              onChange={(e) => setLinkUrl(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") { e.preventDefault(); handleLinkSubmit(); }
                if (e.key === "Escape") handleLinkCancel();
              }}
              autoFocus
            />
            <div className="link-popover-actions">
              <button type="button" onClick={handleLinkSubmit}>Add Link</button>
              <button type="button" className="cancel" onClick={handleLinkCancel}>Cancel</button>
            </div>
          </div>
        )}
        {hasFormatting && (
          <div className="preview">
            <span className="preview-label">Preview:</span>{" "}
            {renderExpansion(expansion)}
          </div>
        )}
        <div className="form-actions">
          <button type="submit">{editingId ? "Update" : "Add"} Snippet</button>
          <button
            type="button"
            className="format-btn"
            onClick={handleBold}
            title="Bold (⌘B)"
          >
            <strong>B</strong>
          </button>
          <button
            type="button"
            className="format-btn"
            onClick={handleItalic}
            title="Italic (⌘I)"
          >
            <em>I</em>
          </button>
          <button
            type="button"
            className="format-btn"
            onClick={handleLinkClick}
            title="Insert hyperlink (⌘K)"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6.5 8.5a3 3 0 0 0 4.2.4l2-2a3 3 0 0 0-4.2-4.2L7.3 3.9" />
              <path d="M9.5 7.5a3 3 0 0 0-4.2-.4l-2 2a3 3 0 0 0 4.2 4.2l1.2-1.2" />
            </svg>
          </button>
          {editingId && (
            <button type="button" className="cancel" onClick={handleCancel}>
              Cancel
            </button>
          )}
        </div>
      </form>

      <table>
        <thead>
          <tr>
            <th>Abbreviation</th>
            <th>Expansion</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {snippets.length === 0 && (
            <tr>
              <td colSpan={3} className="empty">
                No snippets yet. Add one above.
              </td>
            </tr>
          )}
          {(() => {
            const sort = (arr) => [...arr].sort((a, b) => a.abbreviation.localeCompare(b.abbreviation));
            const desktop = sort(snippets.filter((s) => s.abbreviation.startsWith("z")));
            const mobile = sort(snippets.filter((s) => s.abbreviation.startsWith("m")));
            const other = sort(snippets.filter((s) => !s.abbreviation.startsWith("z") && !s.abbreviation.startsWith("m")));
            const sections = [];
            if (desktop.length > 0) sections.push({ label: "Desktop (z-)", items: desktop });
            if (mobile.length > 0) sections.push({ label: "Mobile (m-)", items: mobile });
            if (other.length > 0) sections.push({ label: "Other", items: other });
            return sections.map((section, si) => (
              <React.Fragment key={section.label}>
                {sections.length > 1 && (
                  <tr className="section-header">
                    <td colSpan={3}>{section.label}</td>
                  </tr>
                )}
                {section.items.map((s) => (
                  <tr key={s.id}>
                    <td className="abbr">{s.abbreviation}</td>
                    <td className="expansion">{renderExpansion(s.expansion)}</td>
                    <td className="actions">
                      <button onClick={() => handleEdit(s)}>Edit</button>
                      <button className="delete" onClick={() => handleDelete(s.id)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </React.Fragment>
            ));
          })()}
        </tbody>
      </table>
    </div>
  );
}
