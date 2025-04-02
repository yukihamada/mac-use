#!/bin/bash

# エラーが発生した場合にスクリプトを停止
set -e

# APIキーの設定確認
if [ -z "$OPENAI_API_KEY" ]; then
    echo "警告: OPENAI_API_KEY環境変数が設定されていません。"
    echo "ターミナルで以下を実行してAPIキーを設定してください:"
    echo "export OPENAI_API_KEY='あなたのAPIキー'" # シングルクォート推奨
    # APIキーがない場合でも続行（実行時に要求される）
fi

# Python 3のインストール確認
if ! command -v python3 &> /dev/null; then
    echo "Python 3が見つかりません。インストールを試みます..."
    # macOS (Homebrew)
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if ! command -v brew &> /dev/null; then
            echo "Homebrewがインストールされていません。インストールします..."
            /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        fi
        brew install python3
    # Debian/Ubuntu
    elif command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-pip python3-venv
    # Fedora
    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3 python3-pip
    else
        echo "エラー: 使用しているOSでのPython 3の自動インストール方法がわかりません。"
        echo "手動でPython 3とpipをインストールしてください。"
        exit 1
    fi
fi

# pipの確認
if ! python3 -m pip --version &> /dev/null; then
    echo "pipが見つかりません。インストールを試みます..."
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    python3 get-pip.py
    rm get-pip.py
    # 再度確認
    if ! python3 -m pip --version &> /dev/null; then
        echo "エラー: pipのインストールに失敗しました。手動でインストールしてください。"
        exit 1
    fi
fi

echo "Python 3とpipの準備ができました。"

# --- 必要なパッケージのインストール ---
echo "必要なPythonパッケージをインストール/アップグレードしています..."
python3 -m pip install --upgrade pip
python3 -m pip install flask open-interpreter

# --- app.pyの存在確認 ---
if [ ! -f "app.py" ]; then
    echo "エラー: app.pyファイルが見つかりません。"
    echo "app.pyをこのスクリプトと同じディレクトリに作成してください。"
    exit 1
fi

# --- Flaskサーバーの起動 ---
# macOS Monterey以降ではポート5000がAirPlayで使用されるため、別のポートを使用
PORT=5001
echo "Flaskサーバーを起動しています (http://localhost:$PORT)..."
echo "サーバーを停止するには Ctrl+C を押してください。"

# 環境変数を設定してPythonスクリプトを直接実行
python3 app.py