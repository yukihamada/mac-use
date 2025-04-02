import os
import json
import time
import logging
import asyncio
from typing import Dict, List, Optional, Any
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
import interpreter
from config.settings import FLASK_HOST, FLASK_PORT, FLASK_DEBUG, ANTHROPIC_API_KEY
from utils.interpreter_utils import setup_interpreter, extract_output

# ロギングの設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 設定値
CORS_ORIGINS = [
    "http://127.0.0.1:5001",
    "http://localhost:5001",
    "ws://127.0.0.1:5001",
    "ws://localhost:5001"
]

CSP_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self' ws: wss:; "
    "font-src 'self'; "
    "frame-ancestors 'none';"
)

class CSPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP_POLICY
        return response

class ProcessManager:
    def __init__(self):
        self.active_processes: Dict[str, Any] = {}
        self.stop_events: Dict[str, asyncio.Event] = {}

    def create_stop_event(self, process_id: str) -> asyncio.Event:
        self.stop_events[process_id] = asyncio.Event()
        return self.stop_events[process_id]

    def get_stop_event(self, process_id: str) -> Optional[asyncio.Event]:
        return self.stop_events.get(process_id)

    def set_process(self, process_id: str, process: Any) -> None:
        self.active_processes[process_id] = process

    def remove_process(self, process_id: str) -> None:
        self.active_processes.pop(process_id, None)
        self.stop_events.pop(process_id, None)

    async def stop_process(self, process_id: str) -> None:
        if process_id in self.stop_events:
            self.stop_events[process_id].set()
            if process_id in self.active_processes:
                try:
                    self.active_processes[process_id].cancel()
                except Exception as e:
                    logger.error(f"プロセス停止中にエラーが発生: {str(e)}")
                finally:
                    self.remove_process(process_id)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_processes: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket) -> None:
        self.active_connections.append(websocket)
        self.connection_processes[websocket] = str(id(websocket))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            if websocket in self.connection_processes:
                process_id = self.connection_processes[websocket]
                asyncio.create_task(process_manager.stop_process(process_id))
                del self.connection_processes[websocket]

    async def send_message(self, message: str, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"メッセージ送信中にエラーが発生: {str(e)}")
                self.disconnect(websocket)

# FastAPIアプリケーションの初期化
app = FastAPI(title="AI Chat Application")

# ミドルウェアの設定
app.add_middleware(CSPMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静的ファイルとテンプレートの設定
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# グローバル変数の初期化
process_manager = ProcessManager()
manager = ConnectionManager()
interpreter = None

# Open Interpreterの初期化
def initialize_interpreter() -> None:
    global interpreter
    try:
        interpreter = setup_interpreter()
        if interpreter is None:
            raise Exception("Open Interpreterの初期化に失敗しました。APIキーが正しく設定されているか確認してください。")
        logger.info("Open Interpreterの初期化が完了しました")
    except Exception as e:
        logger.error(f"Open Interpreterの初期化中にエラーが発生しました: {str(e)}")
        interpreter = None

@app.on_event("startup")
async def startup_event():
    initialize_interpreter()

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """チャット形式のHTMLフロントエンドを提供するエンドポイント"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/settings", response_class=HTMLResponse)
async def settings(request: Request):
    """設定画面を提供するエンドポイント"""
    return templates.TemplateResponse("settings.html", {"request": request})

@app.post("/execute")
async def execute_command(request: Request):
    """コマンドを実行するエンドポイント"""
    if interpreter is None:
        raise HTTPException(
            status_code=503,
            detail="Open Interpreterが初期化されていません。APIキーが正しく設定されているか確認してください。"
        )

    try:
        data = await request.json()
        command = data.get("command")
        
        if not command:
            return {"error": "コマンドが指定されていません"}

        logger.info(f"実行コマンド: {command}")
        
        async def generate():
            try:
                messages = interpreter.interpreter.chat(command)
                for chunk in messages:
                    if chunk.get("type") == "output":
                        yield f"data: {json.dumps({'type': 'output', 'content': chunk['content']})}\n\n"
            except Exception as e:
                logger.error(f"コマンド実行中にエラーが発生: {str(e)}")
                yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
        
        return StreamingResponse(generate(), media_type="text/event-stream")

    except Exception as e:
        logger.error(f"エラーが発生しました: {str(e)}")
        return {"error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocketエンドポイント"""
    try:
        if interpreter is None:
            logger.error("Open Interpreterが初期化されていません")
            await websocket.close(code=1011, reason="Open Interpreterが初期化されていません")
            return

        await websocket.accept()
        logger.info("WebSocket接続が確立されました")

        await manager.connect(websocket)
        process_id = manager.connection_processes[websocket]
        stop_event = process_manager.create_stop_event(process_id)
        logger.info(f"接続ID: {process_id} が登録されました")

        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)
                logger.info(f"受信メッセージ: {message}")
                
                if message.get("content") == "reset":
                    interpreter.interpreter.reset()
                    await manager.send_message(json.dumps({
                        "status": "success",
                        "message": "会話履歴をリセットしました。"
                    }), websocket)
                    continue

                if message.get("content") == "stop":
                    await process_manager.stop_process(process_id)
                    await manager.send_message(json.dumps({
                        "status": "success",
                        "message": "処理を停止しました。"
                    }), websocket)
                    continue

                await handle_chat_message(message, websocket, process_id, stop_event)

        except WebSocketDisconnect:
            logger.info(f"WebSocket接続が切断されました: {process_id}")
        finally:
            manager.disconnect(websocket)

    except Exception as e:
        logger.error(f"WebSocket処理中にエラーが発生: {str(e)}")
        await websocket.close(code=1011, reason=str(e))

async def handle_chat_message(message: dict, websocket: WebSocket, process_id: str, stop_event: asyncio.Event) -> None:
    """チャットメッセージを処理する関数"""
    try:
        # 開始メッセージを送信（前のメッセージをクリア）
        await manager.send_message(json.dumps({
            "status": "start",
            "message": "処理を開始しています...",
            "clear": True  # クライアント側でメッセージをクリアするためのフラグ
        }), websocket)

        messages = interpreter.interpreter.chat(message.get("content", ""), display=False, stream=True)
        process_manager.set_process(process_id, messages)

        last_message = ""
        for chunk in messages:
            if stop_event.is_set():
                logger.info(f"接続ID: {process_id} の処理が停止されました")
                break
            if isinstance(chunk, dict):
                content = chunk.get('content', '')
                if isinstance(content, dict):
                    content = str(content)
                # 前のメッセージと新しいメッセージが異なる場合のみ送信
                if content and content != last_message and not str(content).startswith('[object Object]') and not str(content).startswith('null'):
                    last_message = content
                    await manager.send_message(json.dumps({
                        "status": "progress",
                        "message": content,
                        "append": True,
                        "replace": True  # 前のメッセージを置き換える
                    }), websocket)
                await asyncio.sleep(0.05)

        if not stop_event.is_set():
            # 最終的なメッセージを送信
            if last_message and not str(last_message).startswith('[object Object]') and not str(last_message).startswith('null'):
                await manager.send_message(json.dumps({
                    "status": "complete",
                    "message": last_message,  # 最終的なメッセージを送信
                    "append": True,
                    "replace": True
                }), websocket)
            await manager.send_message(json.dumps({
                "status": "complete",
                "message": "処理が完了しました",
                "append": True
            }), websocket)

    except Exception as e:
        logger.error(f"メッセージ処理中にエラーが発生しました: {str(e)}")
        await manager.send_message(json.dumps({
            "status": "error",
            "message": str(e),
            "append": True
        }), websocket)

@app.post("/stop/{process_id}")
async def stop_process(process_id: str):
    """プロセスを停止するエンドポイント"""
    try:
        await process_manager.stop_process(process_id)
        return {"status": "success", "message": "プロセスを停止しました"}
    except Exception as e:
        logger.error(f"プロセス停止中にエラーが発生: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",  # すべてのネットワークインターフェースからのアクセスを許可
        port=FLASK_PORT,
        reload=FLASK_DEBUG
    )
