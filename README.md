# TextExpander Clone

System-wide text expansion for macOS with a React dashboard.

## Setup

### Prerequisites
- Python 3.11+
- Node.js 18+
- macOS Accessibility permission for your terminal app

### Grant Accessibility Permission
System Settings → Privacy & Security → Accessibility → enable your terminal (Terminal.app, iTerm2, etc.)

### Backend
```bash
cd backend
pip install -r requirements.txt
python main.py
```
API runs at http://localhost:8000

### Frontend (development)
```bash
cd frontend
npm install
npm run dev
```
Dashboard at http://localhost:5173

### Frontend (production build)
```bash
cd frontend
npm run build
# The backend will automatically serve the built files
```

## Usage

1. Open the dashboard and add a snippet (e.g. abbreviation `zhello`, expansion `Hello, world!`)
2. Open any app and type `zhello` — it will auto-expand
3. Abbreviations should start with `z` to avoid false matches

## API

- `GET /api/snippets` — list all
- `POST /api/snippets` — create `{abbreviation, expansion}`
- `PUT /api/snippets/:id` — update
- `DELETE /api/snippets/:id` — delete
- `GET /api/status` — listener status
