FROM python:3.13.8-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements-render.txt .
RUN pip install --no-cache-dir -r requirements-render.txt

COPY . .

RUN groupadd --system nexora \
    && useradd --system --gid nexora --home-dir /app nexora \
    && mkdir -p /app/staticfiles /var/data \
    && chown -R nexora:nexora /app /var/data

USER nexora

RUN python manage.py collectstatic --noinput

EXPOSE 8000

CMD ["gunicorn", "nexora_backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "120"]
