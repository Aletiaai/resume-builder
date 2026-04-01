FROM python:3.11-slim

# Create non-root user
RUN useradd -m -u 1000 app

WORKDIR /home/app/resume-builder

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and skill files
COPY app/ app/
COPY frontend/ frontend/
COPY .claude/ .claude/

# Create logs directory and set ownership
RUN mkdir -p logs && chown -R app:app /home/app/resume-builder

USER app

# Single worker — skill_service uses in-memory URI cache
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1
