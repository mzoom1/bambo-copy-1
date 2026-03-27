# TopoPuzzle 3D

3D terrain puzzle generator for 3D printing.

Select an area on the map, configure the puzzle, and export a multi-part `.3mf` file ready for Bambu Studio.

![TopoPuzzle 3D UI](TopoPuzzle%203D/premium-ui-preview-fixed.png)

## Requirements

- Python 3.12+
- Node.js 20+
- `pip`
- `npm`

## Quick Start

### Backend

```bash
python3 -m pip install -r requirements.txt
uvicorn server:app --reload --port 8000
```

The backend API will be available at `http://127.0.0.1:8000`.

### Frontend

```bash
cd "TopoPuzzle 3D"
npm install
npm run dev
```

The frontend dev server runs on `http://127.0.0.1:4173`.

## How It Works

1. Open the web app in your browser.
2. Draw a rectangle on the map.
3. Choose grid size, quality, and export options.
4. Click Generate.
5. Download the resulting `.3mf` file and open it in Bambu Studio.

## API

The FastAPI backend exposes:

- `GET /health` - health check
- `POST /generate` - start a generation job, returns `202`
- `GET /jobs/{job_id}` - job status and progress
- `GET /jobs/{job_id}/download` - download the finished `.3mf`

## Tech Stack

- Backend: Python, FastAPI, `trimesh`, `shapely`
- Frontend: React 19, TypeScript, Vite, Leaflet

## Output

The generator produces a single multipart `.3mf` file. If a `template.3mf` is present, it is used as a metadata template; otherwise the export still works without it.

## Project Layout

- `server.py` - FastAPI backend
- `topomap_to_puzzle_3mf.py` - terrain-to-3MF generation pipeline
- `requirements.txt` - Python dependencies
- `TopoPuzzle 3D/` - React frontend

