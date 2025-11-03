class OpenChat {
    constructor() {
        this.apiBase = window.location.origin;
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isLoading = false;
        
        this.initializeElements();
        this.bindEvents();
        this.checkHealth();
        this.loadVoices();
        this.loadModels();
        this.loadConversationHistory();
    }

    initializeElements() {
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.micBtn = document.getElementById('mic-btn');
        this.modelSelect = document.getElementById('model-select');
        this.ttsSelect = document.getElementById('tts-select');
        this.voiceSelect = document.getElementById('voice-select');
        
        // Status indicators
        this.ollamaStatus = document.getElementById('ollama-status');
        this.ttsStatus = document.getElementById('tts-status');
        this.sttStatus = document.getElementById('stt-status');
        this.ttsProvider = document.getElementById('tts-provider');
    }

    bindEvents() {
        this.sendBtn.addEventListener('click', () => this.sendMessage());
        this.micBtn.addEventListener('click', () => this.toggleRecording());
        
        this.messageInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        this.messageInput.addEventListener('input', () => {
            this.sendBtn.disabled = !this.messageInput.value.trim() || this.isLoading;
        });

        // Auto-scroll messages
        this.messagesContainer.addEventListener('DOMNodeInserted', () => {
            this.scrollToBottom();
        });
    }

    async checkHealth() {
        try {
            const response = await fetch(`${this.apiBase}/health`);
            const health = await response.json();
            
            this.updateStatus('ollama', health.ollama_connected);
            this.updateStatus('tts', health.services.includes('tts-elevenlabs') || health.services.includes('tts-local'));
            this.updateStatus('stt', health.services.includes('stt'));
            
            this.ttsProvider.textContent = `TTS (${health.tts_provider})`;
            
            // Set TTS selector based on current provider
            this.ttsSelect.value = health.tts_provider;
            
        } catch (error) {
            console.error('Health check failed:', error);
            this.updateStatus('ollama', false);
            this.updateStatus('tts', false);
            this.updateStatus('stt', false);
        }
    }

    updateStatus(service, isHealthy) {
        const statusElement = document.getElementById(`${service}-status`);
        statusElement.className = `status-dot ${isHealthy ? '' : 'error'}`;
    }

    async loadVoices() {
        try {
            const response = await fetch(`${this.apiBase}/voices`);
            const data = await response.json();
            
            // Clear existing options except first one
            this.voiceSelect.innerHTML = '';
            
            // Group voices by category
            const groupedVoices = {};
            data.voices.forEach(voice => {
                if (!groupedVoices[voice.category]) {
                    groupedVoices[voice.category] = [];
                }
                groupedVoices[voice.category].push(voice);
            });
            
            // Add voices with category grouping
            Object.keys(groupedVoices).sort().forEach(category => {
                const optgroup = document.createElement('optgroup');
                optgroup.label = category.charAt(0).toUpperCase() + category.slice(1);
                
                groupedVoices[category].forEach(voice => {
                    const option = document.createElement('option');
                    option.value = voice.id;
                    option.textContent = voice.name;
                    optgroup.appendChild(option);
                });
                
                this.voiceSelect.appendChild(optgroup);
            });
            
            // Set default voice
            this.voiceSelect.value = config.ELEVENLABS_VOICE_ID || data.voices[0]?.id;
            
        } catch (error) {
            console.error('Failed to load voices:', error);
        }
    }

    async loadModels() {
        try {
            const response = await fetch(`${this.apiBase}/models`);
            const data = await response.json();
            
            // Clear existing options
            this.modelSelect.innerHTML = '';
            
            // Add models
            data.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model;
                option.textContent = model;
                this.modelSelect.appendChild(option);
            });
            
            // Set default model
            if (data.models.length > 0) {
                this.modelSelect.value = data.models[0];
            }
            
        } catch (error) {
            console.error('Failed to load models:', error);
        }
    }

    async loadConversationHistory() {
        try {
            const response = await fetch(`${this.apiBase}/conversations`);
            const data = await response.json();
            
            // Clear existing messages except welcome message
            const welcomeMessage = this.messagesContainer.querySelector('.message.assistant');
            this.messagesContainer.innerHTML = '';
            if (welcomeMessage) {
                this.messagesContainer.appendChild(welcomeMessage);
            }
            
            // Add conversation history
            data.messages.forEach(msg => {
                this.addMessage(msg.content, msg.role, msg.audio_file, new Date(msg.timestamp));
            });
            
        } catch (error) {
            console.error('Failed to load conversation history:', error);
        }
    }

    async sendMessage() {
        const message = this.messageInput.value.trim();
        if (!message || this.isLoading) return;

        this.setLoading(true);
        this.messageInput.value = '';

        // Add user message to UI
        this.addMessage(message, 'user');

        try {
            const response = await fetch(`${this.apiBase}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    model: this.modelSelect.value,
                    voice_id: this.voiceSelect.value
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            // Add assistant response to UI
            this.addMessage(data.response, 'assistant', data.audio_file, new Date(data.timestamp));
            
            // Auto-play audio if available
            if (data.audio_file) {
                setTimeout(() => this.playAudio(data.audio_file), 500);
            }

        } catch (error) {
            console.error('Chat error:', error);
            this.addMessage(
                `Sorry, I encountered an error: ${error.message}. Please check if Ollama is running and try again.`,
                'assistant',
                null,
                null,
                true
            );
        } finally {
            this.setLoading(false);
        }
    }

    async toggleRecording() {
        if (this.isRecording) {
            this.stopRecording();
        } else {
            await this.startRecording();
        }
    }

    async startRecording() {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 44100
                } 
            });
            
            this.audioChunks = [];
            this.mediaRecorder = new MediaRecorder(stream, {
                mimeType: 'audio/webm'
            });
            
            this.mediaRecorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };
            
            this.mediaRecorder.onstop = () => {
                this.processRecording();
                stream.getTracks().forEach(track => track.stop());
            };
            
            this.mediaRecorder.start();
            this.isRecording = true;
            this.micBtn.classList.add('recording');
            this.micBtn.title = 'Click to stop recording';
            
        } catch (error) {
            console.error('Failed to start recording:', error);
            alert('Microphone access denied or not available. Please check your browser settings.');
        }
    }

    stopRecording() {
        if (this.mediaRecorder && this.isRecording) {
            this.mediaRecorder.stop();
            this.isRecording = false;
            this.micBtn.classList.remove('recording');
            this.micBtn.title = 'Click to speak';
        }
    }

    async processRecording() {
        if (this.audioChunks.length === 0) return;

        this.setLoading(true);
        
        try {
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');

            const response = await fetch(`${this.apiBase}/transcribe`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const data = await response.json();
            
            if (data.text.trim()) {
                this.messageInput.value = data.text;
                this.sendMessage();
            } else {
                alert('No speech detected. Please try again.');
            }

        } catch (error) {
            console.error('Transcription error:', error);
            alert(`Failed to transcribe audio: ${error.message}`);
        } finally {
            this.setLoading(false);
        }
    }

    addMessage(content, role, audioFile = null, timestamp = null, isError = false) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = `message-content ${isError ? 'error' : ''}`;
        
        const textDiv = document.createElement('div');
        textDiv.textContent = content;
        contentDiv.appendChild(textDiv);
        
        // Add metadata for assistant messages
        if (role === 'assistant') {
            const metaDiv = document.createElement('div');
            metaDiv.className = 'message-meta';
            
            // Add timestamp
            const timeSpan = document.createElement('span');
            const time = timestamp || new Date();
            timeSpan.textContent = time.toLocaleTimeString();
            metaDiv.appendChild(timeSpan);
            
            // Add audio controls if available
            if (audioFile) {
                const audioControls = document.createElement('div');
                audioControls.className = 'audio-controls';
                
                const playBtn = document.createElement('button');
                playBtn.className = 'play-btn';
                playBtn.innerHTML = '🔊';
                playBtn.title = 'Play audio';
                playBtn.onclick = () => this.playAudio(audioFile);
                
                audioControls.appendChild(playBtn);
                metaDiv.appendChild(audioControls);
            }
            
            contentDiv.appendChild(metaDiv);
        }
        
        messageDiv.appendChild(contentDiv);
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    async playAudio(audioFile) {
        try {
            const audio = new Audio(`${this.apiBase}/audio/${audioFile}`);
            audio.play();
        } catch (error) {
            console.error('Audio playback error:', error);
        }
    }

    setLoading(loading) {
        this.isLoading = loading;
        this.sendBtn.disabled = loading || !this.messageInput.value.trim();
        this.micBtn.disabled = loading;
        this.messageInput.disabled = loading;
        
        if (loading) {
            const loadingDiv = document.createElement('div');
            loadingDiv.className = 'message assistant';
            loadingDiv.id = 'loading-message';
            
            const contentDiv = document.createElement('div');
            contentDiv.className = 'message-content';
            
            const loadingContent = document.createElement('div');
            loadingContent.className = 'loading';
            loadingContent.innerHTML = '<div class="spinner"></div> Thinking...';
            
            contentDiv.appendChild(loadingContent);
            loadingDiv.appendChild(contentDiv);
            this.messagesContainer.appendChild(loadingDiv);
            this.scrollToBottom();
        } else {
            const loadingMsg = document.getElementById('loading-message');
            if (loadingMsg) {
                loadingMsg.remove();
            }
        }
    }

    scrollToBottom() {
        this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new OpenChat();
});