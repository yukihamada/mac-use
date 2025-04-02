// DOM要素の取得
const userInput = document.getElementById('userInput');
const sendButton = document.getElementById('sendButton');
const resetButton = document.getElementById('resetButton');
const stopButton = document.getElementById('stopButton');

// WebSocket接続の設定
let ws = null;
let reconnectAttempts = 0;
const maxReconnectAttempts = 5;
let reconnectTimeout = null;
let isConnecting = false;
let isIntentionalClose = false;

// 設定の読み込みと適用
const Settings = {
    theme: 'light',
    fontSize: 'medium',
    maxHistory: '50',

    load() {
        const saved = localStorage.getItem('settings');
        if (saved) {
            Object.assign(this, JSON.parse(saved));
        }
        this.apply();
    },

    apply() {
        document.documentElement.setAttribute('data-theme', this.theme);
        document.documentElement.setAttribute('data-font-size', this.fontSize);
    }
};

// 会話履歴の管理
const History = {
    conversations: [],

    load() {
        const saved = localStorage.getItem('conversations');
        if (saved) {
            this.conversations = JSON.parse(saved);
        }
    },

    save() {
        localStorage.setItem('conversations', JSON.stringify(this.conversations));
    },

    add(conversation) {
        this.conversations.unshift(conversation);
        this.trim();
        this.save();
    },

    trim() {
        const max = Settings.maxHistory === 'unlimited' ? Infinity : parseInt(Settings.maxHistory);
        this.conversations = this.conversations.slice(0, max);
    }
};

// チャット関連の変数
let currentConversation = {
    messages: [],
    title: '',
    date: new Date().toISOString()
};

// メッセージの受信処理
let currentMessage = '';
let isNewQuestion = true;  // 新しい質問かどうかを追跡

// メッセージハンドラーの定義
const messageHandlers = {
    start: (message) => {
        addSystemMessage(message);
        setLoading(true);
        currentMessage = ''; // 新しいメッセージの開始時にクリア
        isNewQuestion = true;  // 新しい質問としてマーク
    },
    progress: (message) => {
        // タイピングインジケーターを非表示
        updateTypingIndicator(false);
        
        // メッセージを蓄積
        currentMessage += message;
        
        // 新しいメッセージとして表示
        const chatMessages = document.getElementById('chatMessages');
        const aiMessages = chatMessages.querySelectorAll('.ai-message');
        
        if (isNewQuestion) {
            // 新しい質問の場合は新しいメッセージを作成
            addMessage(currentMessage, false);
            isNewQuestion = false;
        } else if (aiMessages.length > 0) {
            // 既存の回答の場合は最後のメッセージを更新
            const lastAIMessage = aiMessages[aiMessages.length - 1];
            const messageContent = lastAIMessage.querySelector('.message-content');
            messageContent.innerHTML = formatMessageContent(currentMessage);
        }
        
        setLoading(true);
    },
    complete: (message) => {
        // 最後のメッセージを確定
        if (currentMessage) {
            const chatMessages = document.getElementById('chatMessages');
            const aiMessages = chatMessages.querySelectorAll('.ai-message');
            if (aiMessages.length > 0) {
                const lastAIMessage = aiMessages[aiMessages.length - 1];
                const messageContent = lastAIMessage.querySelector('.message-content');
                messageContent.innerHTML = formatMessageContent(currentMessage);
            }
        }
        addSystemMessage(message);
        setLoading(false);
        removeTypingIndicator();
        currentMessage = ''; // メッセージ完了時にクリア
    },
    error: (message) => {
        addSystemMessage(message, true);
        setLoading(false);
        removeTypingIndicator();
        currentMessage = ''; // エラー時にクリア
    },
    success: (message) => {
        addSystemMessage(message);
        currentMessage = ''; // 成功時にクリア
    }
};

// 初期化関数
function initialize() {
    if (!userInput || !sendButton || !resetButton || !stopButton) {
        console.error('必要なDOM要素が見つかりません');
        return;
    }

    // テキストエリアの高さを自動調整する関数
    userInput.addEventListener('input', function() {
        this.style.height = 'auto';
        this.style.height = (Math.min(this.scrollHeight, 120)) + 'px';
    });

    // Enterキーでの送信
    userInput.addEventListener('keydown', function(event) {
        if (event.keyCode === 13 && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    // 送信ボタンのクリックイベント
    sendButton.addEventListener('click', sendMessage);

    // ストップボタンのクリックイベント
    stopButton.addEventListener('click', stopProcess);

    // リセットボタンのクリックイベント
    resetButton.addEventListener('click', () => {
        if (confirm('会話をリセットしてもよろしいですか？')) {
            document.getElementById('chatMessages').innerHTML = '';
            currentConversation = {
                messages: [],
                title: '',
                date: new Date().toISOString()
            };
            addSystemMessage('会話をリセットしました。新しい会話を開始してください。');
        }
    });

    // 例示ボタンのクリックイベント
    document.querySelectorAll('[data-example]').forEach(button => {
        button.addEventListener('click', function() {
            const example = this.getAttribute('data-example');
            setExample(example);
        });
    });

    // WebSocket接続を開始
    connectWebSocket();
}

// 初期化を実行
initialize();

// WebSocketメッセージの処理
function handleWebSocketMessage(data) {
    const handler = messageHandlers[data.status];
    if (handler && typeof handler === 'function') {
        handler(data.message);
    } else {
        console.warn('未処理のメッセージステータス:', data.status);
    }
}

// WebSocket接続の確立
function connectWebSocket() {
    if (isConnecting || (ws && ws.readyState === WebSocket.OPEN)) {
        console.log('既存の接続が存在するため、新しい接続を作成しません');
        return;
    }

    if (ws) {
        console.log('既存の接続をクリーンアップします');
        ws.close();
    }
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
    }

    isConnecting = true;
    isIntentionalClose = false;
    
    const wsUrl = 'ws://127.0.0.1:5001/ws';
    console.log('WebSocket接続を開始します:', wsUrl);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket接続が確立されました');
        reconnectAttempts = 0;
        stopButton.disabled = true;
        isConnecting = false;
        addSystemMessage('WebSocket接続が確立されました');
    };
    
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            console.log('受信メッセージ:', data);
            handleWebSocketMessage(data);
        } catch (error) {
            console.error('メッセージの解析中にエラーが発生しました:', error);
        }
    };
    
    ws.onclose = (event) => {
        console.log('WebSocket接続が閉じられました:', event.code, event.reason);
        stopButton.disabled = true;
        isConnecting = false;
        
        if (isIntentionalClose) {
            console.log('意図的な切断のため、再接続しません');
            addSystemMessage('WebSocket接続が閉じられました');
            return;
        }
        
        addSystemMessage('WebSocket接続が切断されました。再接続を試みます...');
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 30000);
            console.log(`${reconnectAttempts}回目の再接続を${delay}ms後に試みます`);
            reconnectTimeout = setTimeout(connectWebSocket, delay);
        } else {
            console.log('再接続の試行回数が上限に達しました');
            addSystemMessage('再接続の試行回数が上限に達しました。ページをリロードしてください。');
        }
    };
    
    ws.onerror = (error) => {
        console.error('WebSocketエラー:', error);
        stopButton.disabled = true;
        isConnecting = false;
        addSystemMessage('WebSocket接続でエラーが発生しました');
    };
}

function stopProcess() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            content: "stop"
        }));
        stopButton.disabled = true;
    }
}

function setExample(text) {
    userInput.value = text;
    userInput.style.height = 'auto';
    userInput.style.height = (Math.min(userInput.scrollHeight, 120)) + 'px';
    userInput.focus();
}

function formatTimestamp() {
    return new Date().toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' });
}

// タイピングインジケーターを追加
function addTypingIndicator() {
    const chatMessages = document.getElementById('chatMessages');
    const typingDiv = document.createElement('div');
    typingDiv.className = 'typing-indicator';
    typingDiv.id = 'typingIndicator';
    
    // インラインHTMLの代わりにDOM APIを使用
    for (let i = 0; i < 3; i++) {
        const span = document.createElement('span');
        typingDiv.appendChild(span);
    }
    
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

function formatMessageContent(content) {
    // contentが文字列でない場合は空文字列を返す
    if (typeof content !== 'string') {
        return '';
    }

    // コードブロックの処理を安全に行う
    const codeBlockRegex = /```([\s\S]*?)```/g;
    const formattedContent = content.replace(codeBlockRegex, (match, code) => {
        const codeBlock = document.createElement('div');
        codeBlock.className = 'code-block';
        codeBlock.textContent = code;
        return codeBlock.outerHTML;
    });
    
    // 改行の処理を安全に行う
    return formattedContent.replace(/\\n/g, '<br>');
}

// メッセージを追加する関数
function addMessage(content, isUser = false) {
    removeTypingIndicator();
    
    const chatMessages = document.getElementById('chatMessages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isUser ? 'user-message' : 'ai-message'}`;
    
    const messageContent = document.createElement('div');
    messageContent.className = 'message-content';
    
    if (!isUser) {
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
        
        // 既存のメッセージを保持
        const existingContent = messageContent.innerHTML;
        
        // 新しいコンテンツを追加
        const formattedContent = formatMessageContent(content);
        messageContent.innerHTML = existingContent + formattedContent;
        
        // タイムスタンプを更新
        const messageTime = messageContent.querySelector('.message-time');
        if (messageTime) {
            messageTime.textContent = formatTimestamp();
        }
        
        chatMessages.scrollTop = chatMessages.scrollHeight;
    } else {
        addMessage(content, false);
    }
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
    sendButton.disabled = isLoading;
    
    if (isLoading) {
        const loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'loading-indicator';
        sendButton.innerHTML = '';
        sendButton.appendChild(loadingIndicator);
        userInput.disabled = true;
    } else {
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
        svg.setAttribute('viewBox', '0 0 24 24');
        svg.setAttribute('fill', 'none');
        svg.setAttribute('stroke', 'currentColor');
        svg.setAttribute('stroke-width', '2');
        svg.setAttribute('stroke-linecap', 'round');
        svg.setAttribute('stroke-linejoin', 'round');
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', '22');
        line.setAttribute('y1', '2');
        line.setAttribute('x2', '11');
        line.setAttribute('y2', '13');
        
        const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        polygon.setAttribute('points', '22 2 15 22 11 13 2 9 22 2');
        
        svg.appendChild(line);
        svg.appendChild(polygon);
        
        sendButton.innerHTML = '';
        sendButton.appendChild(svg);
        userInput.disabled = false;
        userInput.focus();
    }
}

// タイピングインジケーターの更新
function updateTypingIndicator(isTyping) {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) {
        indicator.style.display = isTyping ? 'block' : 'none';
    }
}

// メッセージの送信
async function sendMessage() {
    const userInput = document.getElementById('userInput');
    const message = userInput.value.trim();
    
    if (!message) return;
    
    // 入力欄をクリア
    userInput.value = '';
    userInput.style.height = 'auto';
    
    // ユーザーメッセージを表示
    addMessage(message, true);
    
    // タイピングインジケーターを表示
    addTypingIndicator();
    
    // WebSocketが接続されていない場合は接続を試みる
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        connectWebSocket();
    }
    
    // メッセージを送信
    ws.send(JSON.stringify({
        type: 'message',
        content: message
    }));
}

// メッセージの受信処理
function progress(data) {
    if (data.status === 'progress') {
        // タイピングインジケーターを非表示
        updateTypingIndicator(false);
        
        // メッセージを表示
        updateLastAIMessage(data.message);
    }
}

// ページ読み込み時の初期化
window.addEventListener('load', function() {
    userInput.focus();
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        console.log('ページ読み込み時の初期接続を開始します');
        connectWebSocket();
    }
}); 