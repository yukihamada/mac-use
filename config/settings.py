import os

# Flask設定
FLASK_HOST = '0.0.0.0'
FLASK_PORT = 5001
FLASK_DEBUG = True

# Open Interpreter設定
INTERPRETER_SETTINGS = {
    'auto_run': True,
    'max_output': 2000,
    'model': 'claude-3-5-sonnet-20240620',
    'context_window': 200000,
    'max_tokens': 4000
}

# API設定
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("警告: ANTHROPIC_API_KEY環境変数が設定されていません。")
    print("export ANTHROPIC_API_KEY='your-api-key' を実行してAPIキーを設定してください。") 