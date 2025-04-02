import os
import logging
import interpreter
from config.settings import ANTHROPIC_API_KEY

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_interpreter():
    """
    Open Interpreterの初期化と設定を行う関数
    """
    try:
        # APIキーの設定
        if not ANTHROPIC_API_KEY:
            logger.error("ANTHROPIC_API_KEYが設定されていません")
            return None

        # Open Interpreterの設定
        interpreter.api_key = ANTHROPIC_API_KEY
        interpreter.model = "claude-3-sonnet-20240229"  # Claude 3 Sonnetを使用
        interpreter.auto_run = True  # 自動実行を有効化
        interpreter.verbose = True   # 詳細な出力を有効化

        logger.info("Open Interpreterの設定が完了しました")
        return interpreter

    except Exception as e:
        logger.error(f"Open Interpreterの設定中にエラーが発生しました: {str(e)}")
        return None

def extract_output(messages):
    """
    メッセージから出力を抽出する関数
    """
    try:
        output = []
        for message in messages:
            if isinstance(message, dict) and 'content' in message:
                output.append(message['content'])
        return '\n'.join(output)
    except Exception as e:
        logger.error(f"出力の抽出中にエラーが発生しました: {str(e)}")
        return str(e) 