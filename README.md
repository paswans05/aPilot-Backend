# aPilot Backend

A modern, high-performance backend API for the aPilot application, built with FastAPI, Python, and MySQL.

## 🚀 Tech Stack

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/)
- **Language**: Python 3.10+
- **Database**: MySQL
- **ORM**: [SQLAlchemy](https://www.sqlalchemy.org/)
- **Authentication**: JWT (JSON Web Tokens)
- **Validation**: [Pydantic](https://docs.pydantic.dev/)

## 🛠️ Getting Started

### Prerequisites

- Python 3.10 or higher
- MySQL Server
- `pip` (Python package manager)

### Installation

1. **Clone the repository** (if you haven't already):
   ```bash
   git clone <repository-url>
   cd aPilot-backend
   ```

2. **Create a virtual environment**:
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   source venv/Scripts/activate  # For Linux/macOS
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

### Configuration

Create a `.env` file in the root directory and add the following variables:

```env
PROJECT_NAME=aPilot
DATABASE_URL=mysql+pymysql://<user>:<password>@<host>:<port>/<database>
SECRET_KEY=your_super_secret_key_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=43200
```

### Running the Server

Start the development server with auto-reload:

```powershell
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`.

## 📖 API Documentation

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## 📁 Project Structure

```text
app/
├── api/             # API routes and endpoints
│   └── endpoints/   # Specific resource handlers (auth, users, etc.)
├── core/            # Core configuration (security, jwt, config)
├── db/              # Database session and base model
├── models/          # SQLAlchemy database models
├── schemas/         # Pydantic data validation schemas
├── services/        # Business logic services
└── main.py          # Application entry point
```

## 🔐 Authentication

This API uses JWT for authentication. To access protected routes, include the token in the Authorization header:

`Authorization: Bearer <your_access_token>`

## 📝 License

This project is licensed under the [ISC License](LICENSE).
