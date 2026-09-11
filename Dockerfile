FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN groupadd --system quickgo && useradd --system --gid quickgo --home-dir /app quickgo \
    && mkdir -p /app/instance /app/static/uploads/receipts /app/static/uploads/logos /app/static/icons /app/.gunicorn \
    && chown -R quickgo:quickgo /app/instance /app/static /app/.gunicorn
USER quickgo

EXPOSE 8000

CMD ["gunicorn", "--worker-class", "gevent", "--worker-connections", "1000", "-w", "1", "--bind", "0.0.0.0:8000", "wsgi:app"]

# REBUILD 2026-08-26 - Force cloudinary install
