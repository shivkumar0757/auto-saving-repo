# docker build -t blk-hacking-ind-name-lastname .

# python:3.12-slim chosen: Debian-based minimal image (~150MB vs ~1GB full),
# includes only what's needed to run Python; no build tools, docs, or test
# packages. Ideal for production REST APIs where image size and attack surface
# both matter. FastAPI + uvicorn + numpy all install cleanly on this base.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5477

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5477"]
