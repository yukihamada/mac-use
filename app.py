import os
import re # 正規表現モジュールをインポート
from flask import Flask, request, jsonify, render_template_string, Response
from interpreter import interpreter
import logging
import sys
import json
import time

# Flaskアプリケーションの初期化
app = Flask(__name__)

# ロギングの設定 (デバッグに役立ちます)
logging.basicConfig(level=logging.INFO)

# Open Interpreterの設定
# ローカル環境での実行設定
interpreter.auto_run = True      # 確認プロンプトなしでコードを実行
interpreter.max_output = 2000    # 出力の最大文字数を制限

# APIキーの設定 - 環境変数から取得
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("警告: OPENAI_API_KEY環境変数が設定されていません。")
    print("export OPENAI_API_KEY='your-api-key' を実行してAPIキーを設定してください。")
    # APIキーがない場合はエラーにせず、実行時に要求されるようにする

# モデルの設定 - 環境変数から取得するか、デフォルト値を使用
interpreter.llm.model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")

def extract_output(messages):
    """
    Open Interpreterのメッセージリストから主要な出力を抽出するヘルパー関数。
    コードブロックや不要なテキストを除去しようと試みる。
    """
    if not messages or not isinstance(messages, list):
        return "応答がありませんでした。"

    # 最後のメッセージ、または 'type': 'console', 'format': 'output' のメッセージを探す
    output_content = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and 'content' in msg:
            output_content = msg['content']
            break # 最後に見つかった content を使う

    if not output_content:
        return "応答から内容を抽出できませんでした。"

    # 簡単なクリーンアップ: コードブロックの除去など
    # ```python\n...\n``` や ```\n...\n``` を除去
    output_content = re.sub(r'^```[a-zA-Z]*\n', '', output_content)
    output_content = re.sub(r'\n```$', '', output_content)
    # 先頭・末尾の空白を除去
    output_content = output_content.strip()

    return output_content if output_content else "空の出力です。"

@app.route('/execute', methods=['POST'])
def execute_command():
    """
    POSTリクエストを受け取り、自然言語の指示をOpen Interpreterで処理するエンドポイント。
    Open Interpreterが適切なコード（シェルコマンドなど）を生成して実行します。
    会話の履歴を保持します。
    """
    # リクエストから指示を取得
    data = request.get_json()
    instruction = data.get('instruction', "現在の日時を表示して")
    reset_conversation = data.get('reset', False)  # 会話をリセットするかどうかのフラグ
    app.logger.info(f"Received instruction: {instruction}")

    try:
        # リセットフラグが立っている場合のみリセット
        if reset_conversation:
            interpreter.reset()
            app.logger.info("Conversation history reset")
            return jsonify({"status": "success", "output": "会話履歴をリセットしました。"})

        # Open Interpreterのchatメソッドを使用して指示を処理
        # 自然言語の指示をそのまま渡す
        messages = interpreter.chat(instruction, display=False, stream=False)

        app.logger.info(f"Raw messages from interpreter: {messages}")

        # 結果の解析
        output = extract_output(messages)

        app.logger.info(f"Extracted output: {output}")
        return jsonify({"status": "success", "output": output})

    except Exception as e:
        app.logger.error(f"Error during Open Interpreter execution: {e}", exc_info=True)
        return jsonify({"status": "error", "output": f"サーバー内部エラーが発生しました: {str(e)}"}), 500

@app.route('/stream', methods=['POST'])
def stream_execute():
    """
    リアルタイムストリーミングでOpen Interpreterの出力を返すエンドポイント
    """
    data = request.get_json()
    instruction = data.get('instruction', "現在の日時を表示して")
    app.logger.info(f"Received streaming instruction: {instruction}")

    def generate():
        try:
            # 最初のメッセージを送信
            yield f"data: {json.dumps({'status': 'start', 'message': '処理を開始しています...'})}\n\n"
            
            # ストリーミングモードでInterpreterを実行
            for chunk in interpreter.chat(instruction, display=False, stream=True):
                if isinstance(chunk, dict) and 'content' in chunk:
                    content = chunk['content']
                    # 進行状況を送信
                    yield f"data: {json.dumps({'status': 'progress', 'message': content})}\n\n"
                    # 少し待機してクライアントが処理できるようにする
                    time.sleep(0.05)
            
            # 完了メッセージを送信
            yield f"data: {json.dumps({'status': 'complete', 'message': '処理が完了しました'})}\n\n"
            
        except Exception as e:
            app.logger.error(f"Streaming error: {e}", exc_info=True)
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)})}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/')
def index():
    """
    チャット形式のHTMLフロントエンドを提供するエンドポイント。
    """
    # HTMLテンプレートを文字列として定義
    html_template = '''<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Open Interpreter チャット</title>
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            flex: 1;
            display: flex;
            flex-direction: column;
        }
        header {
            background-color: #007bff;
            color: white;
            padding: 15px 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        h1 {
            font-size: 1.5rem;
            font-weight: 500;
        }
        .chat-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            background-color: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
            margin-bottom: 20px;
        }
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
        }
        .message {
            margin-bottom: 15px;
            display: flex;
        }
        .message-content {
            padding: 10px 15px;
            border-radius: 18px;
            max-width: 80%;
        }
        .user-message {
            justify-content: flex-end;
        }
        .user-message .message-content {
            background-color: #007bff;
            color: white;
            border-bottom-right-radius: 4px;
        }
        .ai-message .message-content {
            background-color: #f0f0f0;
            border-bottom-left-radius: 4px;
        }
        .message-time {
            font-size: 0.75rem;
            color: #999;
            margin-top: 5px;
            text-align: right;
        }
        .chat-input {
            display: flex;
            padding: 15px;
            background-color: #f9f9f9;
            border-top: 1px solid #eee;
        }
        .chat-input textarea {
            flex: 1;
            padding: 12px 15px;
            border: 1px solid #ddd;
            border-radius: 24px;
            font-size: 1rem;
            resize: none;
            outline: none;
            max-height: 120px;
            min-height: 48px;
        }
        .chat-input textarea:focus {
            border-color: #007bff;
        }
        .chat-input button {
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 50%;
            width: 48px;
            height: 48px;
            margin-left: 10px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background-color 0.2s;
        }
        .chat-input button:hover {
            background-color: #0056b3;
        }
        .chat-input button:disabled {
            background-color: #ccc;
            cursor: not-allowed;
        }
        .chat-input button svg {
            width: 24px;
            height: 24px;
        }
        .examples {
            background-color: white;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .examples h3 {
            margin-bottom: 10px;
            font-size: 1rem;
            color: #555;
        }
        .example-buttons {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }
        .example-button {
            background-color: #f0f7ff;
            border: 1px solid #cce5ff;
            color: #0066cc;
            padding: 8px 12px;
            border-radius: 16px;
            font-size: 0.9rem;
            cursor: pointer;
            transition: all 0.2s;
        }
        .example-button:hover {
            background-color: #e0f0ff;
            border-color: #99caff;
        }
        .toolbar {
            display: flex;
            justify-content: flex-end;
            margin-bottom: 10px;
        }
        .reset-button {
            background-color: transparent;
            color: #dc3545;
            border: 1px solid #dc3545;
            padding: 6px 12px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 0.9rem;
            transition: all 0.2s;
        }
        .reset-button:hover {
            background-color: #dc3545;
            color: white;
        }
        .loading-indicator {
            display: inline-block;
            width: 20px;
            height: 20px;
            border: 2px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top-color: white;
            animation: spin 1s ease-in-out infinite;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .code-block {
            background-color: #f6f8fa;
            border-radius: 6px;
            padding: 12px;
            font-family: monospace;
            white-space: pre-wrap;
            margin: 10px 0;
            overflow-x: auto;
        }
        .system-message {
            text-align: center;
            margin: 10px 0;
            color: #6c757d;
            font-style: italic;
            font-size: 0.9rem;
        }
        .typing-indicator {
            display: flex;
            align-items: center;
            margin-bottom: 15px;
        }
        .typing-indicator span {
            height: 8px;
            width: 8px;
            background-color: #bbb;
            border-radius: 50%;
            display: inline-block;
            margin-right: 5px;
            animation: bounce 1.5s infinite ease-in-out;
        }
        .typing-indicator span:nth-child(2) {
            animation-delay: 0.2s;
        }
        .typing-indicator span:nth-child(3) {
            animation-delay: 0.4s;
        }
        @keyframes bounce {
            0%, 60%, 100% { transform: translateY(0); }
            30% { transform: translateY(-5px); }
        }
    </style>
</head>
<body>
    <header>
        <h1>Open Interpreter チャット</h1>
    </header>
    <div class="container">
        <div class="examples">
            <h3>例えば、こんな指示を試してみてください:</h3>
            <div class="example-buttons">
                <button class="example-button" onclick="setExample(this.textContent)">現在のディレクトリのファイル一覧を表示して</button>
                <button class="example-button" onclick="setExample(this.textContent)">システムの使用状況を確認して</button>
                <button class="example-button" onclick="setExample(this.textContent)">現在の日時を表示して</button>
                <button class="example-button" onclick="setExample(this.textContent)">メモリとCPU使用率を確認して</button>
                <button class="example-button" onclick="setExample(this.textContent)">簡単なPythonスクリプトを作成して実行して</button>
            </div>
        </div>
        
        <div class="toolbar">
            <button id="resetBtn" class="reset-button">会話をリセット</button>
        </div>
        
        <div class="chat-container">
            <div id="chatMessages" class="chat-messages">
                <div class="message ai-message">
                    <div class="message-content">
                        こんにちは！Open Interpreterへようこそ。自然言語でコンピュータを操作できます。何をお手伝いしましょうか？
                    </div>
                </div>
            </div>
            
            <div class="chat-input">
                <textarea id="userInput" placeholder="メッセージを入力..." rows="1" onkeydown="if(event.keyCode === 13 && !event.shiftKey) { event.preventDefault(); sendMessage(); }"></textarea>
                <button id="sendButton" onclick="sendMessage()">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <line x1="22" y1="2" x2="11" y2="13"></line>
                        <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
                    </svg>
                </button>
            </div>
        </div>
    </div>

    <script>
        // テキストエリアの高さを自動調整する関数
        const userInput = document.getElementById('userInput');
        userInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
            // 最大高さを制限
            if (this.scrollHeight > 120) {
                this.style.height = '120px';
            }
        });
        
        function setExample(text) {
            userInput.value = text;
            userInput.style.height = 'auto';
            userInput.style.height = (userInput.scrollHeight) + 'px';
            userInput.focus();
        }
        
        function formatTimestamp() {
            const now = new Date();
            return now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        }
        
        // タイピングインジケーターを追加
        function addTypingIndicator() {
            const chatMessages = document.getElementById('chatMessages');
            const typingDiv = document.createElement('div');
            typingDiv.className = 'typing-indicator';
            typingDiv.id = 'typingIndicator';
            typingDiv.innerHTML = '<span></span><span></span><span></span>';
            chatMessages.appendChild(typingDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        // タイピングインジケーターを削除
        function removeTypingIndicator() {
            const indicator = document.getElementById('typingIndicator');
            if (indicator) {
                indicator.remove();
            }
        }
        
        // メッセージを追加する関数
        function addMessage(content, isUser = false) {
            removeTypingIndicator(); // タイピングインジケーターを削除
            
            const chatMessages = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${isUser ? 'user-message' : 'ai-message'}`;
            
            const messageContent = document.createElement('div');
            messageContent.className = 'message-content';
            
            // コードブロックを検出して適切にフォーマット
            if (!isUser) {
                // コードブロックを検出して適切にフォーマット
                const formattedContent = formatMessageContent(content);
                messageContent.innerHTML = formattedContent;
            } else {
                messageContent.textContent = content;
            }
            
            const messageTime = document.createElement('div');
            messageTime.className = 'message-time';
            messageTime.textContent = formatTimestamp();
            
            messageDiv.appendChild(messageContent);
            messageContent.appendChild(messageTime);
            
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        // AIメッセージを更新する関数
        function updateLastAIMessage(content) {
            const chatMessages = document.getElementById('chatMessages');
            const aiMessages = chatMessages.querySelectorAll('.ai-message');
            
            if (aiMessages.length > 0) {
                const lastAIMessage = aiMessages[aiMessages.length - 1];
                const messageContent = lastAIMessage.querySelector('.message-content');
                
                // 最初の子要素（メッセージ本文）を更新
                const formattedContent = formatMessageContent(content);
                
                // メッセージ時間を保持
                const messageTime = messageContent.querySelector('.message-time');
                
                // 内容を更新
                messageContent.innerHTML = formattedContent;
                messageContent.appendChild(messageTime);
                
                chatMessages.scrollTop = chatMessages.scrollHeight;
            } else {
                // AIメッセージがない場合は新しく追加
                addMessage(content, false);
            }
        }
        
        function formatMessageContent(content) {
            // コードブロックを検出して<div class="code-block">でラップ
            return content.replace(/```([\\s\\S]*?)```/g, '<div class="code-block">$1</div>')
                         .replace(/\\n/g, '<br>');
        }
        
        function addSystemMessage(content) {
            const chatMessages = document.getElementById('chatMessages');
            const messageDiv = document.createElement('div');
            messageDiv.className = 'system-message';
            messageDiv.textContent = content;
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }
        
        function setLoading(isLoading) {
            const sendButton = document.getElementById('sendButton');
            sendButton.disabled = isLoading;
            
            if (isLoading) {
                sendButton.innerHTML = '<div class="loading-indicator"></div>';
                userInput.disabled = true;
            } else {
                sendButton.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>';
                userInput.disabled = false;
                userInput.focus();
            }
        }
        
        // リアルタイムストリーミングを使用してメッセージを送信
        function sendMessage() {
            const userMessage = userInput.value.trim();
            if (!userMessage) return;
            
            // ユーザーメッセージを表示
            addMessage(userMessage, true);
            
            // 入力欄をクリア
            userInput.value = '';
            userInput.style.height = 'auto';
            
            // ローディング状態に設定
            setLoading(true);
            
            // タイピングインジケーターを表示
            addTypingIndicator();
            
            // EventSourceを使用してストリーミングデータを受信
            fetch('/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ instruction: userMessage })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error(`サーバーエラー: ${response.status} ${response.statusText}`);
                }
                
                // レスポンスをストリームとして処理
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let aiResponse = '';
                
                function processStream({ done, value }) {
                    if (done) {
                        // ストリーミング完了
                        removeTypingIndicator();
                        if (!aiResponse) {
                            addMessage("応答を生成できませんでした。", false);
                        }
                        setLoading(false);
                        return;
                    }
                    
                    // 受信したデータをデコード
                    buffer += decoder.decode(value, { stream: true });
                    
                    // SSEフォーマットのデータを処理
                    const lines = buffer.split('\\n\\n');
                    buffer = lines.pop(); // 最後の不完全な行を保持
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            try {
                                const data = JSON.parse(line.substring(6));
                                
                                if (data.status === 'start') {
                                    // 処理開始
                                    removeTypingIndicator();
                                    addMessage("", false); // 空のAIメッセージを追加
                                } else if (data.status === 'progress') {
                                    // 進行中のメッセージ
                                    aiResponse += data.message;
                                    updateLastAIMessage(aiResponse);
                                } else if (data.status === 'error') {
                                    // エラー
                                    removeTypingIndicator();
                                    addSystemMessage(`エラー: ${data.message}`);
                                }
                            } catch (e) {
                                console.error('JSON解析エラー:', e, line);
                            }
                        }
                    }
                    
                    // 次のチャンクを読み込む
                    return reader.read().then(processStream);
                }
                
                // ストリーム処理を開始
                return reader.read().then(processStream);
            })
            .catch(error => {
                console.error('Fetch Error:', error);
                removeTypingIndicator();
                addSystemMessage(`エラーが発生しました: ${error.message}`);
                setLoading(false);
            });
        }
        
        // リセットボタンのイベントリスナー
        document.getElementById('resetBtn').addEventListener('click', function() {
            if (confirm('会話履歴をリセットしますか？')) {
                fetch('/execute', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ reset: true })
                })
                .then(response => response.json())
                .then(data => {
                    // チャット履歴をクリア
                    const chatMessages = document.getElementById('chatMessages');
                    chatMessages.innerHTML = '';
                    
                    // 初期メッセージを追加
                    addMessage('こんにちは！Open Interpreterへようこそ。自然言語でコンピュータを操作できます。何をお手伝いしましょうか？');
                    
                    // リセット完了メッセージ
                    addSystemMessage(data.output);
                })
                .catch(error => {
                    console.error('Reset Error:', error);
                    addSystemMessage(`リセット中にエラーが発生しました: ${error.message}`);
                });
            }
        });
        
        // ページ読み込み時にテキストエリアにフォーカス
        window.addEventListener('load', function() {
            document.getElementById('userInput').focus();
        });
    </script>
</body>
</html>'''
    # render_template_string を使用してHTMLをレンダリング
    return render_template_string(html_template)

if __name__ == '__main__':
    # すべてのインターフェースでリッスンし、ポート5001を使用
    app.run(host='0.0.0.0', port=5001, debug=True)
