FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBUG=False

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Collect static files
RUN python manage.py collectstatic --noinput

# Create media directory
RUN mkdir -p /app/media/uploads

EXPOSE 8000

CMD ["gunicorn", "core.wsgi:application", "--workers", "4", "--bind", "0.0.0.0:8000", "--timeout", "120"]
