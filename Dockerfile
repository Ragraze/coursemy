FROM python:3.12-slim AS css
WORKDIR /build
COPY scripts/build_css.py scripts/build_css.py
COPY app/templates app/templates
COPY app/static/css app/static/css
COPY app/static/js app/static/js
RUN python scripts/build_css.py

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home course
COPY --chown=course:course . .
COPY --from=css --chown=course:course /build/app/static/css/style.css app/static/css/style.css
USER course
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn app.main:app -k uvicorn_worker.UvicornWorker --workers 1 --bind 0.0.0.0:${PORT:-8000} --timeout 180 --access-logfile -"]
