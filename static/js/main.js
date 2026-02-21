// YouTube URL Input Management
function addUrlInput() {
    const container = document.getElementById('youtube-urls');
    const div = document.createElement('div');
    div.className = 'url-input-group';
    div.innerHTML = `
        <input type="text" class="youtube-url" placeholder="YouTube URLを入力">
        <button class="remove-url-btn" onclick="removeUrlInput(this)">×</button>
    `;
    container.appendChild(div);
}

function removeUrlInput(btn) {
    const groups = document.querySelectorAll('.url-input-group');
    if (groups.length > 1) {
        btn.parentElement.remove();
    }
}

// Download from YouTube
async function downloadFromYoutube() {
    const urlInputs = document.querySelectorAll('.youtube-url');
    const urls = Array.from(urlInputs)
        .map(input => input.value.trim())
        .filter(url => url.length > 0);

    if (urls.length === 0) {
        showStatus('youtube-status', 'URLを入力してください', 'error');
        return;
    }

    const statusDiv = document.getElementById('youtube-status');
    const resultsDiv = document.getElementById('youtube-results');

    statusDiv.innerHTML = '<span class="loading"></span> ダウンロード中...';
    resultsDiv.innerHTML = '';

    try {
        const response = await fetch('/download_youtube', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ urls: urls })
        });

        const data = await response.json();

        if (data.downloaded && data.downloaded.length > 0) {
            let html = '<h3>ダウンロード完了:</h3>';
            data.downloaded.forEach(item => {
                html += `<div class="result-item">
                    <strong>${item.title}</strong><br>
                    <small>${item.filename}</small>
                    <a href="/get_audio/${item.filename}" class="download-link" download>ダウンロード</a>
                </div>`;
            });
            resultsDiv.innerHTML = html;
        }

        if (data.errors && data.errors.length > 0) {
            let errorHtml = '<h3>エラー:</h3>';
            data.errors.forEach(err => {
                errorHtml += `<div class="result-item result-error">
                    <strong>${err.url}</strong><br>
                    <small>${err.error}</small>
                </div>`;
            });
            resultsDiv.innerHTML += errorHtml;
        }

        statusDiv.innerHTML = `<span class="success">処理完了 (${data.downloaded.length}件成功)</span>`;

    } catch (error) {
        statusDiv.innerHTML = `<span class="error">エラー: ${error.message}</span>`;
    }
}

// File Upload
function updateSelectedFiles() {
    const input = document.getElementById('audio-files');
    const display = document.getElementById('selected-files');

    if (input.files.length > 0) {
        let html = '<p>選択されたファイル:</p>';
        Array.from(input.files).forEach(file => {
            html += `<p>${file.name}</p>`;
        });
        display.innerHTML = html;
    } else {
        display.innerHTML = '';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const fileInput = document.getElementById('audio-files');
    if (fileInput) {
        fileInput.addEventListener('change', updateSelectedFiles);
    }
});

async function uploadFiles() {
    const input = document.getElementById('audio-files');
    const statusDiv = document.getElementById('upload-status');

    if (input.files.length === 0) {
        alert('ファイルを選択してください');
        return;
    }

    const formData = new FormData();
    Array.from(input.files).forEach(file => {
        formData.append('files[]', file);
    });

    try {
        const response = await fetch('/upload_files', {
            method: 'POST',
            body: formData
        });

        const data = await response.json();

        if (data.success && data.redirect) {
            window.location.href = data.redirect;
        } else {
            alert('アップロードに失敗しました');
        }
    } catch (error) {
        alert('エラー: ' + error.message);
    }
}

// Utility Functions
function showStatus(elementId, message, type) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `<span class="${type}">${message}</span>`;
    }
}
