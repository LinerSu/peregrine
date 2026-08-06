FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# LaTeX toolchain for tailored-CV PDF compilation. The app degrades gracefully to
# tex-only when LaTeX is absent (so CI, which doesn't build this image, stays fast),
# but the running image ships an engine so PDFs actually render.
RUN apt-get update && apt-get install -y --no-install-recommends \
      texlive-latex-base texlive-latex-recommended texlive-latex-extra texlive-fonts-recommended \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Inert outside pytest, but the documented container test run
# (`docker compose run --rm -v "$PWD/api/tests:/app/tests" api ... pytest tests`) has
# ROOT=/app with data/, config/, applications/ and logs/ bind-mounted from the host —
# so without this the suite writes STATUS.md and applications/<id>/ artifacts straight
# into the user's real install. The conftest points it at a throwaway root instead.
COPY conftest.py .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
