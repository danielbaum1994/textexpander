import { useState, useEffect, useRef } from "react";

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
      .then((data) => setPaused(!!data.paused))
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
        <h1>TextExpander Dashboard</h1>
        <div className="header-right">
          <label className="toggle" title={paused ? "Expansion paused" : "Expansion active"}>
            <input type="checkbox" checked={!paused} onChange={togglePaused} />
            <span className="toggle-slider" />
            <span className="toggle-label">{paused ? "Off" : "On"}</span>
          </label>
          <span className="user-name">{user?.name}</span>
          <button className="sign-out" onClick={handleSignOut}>Sign out</button>
        </div>
      </header>

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
          {snippets.map((s) => (
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
        </tbody>
      </table>
    </div>
  );
}
