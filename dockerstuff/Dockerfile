FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir google-generativeai

WORKDIR /app

# ローカルで作ったファイルをコンテナにコピー
COPY gemini_app.py /usr/local/bin/gemini-cli.py

# 実行
ENTRYPOINT ["python", "/usr/local/bin/gemini-cli.py"]