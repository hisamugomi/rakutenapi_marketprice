# 軽量なNode.jsイメージを使用
FROM node:22-slim

# Claude Codeの実行に必要なパッケージと基本ツールをインストール
RUN apt-get update && apt-get install -y \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Claude Codeをグローバルにインストール
RUN npm install -g @anthropic-ai/claude-code

# 作業ディレクトリを作成（ここがClaudeに見える「壁」の内側になります）
WORKDIR /project

# 非ルートユーザーを作成（セキュリティ強化：コンテナ内でもrootを避ける）
RUN useradd -m developer && chown -R developer /project
USER developer

# デフォルトのコマンド
ENTRYPOINT ["claude"]