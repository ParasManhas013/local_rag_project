const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const statusDiv = document.getElementById('upload-status');
const chatHistory = document.getElementById('chat-history');

const fileList = document.getElementById('file-list');

async function fetchFileList() {
    try {
        const res = await fetch('/list-files');
        const data = await res.json();
        const files = data.files;
        const activeDoc = data.active_document;

        document.getElementById('active-doc-name').innerText = activeDoc || 'None';
        fileList.innerHTML = ''; // Clear the list

        if (files.length === 0) {
            fileList.innerHTML = '<p>No files uploaded yet.</p>';
            return;
        }

        files.forEach(file => {
            const fileDiv = document.createElement('div');
            fileDiv.classList.add('file-item');
            if (file === activeDoc) {
                fileDiv.classList.add('active');
            }
            
            const fileNameSpan = document.createElement('span');
            fileNameSpan.innerText = file;
            fileNameSpan.onclick = () => showFileContent(file);
            fileDiv.appendChild(fileNameSpan);

            const actionsDiv = document.createElement('div');
            actionsDiv.classList.add('file-actions');

            if (file !== activeDoc) {
                const activateBtn = document.createElement('button');
                activateBtn.innerText = 'Set Active';
                activateBtn.classList.add('btn-secondary', 'btn-small');
                activateBtn.onclick = () => setActiveDocument(file);
                actionsDiv.appendChild(activateBtn);
            }

            const deleteBtn = document.createElement('button');
            deleteBtn.innerText = '🗑️';
            deleteBtn.classList.add('btn-danger', 'btn-small');
            deleteBtn.onclick = () => deleteFile(file);
            actionsDiv.appendChild(deleteBtn);

            fileDiv.appendChild(actionsDiv);
            fileList.appendChild(fileDiv);
        });
    } catch (err) {
        console.error("Error fetching file list:", err);
        fileList.innerHTML = "Could not load files.";
    }
}

async function showFileContent(filename) {
    try {
        const res = await fetch('/get-file-content', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename })
        });
        if (res.ok) {
            const data = await res.json();
            appendMessage('System', `**Content of ${data.filename}:**\n${data.content}`);
        } else {
            alert('Failed to load file content.');
        }
    } catch (err) {
        console.error("Error loading file content:", err);
        alert('Error loading file content.');
    }
}

async function deleteFile(filename) {
    try {
        const res = await fetch('/delete-file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename })
        });
        if (res.ok) {
            fetchFileList(); // Refresh file list
        } else {
            alert('Failed to delete file.');
        }
    } catch (err) {
        console.error("Error deleting file:", err);
        alert('Error deleting file.');
    }
}

// Drag & Drop Handlers
dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.style.borderColor = '#fff'; });
dropZone.addEventListener('dragleave', (e) => { dropZone.style.borderColor = '#89b4fa'; });
dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '#89b4fa';
    handleFiles(e.dataTransfer.files);
});
dropZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => handleFiles(fileInput.files));

async function handleFiles(files) {
    if (files.length === 0) return;
    const formData = new FormData();
    formData.append('file', files[0]);

    statusDiv.innerText = "Uploading & Indexing... (This uses CPU/GPU)";
    try {
        const res = await fetch('/upload', { method: 'POST', body: formData });
        const data = await res.json();
        statusDiv.innerText = `✅ Success! Processed ${data.chunks_processed} chunks.`;
        fetchFileList(); // Refresh file list and active status
    } catch (err) {
        statusDiv.innerText = "❌ Error uploading file.";
    }
}

async function setActiveDocument(filename) {
    try {
        const res = await fetch('/set-active-document', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ filename: filename })
        });
        if (res.ok) {
            fetchFileList(); // Refresh UI to show new active document
            appendMessage('System', `Active document set to: ${filename}`);
        } else {
            const errorData = await res.json();
            alert(`Failed to set active document: ${errorData.detail}`);
        }
    } catch (err) {
        console.error("Error setting active document:", err);
        alert('Error setting active document.');
    }
}

// Initial Load
window.onload = () => {
    fetchFileList();
    appendMessage('System', 'Welcome! Upload a document or ask a question about the existing documents.');
};

async function sendQuery() {
    const input = document.getElementById('user-query');
    const text = input.value;
    if (!text) {
        alert('Please enter a query.');
        return;
    }

    appendMessage('User', text);
    input.value = '';

    const loadingDiv = appendMessage('System', '...');
    loadingDiv.classList.add('loading');

    try {
        const res = await fetch('/query', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: text })
        });
        const data = await res.json();
        
        loadingDiv.innerText = data.answer;
        loadingDiv.classList.remove('loading');

        const sources = data.context.map(item => item.source).filter((value, index, self) => self.indexOf(value) === index);
        if (sources && sources.length > 0) {
            const sourcesDiv = document.createElement('div');
            sourcesDiv.classList.add('sources');
            sourcesDiv.innerText = 'Sources: ' + sources.join(', ');
            loadingDiv.appendChild(sourcesDiv);
        }
    } catch (err) {
        loadingDiv.innerText = 'Error: Could not get a response.';
        loadingDiv.classList.remove('loading');
    }
}

async function summarizeDoc() {
    appendMessage('System', 'Generating summary... please wait.');
    const res = await fetch('/summarize', { method: 'POST' });
    const data = await res.json();
    appendMessage('System', `📝 **Summary:**\n${data.summary}`);
}

async function generatePPT() {
    appendMessage('System', 'Generating PPT... Check downloads folder shortly.');
    const res = await fetch('/generate-ppt', { method: 'POST' });
    if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = "RAG_Presentation.pptx";
        document.body.appendChild(a);
        a.click();
        appendMessage('System', '✅ PPT Downloaded!');
    } else {
        appendMessage('System', '❌ Failed to generate PPT.');
    }
}

function appendMessage(sender, text, sources) {
    const div = document.createElement('div');
    div.classList.add('message', sender === 'User' ? 'user-msg' : 'bot-msg');
    
    const textDiv = document.createElement('div');
    textDiv.innerText = text;
    div.appendChild(textDiv);

    if (sources && sources.length > 0) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.classList.add('sources');
        sourcesDiv.innerText = 'Sources: ' + sources.join(', ');
        div.appendChild(sourcesDiv);
    }

    chatHistory.appendChild(div);
    chatHistory.scrollTop = chatHistory.scrollHeight;
    return div;
}

function clearChat() {
    chatHistory.innerHTML = '';
}