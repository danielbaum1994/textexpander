"""FastAPI server for TextExpander with Google OAuth."""

from __future__ import annotations

import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from auth import create_access_token, get_current_user, oauth
from database import Snippet, User, create_tables, get_db

import os

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Pydantic models ---

class SnippetCreate(BaseModel):
    abbreviation: str
    expansion: str


class SnippetUpdate(BaseModel):
    abbreviation: Optional[str] = None
    expansion: Optional[str] = None


# --- Auth routes ---

@app.get("/auth/google")
async def auth_google(request: Request, device: bool = False):
    redirect_uri = f"{BASE_URL}/auth/callback"
    if device:
        request.session["device_flow"] = True
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    token = await oauth.google.authorize_access_token(request)
    userinfo = token.get("userinfo")
    if not userinfo:
        raise HTTPException(status_code=400, detail="Failed to get user info from Google")

    google_id = userinfo["sub"]
    email = userinfo["email"]
    name = userinfo.get("name", email)

    # Find or create user
    user = db.query(User).filter(User.google_id == google_id).first()
    if not user:
        user = User(
            id=str(uuid.uuid4()),
            google_id=google_id,
            email=email,
            name=name,
            api_key=secrets.token_urlsafe(32),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.name = name
        user.email = email
        if not user.api_key:
            user.api_key = secrets.token_urlsafe(32)
        db.commit()

    jwt_token = create_access_token(user.id)

    # Device flow: show the API key on a page
    if request.session.pop("device_flow", False):
        device_html = (
            '<!DOCTYPE html>'
            '<html><head><title>TextExpander - Device Auth</title>'
            '<style>'
            'body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f5f5f7; display: flex; justify-content: center; align-items: center; min-height: 100vh; }'
            '.card { background: #fff; padding: 40px; border-radius: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; max-width: 480px; }'
            'h2 { margin-bottom: 8px; }'
            'p { color: #86868b; margin-bottom: 20px; }'
            '.key { font-family: "SF Mono", monospace; background: #f5f5f7; padding: 12px 16px; border-radius: 8px; font-size: 14px; word-break: break-all; user-select: all; cursor: text; border: 1px solid #d2d2d7; }'
            '.note { font-size: 13px; color: #86868b; margin-top: 16px; }'
            '</style></head>'
            '<body><div class="card">'
            '<h2>Signed in as ' + name + '</h2>'
            '<p>Copy this API key and paste it into your terminal:</p>'
            '<div class="key">' + user.api_key + '</div>'
            '<p class="note">You can close this tab after copying the key.</p>'
            '</div></body></html>'
        )
        return HTMLResponse(device_html)

    # Web flow: redirect to frontend with token
    safe_name = name.replace("'", "\\'")
    safe_email = email.replace("'", "\\'")
    web_html = (
        "<!DOCTYPE html><html><head><script>"
        "localStorage.setItem('token', '" + jwt_token + "');"
        "localStorage.setItem('user', JSON.stringify({name: '" + safe_name + "', email: '" + safe_email + "'}));"
        "window.location.href = '/';"
        "</script></head><body>Signing in...</body></html>"
    )
    return HTMLResponse(web_html)


@app.get("/auth/device")
async def auth_device(request: Request):
    """Start device auth flow — redirects to Google with device flag."""
    redirect_uri = f"{BASE_URL}/auth/callback"
    request.session["device_flow"] = True
    return await oauth.google.authorize_redirect(request, redirect_uri)


# --- API routes ---

@app.get("/api/me")
def get_me(user: User = Depends(get_current_user)):
    return {"id": user.id, "email": user.email, "name": user.name}


@app.get("/api/snippets")
def list_snippets(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snippets = db.query(Snippet).filter(Snippet.user_id == user.id).all()
    return [
        {"id": s.id, "abbreviation": s.abbreviation, "expansion": s.expansion}
        for s in snippets
    ]


@app.post("/api/snippets", status_code=201)
def create_snippet(body: SnippetCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snippet = Snippet(
        id=str(uuid.uuid4()),
        user_id=user.id,
        abbreviation=body.abbreviation,
        expansion=body.expansion,
    )
    db.add(snippet)
    db.commit()
    return {"id": snippet.id, "abbreviation": snippet.abbreviation, "expansion": snippet.expansion}


@app.put("/api/snippets/{snippet_id}")
def update_snippet(snippet_id: str, body: SnippetUpdate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snippet = db.query(Snippet).filter(Snippet.id == snippet_id, Snippet.user_id == user.id).first()
    if not snippet:
        raise HTTPException(status_code=404, detail="Snippet not found")
    if body.abbreviation is not None:
        snippet.abbreviation = body.abbreviation
    if body.expansion is not None:
        snippet.expansion = body.expansion
    db.commit()
    return {"id": snippet.id, "abbreviation": snippet.abbreviation, "expansion": snippet.expansion}


@app.delete("/api/snippets/{snippet_id}")
def delete_snippet(snippet_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    snippet = db.query(Snippet).filter(Snippet.id == snippet_id, Snippet.user_id == user.id).first()
    if not snippet:
        raise HTTPException(status_code=404, detail="Snippet not found")
    db.delete(snippet)
    db.commit()
    return {"ok": True}


# Serve React build if it exists
frontend_build = Path(__file__).parent.parent / "frontend" / "dist"
if frontend_build.exists():
    app.mount("/", StaticFiles(directory=str(frontend_build), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
