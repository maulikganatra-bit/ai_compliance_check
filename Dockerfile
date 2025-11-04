# ----------------------------------------------------------
# Base Image — Lightweight Python runtime
# ----------------------------------------------------------
FROM python:3.10-slim

# ----------------------------------------------------------
#  Set working directory inside the container
# ----------------------------------------------------------
WORKDIR /app

# ----------------------------------------------------------
# Copy dependency files first (for layer caching)
# ----------------------------------------------------------
COPY requirements.txt .

# ----------------------------------------------------------
#  Install dependencies
# ----------------------------------------------------------
RUN pip install --no-cache-dir -r requirements.txt

# ----------------------------------------------------------
#  Copy the rest of your application code
# ----------------------------------------------------------
COPY . .

# ----------------------------------------------------------
#  Set environment variables
# ----------------------------------------------------------
# Avoid Python writing .pyc files
ENV PYTHONDONTWRITEBYTECODE=1
# Force stdout/stderr to be unbuffered (real-time logs)
ENV PYTHONUNBUFFERED=1
# Optional: expose port for FastAPI
EXPOSE 8000

# ----------------------------------------------------------
#  Command to run your FastAPI app
# ----------------------------------------------------------
# Replace "main:app" if your entry file or variable name differ
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
