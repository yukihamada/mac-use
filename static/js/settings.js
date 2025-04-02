// 設定の保存と読み込み
const Settings = {
    theme: 'light',
    fontSize: 'medium',
    maxHistory: '50',

    save() {
        localStorage.setItem('settings', JSON.stringify(this));
    },

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
        this.updateList();
    },

    save() {
        localStorage.setItem('conversations', JSON.stringify(this.conversations));
    },

    add(conversation) {
        this.conversations.unshift(conversation);
        this.trim();
        this.save();
        this.updateList();
    },

    trim() {
        const max = Settings.maxHistory === 'unlimited' ? Infinity : parseInt(Settings.maxHistory);
        this.conversations = this.conversations.slice(0, max);
    },

    clear() {
        this.conversations = [];
        this.save();
        this.updateList();
    },

    updateList() {
        const list = document.getElementById('historyList');
        list.innerHTML = '';

        this.conversations.forEach((conv, index) => {
            const item = document.createElement('div');
            item.className = 'history-item';
            item.innerHTML = `
                <div class="history-item-title">${conv.title || '無題の会話'}</div>
                <div class="history-item-date">${new Date(conv.date).toLocaleString()}</div>
            `;
            item.addEventListener('click', () => {
                localStorage.setItem('currentConversation', JSON.stringify(conv));
                window.location.href = '/';
            });
            list.appendChild(item);
        });
    }
};

// 設定画面の初期化
function initializeSettings() {
    // 設定の読み込みと適用
    Settings.load();

    // 設定要素の初期値設定
    document.getElementById('theme').value = Settings.theme;
    document.getElementById('fontSize').value = Settings.fontSize;
    document.getElementById('maxHistory').value = Settings.maxHistory;

    // 設定変更イベントの設定
    document.getElementById('theme').addEventListener('change', (e) => {
        Settings.theme = e.target.value;
        Settings.save();
        Settings.apply();
    });

    document.getElementById('fontSize').addEventListener('change', (e) => {
        Settings.fontSize = e.target.value;
        Settings.save();
        Settings.apply();
    });

    document.getElementById('maxHistory').addEventListener('change', (e) => {
        Settings.maxHistory = e.target.value;
        Settings.save();
        History.trim();
        History.save();
        History.updateList();
    });

    // 履歴削除ボタンの設定
    document.getElementById('clearHistory').addEventListener('click', () => {
        if (confirm('会話履歴を削除してもよろしいですか？')) {
            History.clear();
        }
    });

    // 会話履歴の読み込みと表示
    History.load();
}

// 初期化を実行
initializeSettings(); 