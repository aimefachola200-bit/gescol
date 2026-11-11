# Image GESCOL (tout hébergeur acceptant Docker, ou VPS : docker compose up -d)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 GESCOL_DATA=/data GESCOL_EN_LIGNE=1 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/sante' % os.environ.get('PORT','8000'))"
CMD ["sh", "-c", "waitress-serve --listen=0.0.0.0:${PORT} --threads=8 wsgi:application"]
