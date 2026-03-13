# Options Payoff Tracker - Backend

Backend API built with **FastAPI** for the Options Payoff Tracker application.

## Architecture

```
Route (API endpoint) → Controller (request/response) → Service (business logic) → Repository (database) → Model
```

```
app/
├── api/routes/         # API endpoints (thin layer, routing only)
├── controllers/        # Request/response handling, validation
├── services/           # Business logic
├── repositories/       # Database operations (queries)
├── models/             # SQLAlchemy ORM models
├── schemas/            # Pydantic request/response schemas
├── middleware/          # Auth middleware (JWT)
├── utils/              # Security helpers, custom exceptions
├── config.py           # App settings (from .env)
├── database.py         # DB engine & session
└── main.py             # FastAPI app factory
```

## Setup

### 1. Install dependencies

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your PostgreSQL credentials
```

### 3. Create database

```bash
createdb options_tracker  # or via pgAdmin
```

### 4. Run the server

```bash
uvicorn app.main:app --reload --port 8000
```

### 5. API Docs

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Auth
- `POST /api/v1/auth/register` - Register new user
- `POST /api/v1/auth/login` - Login, get JWT tokens
- `POST /api/v1/auth/refresh` - Refresh access token

### Users
- `GET /api/v1/users/me` - Get profile
- `PATCH /api/v1/users/me` - Update profile
- `DELETE /api/v1/users/me` - Delete account

### Strategies
- `GET /api/v1/strategies/` - List user strategies
- `GET /api/v1/strategies/{id}` - Get strategy
- `GET /api/v1/strategies/{id}/details` - Get strategy with trades
- `POST /api/v1/strategies/` - Create strategy
- `PATCH /api/v1/strategies/{id}` - Update strategy
- `DELETE /api/v1/strategies/{id}` - Delete strategy

### Trades
- `GET /api/v1/trades/strategy/{strategy_id}` - List trades by strategy
- `GET /api/v1/trades/{id}` - Get trade
- `POST /api/v1/trades/strategy/{strategy_id}` - Create trade
- `PATCH /api/v1/trades/{id}` - Update trade
- `POST /api/v1/trades/{id}/close` - Close trade
- `DELETE /api/v1/trades/{id}` - Delete trade

## Trade Data Model

Each trade stores:
- **Basic**: ticker, option_type (CALL/PUT), direction (BUY/SELL), strike, premium, quantity, expiry
- **Greeks**: delta, gamma, theta, vega
- **Market Data**: underlying_price, implied_volatility
- **Metadata**: status (OPEN/CLOSED), open_date, close_date, close_premium, pnl, notes
