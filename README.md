# SysTrader

News scalping automated trading system using CYBOS Plus COM API.

## Requirements

- Windows 10/11
- Python 3.x **32-bit** (CYBOS COM is 32-bit only)
- CYBOS Plus installed and logged in
- Node.js 18+ (for frontend build)

## Setup

```bash
# 1. Create virtual environment (32-bit Python)
python -m venv .venv
.venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure
copy appsettings.example.json appsettings.json
# Edit appsettings.json with your Telegram credentials

# 4. Build frontend
cd web
npm install
npm run build
cd ..

# 5. Initialize database
python -c "from src.database import Database; db = Database('data/systrader.db'); db.ensure_schema()"

# 6. Run
python main.py
```

## Usage

- Web UI: http://localhost:8000
- Start engine via Dashboard or `POST /api/engine/start`
- Configure parameters via Settings page

## PoC

Before first run, verify CYBOS news events work:

```bash
python poc/test_news_event.py
```

## Tests

```bash
python -m pytest tests/ -v
```
