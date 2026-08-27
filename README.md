# ShelfGuard-AI

ShelfGuard-AI is an intelligent, automated perishable inventory and expiry management system. It prevents food waste, optimizes dynamic markdowns using Machine Learning, automates stock entry with OCR and LLM label processing, and routes near-expiry items to NGO donation channels with automated tax deduction tracking.

---

## Key Features

- **Dynamic Lifecycle & Expiry Tracking**: Automatically categorizes inventory into dynamic lifecycle stages (`SAFE`, `WARNING`, `CRITICAL`, `DONATION`, `EXPIRED`, `NGO_DISPATCH`) using business timezone-aware date logic (IST / Asia/Kolkata).
- **ML Dynamic Pricing Engine**: Uses an XGBoost regression model to calculate optimal discount percentages (0–70%) based on remaining shelf life hours, base price, initial quantity, and daily sales demand velocity. Includes fallback heuristic pricing.
- **Smart Label OCR & Semantic Extraction**: Processes images of product packaging or receipts using EasyOCR and OpenCV, paired with Google Gemini Flash (`gemini-3.6-flash`) for structured semantic JSON extraction (product name, category, batch, dates, price).
- **Automated NGO Donation Dispatch**: Automatically identifies inventory entering donation eligibility, checks daily demand thresholds, and routes batches via round-robin allocation to partner NGOs (e.g., Feeding India, Robin Hood Army, Akshaya Patra).
- **Tax Audit Ledger**: Tracks Section 80G tax deductions and overall financial loss mitigation metrics for donated inventory.

---

## Tech Stack

- **Backend**: Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2, SQLite
- **Machine Learning & Analytics**: XGBoost, Scikit-Learn, Pandas, NumPy, Joblib
- **Computer Vision & AI**: EasyOCR, OpenCV (`opencv-python-headless`), Google Gemini Flash API (`google-genai`)
- **Testing & Quality Assurance**: Pytest, HTTPX, Ruff
- **Frontend Dashboard**: React, Vite (located in `frontend/`)

---

## Setup & Installation

### 1. Prerequisites

- Python 3.11 or higher installed on your system.
- Git.

### 2. Create Virtual Environment

Clone the repository and create a Python virtual environment:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

Install all required packages from `requirements.txt`:

```bash
pip install -r requirements.txt
```

---

## Configuration (`.env` Setup)

Create a `.env` file at the root of the project by copying `.env.example`:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**
```bash
cp .env.example .env
```

### Required & Optional Environment Variables

Edit `.env` and set the following parameters:

```env
# Database Path (SQLite URL)
DB_PATH=sqlite:///shelfguard.db

# Path to trained XGBoost pricing model artifact
MODEL_PATH=models/xgboost_pricing_model.joblib

# Google Gemini API Key (Required for LLM-based OCR semantic extraction)
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.6-flash

# Allowed CORS Origins (JSON formatted array string)
ALLOWED_ORIGINS=["http://localhost:8000","http://127.0.0.1:8000","http://localhost:5173"]

# Partner NGOs for donation routing (JSON formatted array string)
NGO_PARTNERS=["Feeding India","Robin Hood Army","Akshaya Patra"]

# System Log Level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

> **Note:** If `GEMINI_API_KEY` is omitted or empty, the OCR extraction engine will automatically fall back to rule-based regex parsing for dates and product names.

---

## Database Initialization & Seeding

To initialize the SQLite database schema and populate it with mock inventory data:

```bash
python scripts/init_db.py
```

What `init_db.py` does:
1. Automatically generates `data/mock_inventory.csv` if it does not already exist (via `scripts/generate_mock_inventory.py`).
2. Clears previous live inventory records from `shelfguard.db`.
3. Creates required database tables (`products`, `inventory_batches`, `ngo_donations`).
4. Ingests mock inventory rows into SQLite and prints a verification lifecycle status summary.

---

## Train the Pricing Model

To train the XGBoost dynamic markdown pricing model on historical sales data:

```bash
python src/shelfguard/train_model.py
```

What `train_model.py` does:
1. Loads historical data from `data/perishable_goods_management.csv`.
2. Validates and preprocesses features (`remaining_hours`, `base_price`, `initial_quantity`, `daily_demand`).
3. Performs group-based splitting (`GroupShuffleSplit` on `product_id`) to prevent data leakage.
4. Trains an `XGBRegressor` and evaluates performance metrics (MAE and RMSE) against a baseline model.
5. Saves the trained model to `models/xgboost_pricing_model.joblib` and feature list to `models/feature_names.json`.

---

## Start the FastAPI Server

Run the FastAPI development server with `uvicorn`:

**Using `python -m` (recommended):**
```bash
python -m uvicorn shelfguard.main:app --reload --app-dir src
```

**Alternatively (setting PYTHONPATH):**
```bash
# Windows PowerShell
$env:PYTHONPATH="src"; uvicorn shelfguard.main:app --reload

# Linux / macOS
PYTHONPATH=src uvicorn shelfguard.main:app --reload
```

Once running, access:
- **API Base URL**: `http://127.0.0.1:8000`
- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc API Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## Running Tests

Execute the complete automated test suite using `pytest`:

```bash
pytest
```

or via `python -m`:

```bash
python -m pytest
```

### Test Coverage Includes:
- **`tests/test_api.py`**: API endpoint integration tests for inventory, OCR ingestion, pricing predictions, and donation dispatch.
- **`tests/test_ocr.py`**: OCR image pre-processing, text extraction, and semantic fallback logic.
- **`tests/test_train_model.py`**: Preprocessing validation, group splitting, and model training metrics.
- **`tests/test_ngo_router.py`**: NGO donation eligibility checks and allocation logic.
- **`tests/test_tax_ledger.py`**: Tax deduction calculations and 80G compliance report generation.

---

## Core API Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Server health check and database status |
| `GET` | `/inventory/` | Paginated listing of inventory batches with dynamic lifecycle status |
| `POST` | `/inventory/add` | Manually add a new inventory batch |
| `POST` | `/ocr/process` | Upload label/receipt image to extract raw text & semantic JSON |
| `POST` | `/ocr/ingest` | Process label image and immediately ingest batch into database |
| `POST` | `/pricing/predict` | Get ML-recommended discount percentage and dynamic price for a batch |
| `POST` | `/donations/scan-dispatch` | Run NGO donation dispatch worker for near-expiry items |
| `GET` | `/donations/history` | Retrieve NGO donation history log |
| `GET` | `/tax-ledger/summary` | Retrieve Section 80G tax audit savings and loss mitigation report |
