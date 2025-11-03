class OpenChat {
    constructor() {
        this.apiBase = window.location.origin;
        this.isRecording = false;
        this.mediaRecorder = null;
        this.audioChunks = [];
        this.isLoading = false;
        this.isGenerating = false;
        
        // Audio playback management
        this.currentAudio = null;
        this.currentPlayButton = null;
        
        this.initializeElements();
        this.bindEvents();
        this.checkHealth();
        this.loadVoices();
        this.loadModels();
        this.loadConversationHistory();
        this.loadConversationStats();
        this.checkComfyUIStatus();
    }

    initializeElements() {
        // UI elements
        this.messagesContainer = document.getElementById('messages');
        this.messageInput = document.getElementById('message-input');
        this.sendBtn = document.getElementById('send-btn');
        this.micBtn = document.getElementById('mic-btn');
        this.modelSelect = document.getElementById('model-select');
        this.ttsSelect = document.getElementById('tts-select');
        this.voiceSelect = document.getElementById('voice-select');
        
        // Image upload elements
        this.imageBtn = document.getElementById('image-btn');
        this.imageInput = document.getElementById('image-input');
        this.imagePreview = document.getElementById('image-preview');
        this.imagePreviewContainer = document.getElementById('image-preview-container');
        this.removeImageBtn = document.getElementById('remove-image');
        
        // Current image data
        this.currentImageFile = null;
        
        // Status indicators
        this.ollamaStatus = document.getElementById('ollama-status');
        this.ttsStatus = document.getElementById('tts-status');
        this.sttStatus = document.getElementById('stt-status');
        this.ttsProvider = document.getElementById('tts-provider');
        
        // Conversation controls
        this.loadHistoryBtn = document.getElementById('load-history-btn');
        this.clearHistoryBtn = document.getElementById('clear-history-btn');
        this.conversationStats = document.getElementById('conversation-stats');
        
        // RAG controls
        this.ragSection = document.getElementById('rag-section');
        this.ragStatus = document.getElementById('rag-status');
        this.ragStats = document.getElementById('rag-stats');
        this.fileInput = document.getElementById('file-input');
        this.fileDropZone = document.getElementById('file-drop-zone');
        this.uploadProgress = document.getElementById('upload-progress');
        this.uploadProgressBar = document.getElementById('upload-progress-bar');
        
        // ComfyUI elements
        this.comfyuiStatus = document.getElementById('comfyui-status');
        this.imagePrompt = document.getElementById('image-prompt');
        this.negativePrompt = document.getElementById('negative-prompt');
        this.imageWidth = document.getElementById('image-width');
        this.imageHeight = document.getElementById('image-height');
        this.imageSteps = document.getElementById('image-steps');
        this.imageCfg = document.getElementById('image-cfg');
        this.generateBtn = document.getElementById('generate-btn');
        this.generationProgress = document.getElementById('generation-progress');
        this.progressFill = document.getElementById('progress-fill');
        this.progressText = document.getElementById('progress-text');
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
        
        // Model selection change handler
        this.modelSelect.addEventListener('change', () => {
            this.updateImageButtonState();
        });

        // Conversation controls
        this.loadHistoryBtn.addEventListener('click', () => this.reloadConversationHistory());
        this.clearHistoryBtn.addEventListener('click', () => this.clearConversationHistory());

        // Image upload controls
        this.imageBtn.addEventListener('click', () => this.imageInput.click());
        this.imageInput.addEventListener('change', () => this.handleImageSelection());
        this.removeImageBtn.addEventListener('click', () => this.removeImage());

        // RAG controls
        this.fileInput.addEventListener('change', () => this.handleFileUpload());
        this.setupDragAndDrop();

        // ComfyUI controls
        this.generateBtn.addEventListener('click', () => this.generateImage());
        this.imagePrompt.addEventListener('input', () => this.updateGenerateButton());

        // Auto-scroll messages
        this.messagesContainer.addEventListener('DOMNodeInserted', () => {
            this.scrollToBottom();
        });
    }

    setupDragAndDrop() {
        // Click to browse
        this.fileDropZone.addEventListener('click', () => {
            this.fileInput.click();
        });

        // Drag and drop events
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            this.fileDropZone.addEventListener(eventName, this.preventDefaults, false);
        });

        ['dragenter', 'dragover'].forEach(eventName => {
            this.fileDropZone.addEventListener(eventName, () => {
                this.fileDropZone.classList.add('drag-over');
            }, false);
        });

        ['dragleave', 'drop'].forEach(eventName => {
            this.fileDropZone.addEventListener(eventName, () => {
                this.fileDropZone.classList.remove('drag-over');
            }, false);
        });

        this.fileDropZone.addEventListener('drop', (e) => {
            const files = e.dataTransfer.files;
            this.handleFileUpload(files);
        }, false);
    }

    preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
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
            
            // Add models with vision indicators
            if (data.models_with_info) {
                data.models_with_info.forEach(modelInfo => {
                    const option = document.createElement('option');
                    option.value = modelInfo.name;
                    option.textContent = modelInfo.name + (modelInfo.supports_vision ? ' 👁️' : '');
                    option.dataset.supportsVision = modelInfo.supports_vision;
                    this.modelSelect.appendChild(option);
                });
            } else {
                // Fallback to simple list
                data.models.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model;
                    option.textContent = model;
                    this.modelSelect.appendChild(option);
                });
            }
            
            // Set default model
            if (data.models && data.models.length > 0) {
                this.modelSelect.value = data.models[0];
            }
            
            // Update image button availability
            this.updateImageButtonState();
            
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

        // Check if we have an image
        const hasImage = this.currentImageFile !== null;
        
        // Add user message to UI (with image if present)
        this.addMessage(message, 'user', null, null, false, this.currentImageFile);

        try {
            let response;
            
            if (hasImage) {
                // Use vision endpoint with FormData
                const formData = new FormData();
                formData.append('message', message);
                formData.append('model', this.modelSelect.value);
                formData.append('voice_id', this.voiceSelect.value);
                formData.append('image', this.currentImageFile);
                
                response = await fetch(`${this.apiBase}/chat-vision`, {
                    method: 'POST',
                    body: formData
                });
            } else {
                // Use regular text endpoint
                response = await fetch(`${this.apiBase}/chat`, {
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
            }

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
            
            // Clear image after successful send
            if (hasImage) {
                this.removeImage();
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
            // Check if getUserMedia is supported
            if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
                throw new Error('getUserMedia is not supported in this browser');
            }

            console.log('Requesting microphone access...');
            const stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                    sampleRate: 44100
                } 
            });
            
            console.log('Microphone access granted, stream tracks:', stream.getTracks().length);
            
            this.audioChunks = [];
            
            // Check supported MIME types and use the best available
            let mimeType = 'audio/webm';
            if (!MediaRecorder.isTypeSupported('audio/webm')) {
                if (MediaRecorder.isTypeSupported('audio/mp4')) {
                    mimeType = 'audio/mp4';
                } else if (MediaRecorder.isTypeSupported('audio/wav')) {
                    mimeType = 'audio/wav';
                } else {
                    console.warn('No preferred audio format supported, using default');
                    mimeType = '';
                }
            }
            
            console.log('Using MIME type:', mimeType);
            
            this.mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});
            
            this.mediaRecorder.ondataavailable = (event) => {
                console.log('Audio data chunk received:', event.data.size, 'bytes');
                if (event.data.size > 0) {
                    this.audioChunks.push(event.data);
                }
            };
            
            this.mediaRecorder.onstop = () => {
                console.log('Recording stopped, processing...');
                this.processRecording();
                stream.getTracks().forEach(track => track.stop());
            };
            
            this.mediaRecorder.onerror = (event) => {
                console.error('MediaRecorder error:', event.error);
            };
            
            this.mediaRecorder.start(1000); // Collect data every second
            this.isRecording = true;
            this.micBtn.classList.add('recording');
            this.micBtn.title = 'Click to stop recording';
            
            console.log('Recording started successfully');
            
        } catch (error) {
            console.error('Failed to start recording:', error);
            let errorMessage = 'Microphone access failed. ';
            
            if (error.name === 'NotAllowedError') {
                errorMessage += 'Please allow microphone access and try again.';
            } else if (error.name === 'NotFoundError') {
                errorMessage += 'No microphone found. Please connect a microphone.';
            } else if (error.name === 'NotSupportedError') {
                errorMessage += 'Microphone not supported in this browser.';
            } else {
                errorMessage += error.message;
            }
            
            alert(errorMessage);
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
        if (this.audioChunks.length === 0) {
            console.warn('No audio chunks to process');
            return;
        }

        console.log('Processing', this.audioChunks.length, 'audio chunks');
        this.setLoading(true);
        
        try {
            const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
            console.log('Created audio blob:', audioBlob.size, 'bytes, type:', audioBlob.type);
            
            if (audioBlob.size === 0) {
                throw new Error('Audio recording is empty');
            }
            
            const formData = new FormData();
            formData.append('audio', audioBlob, 'recording.webm');

            console.log('Sending audio to server for transcription...');
            const response = await fetch(`${this.apiBase}/transcribe`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`HTTP ${response.status}: ${errorText}`);
            }

            const data = await response.json();
            console.log('Transcription response:', data);
            
            if (data.text && data.text.trim()) {
                console.log('Transcribed text:', data.text);
                this.messageInput.value = data.text;
                this.sendMessage();
            } else {
                console.warn('No speech detected in transcription');
                alert('No speech detected. Please try speaking more clearly or check your microphone.');
            }

        } catch (error) {
            console.error('Transcription error:', error);
            alert(`Failed to transcribe audio: ${error.message}`);
        } finally {
            this.setLoading(false);
        }
    }

    addMessage(content, role, audioFile = null, timestamp = null, isError = false, imageFile = null) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${role}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = `message-content ${isError ? 'error' : ''}`;
        
        // Add image if provided (for user messages)
        if (imageFile && role === 'user') {
            const imageDiv = document.createElement('div');
            const img = document.createElement('img');
            img.className = 'message-image';
            img.src = URL.createObjectURL(imageFile);
            img.alt = 'Uploaded image';
            img.onclick = () => window.open(img.src, '_blank');
            imageDiv.appendChild(img);
            contentDiv.appendChild(imageDiv);
        }
        
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
                playBtn.dataset.audioFile = audioFile;
                playBtn.onclick = (e) => this.toggleAudio(audioFile, e.target);
                
                const stopBtn = document.createElement('button');
                stopBtn.className = 'stop-btn';
                stopBtn.innerHTML = '⏹️';
                stopBtn.title = 'Stop audio';
                stopBtn.style.display = 'none';
                stopBtn.onclick = () => this.stopAudio();
                
                audioControls.appendChild(playBtn);
                audioControls.appendChild(stopBtn);
                metaDiv.appendChild(audioControls);
            }
            
            contentDiv.appendChild(metaDiv);
        }
        
        messageDiv.appendChild(contentDiv);
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    async toggleAudio(audioFile, buttonElement) {
        try {
            // If audio is currently playing, stop it
            if (this.currentAudio && !this.currentAudio.paused) {
                this.stopAudio();
                
                // If clicking the same button, just stop
                if (this.currentPlayButton === buttonElement) {
                    return;
                }
            }
            
            // Play new audio
            await this.playAudio(audioFile, buttonElement);
            
        } catch (error) {
            console.error('Audio toggle error:', error);
        }
    }

    async playAudio(audioFile, buttonElement = null) {
        try {
            // Stop any currently playing audio
            this.stopAudio();
            
            console.log('Playing audio:', audioFile);
            this.currentAudio = new Audio(`${this.apiBase}/audio/${audioFile}`);
            this.currentPlayButton = buttonElement;
            
            // Update button state
            if (buttonElement) {
                buttonElement.innerHTML = '⏸️';
                buttonElement.title = 'Pause audio';
                
                // Show stop button
                const stopBtn = buttonElement.parentElement.querySelector('.stop-btn');
                if (stopBtn) {
                    stopBtn.style.display = 'inline-block';
                }
            }
            
            // Set up event listeners
            this.currentAudio.onended = () => {
                this.resetAudioControls();
            };
            
            this.currentAudio.onerror = (e) => {
                console.error('Audio playback error:', e);
                this.resetAudioControls();
            };
            
            // Play the audio
            await this.currentAudio.play();
            
        } catch (error) {
            console.error('Audio playback error:', error);
            this.resetAudioControls();
        }
    }

    stopAudio() {
        if (this.currentAudio) {
            this.currentAudio.pause();
            this.currentAudio.currentTime = 0;
            this.currentAudio = null;
        }
        this.resetAudioControls();
    }

    resetAudioControls() {
        if (this.currentPlayButton) {
            this.currentPlayButton.innerHTML = '🔊';
            this.currentPlayButton.title = 'Play audio';
            
            // Hide stop button
            const stopBtn = this.currentPlayButton.parentElement.querySelector('.stop-btn');
            if (stopBtn) {
                stopBtn.style.display = 'none';
            }
        }
        this.currentPlayButton = null;
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

    async loadConversationStats() {
        try {
            const response = await fetch(`${this.apiBase}/conversations/stats`);
            const stats = await response.json();
            
            let statsText = `Messages: ${stats.total_messages} (${stats.user_messages} user, ${stats.assistant_messages} assistant)`;
            if (stats.oldest_message) {
                const oldestDate = new Date(stats.oldest_message);
                statsText += ` • Since: ${oldestDate.toLocaleDateString()}`;
            }
            
            this.conversationStats.textContent = statsText;
            
        } catch (error) {
            console.error('Failed to load conversation stats:', error);
            this.conversationStats.textContent = 'Stats unavailable';
        }
    }

    async reloadConversationHistory() {
        this.loadHistoryBtn.disabled = true;
        this.loadHistoryBtn.textContent = '🔄 Loading...';
        
        try {
            await this.loadConversationHistory();
            await this.loadConversationStats();
            
            // Show success feedback
            this.loadHistoryBtn.textContent = '✅ Reloaded';
            setTimeout(() => {
                this.loadHistoryBtn.textContent = '🔄 Reload History';
                this.loadHistoryBtn.disabled = false;
            }, 2000);
            
        } catch (error) {
            console.error('Failed to reload conversation history:', error);
            alert('Failed to reload conversation history');
            this.loadHistoryBtn.textContent = '🔄 Reload History';
            this.loadHistoryBtn.disabled = false;
        }
    }

    async clearConversationHistory() {
        const confirmed = confirm(
            'Are you sure you want to clear all conversation history? This cannot be undone.'
        );
        
        if (!confirmed) return;
        
        this.clearHistoryBtn.disabled = true;
        this.clearHistoryBtn.textContent = '🗑️ Clearing...';
        
        try {
            const response = await fetch(`${this.apiBase}/conversations`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            // Clear the messages container except welcome message
            const welcomeMessage = this.messagesContainer.querySelector('.message.assistant');
            this.messagesContainer.innerHTML = '';
            if (welcomeMessage) {
                this.messagesContainer.appendChild(welcomeMessage);
            }
            
            // Update stats
            await this.loadConversationStats();
            
            // Show success feedback
            this.clearHistoryBtn.textContent = '✅ Cleared';
            setTimeout(() => {
                this.clearHistoryBtn.textContent = '🗑️ Clear History';
                this.clearHistoryBtn.disabled = false;
            }, 2000);
            
        } catch (error) {
            console.error('Failed to clear conversation history:', error);
            alert('Failed to clear conversation history');
            this.clearHistoryBtn.textContent = '🗑️ Clear History';
            this.clearHistoryBtn.disabled = false;
        }
    }

    async checkRAGStatus() {
        try {
            const response = await fetch(`${this.apiBase}/rag/stats`);
            const stats = await response.json();
            
            if (stats.enabled) {
                this.ragStatus.textContent = 'Enabled';
                this.ragStatus.classList.add('enabled');
                this.updateRAGStats(stats);
            } else {
                this.ragStatus.textContent = 'Disabled';
                this.ragStats.textContent = 'RAG service not available';
            }
            
        } catch (error) {
            console.error('Failed to check RAG status:', error);
            this.ragStatus.textContent = 'Error';
            this.ragStats.textContent = 'Unable to connect to RAG service';
        }
    }

    updateRAGStats(stats) {
        const documents = stats.unique_documents || 0;
        const chunks = stats.total_chunks || 0;
        const coverage = Math.round((stats.embedding_coverage || 0) * 100);
        
        this.ragStats.textContent = `${documents} documents, ${chunks} chunks, ${coverage}% embedded`;
    }

    async handleFileUpload(droppedFiles = null) {
        const files = droppedFiles || this.fileInput.files;
        if (!files || files.length === 0) return;
        
        // Update UI
        this.showUploadProgress();
        
        try {
            // Upload files one by one
            for (let i = 0; i < files.length; i++) {
                const file = files[i];
                console.log(`Uploading file ${i + 1}/${files.length}:`, file.name);
                
                // Update progress
                const progress = ((i / files.length) * 100);
                this.updateUploadProgress(progress, `Uploading ${file.name}...`);
                
                await this.uploadSingleFile(file);
            }
            
            // Complete
            this.updateUploadProgress(100, 'Upload complete!');
            
            // Update stats
            await this.checkRAGStatus();
            
            // Reset file input
            this.fileInput.value = '';
            
            // Hide progress after a moment
            setTimeout(() => {
                this.hideUploadProgress();
            }, 2000);
            
        } catch (error) {
            console.error('Upload error:', error);
            this.updateUploadProgress(0, `Upload failed: ${error.message}`);
            
            setTimeout(() => {
                this.hideUploadProgress();
            }, 3000);
        }
    }

    async uploadSingleFile(file) {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${this.apiBase}/rag/upload`, {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Upload failed');
        }
        
        const result = await response.json();
        
        // Add system message about upload
        this.addMessage(
            `📚 Document "${file.name}" has been added to my knowledge base. I can now answer questions based on its content!`,
            'assistant',
            null,
            new Date()
        );
        
        return result;
    }

    showUploadProgress() {
        this.uploadProgress.style.display = 'block';
        this.fileDropZone.querySelector('.drop-text').textContent = 'Uploading...';
    }

    updateUploadProgress(percent, message = '') {
        this.uploadProgressBar.style.width = `${percent}%`;
        if (message) {
            this.fileDropZone.querySelector('.drop-hint').textContent = message;
        }
    }

    hideUploadProgress() {
        this.uploadProgress.style.display = 'none';
        this.uploadProgressBar.style.width = '0%';
        this.fileDropZone.querySelector('.drop-text').textContent = 'Drag & drop documents here';
        this.fileDropZone.querySelector('.drop-hint').textContent = 'or click to browse (.txt, .md, .pdf, .docx)';
    }

    // Image handling methods
    handleImageSelection() {
        const file = this.imageInput.files[0];
        if (!file) return;

        // Validate file type
        if (!file.type.startsWith('image/')) {
            alert('Please select a valid image file.');
            return;
        }

        // Check file size (max 10MB)
        if (file.size > 10 * 1024 * 1024) {
            alert('Image file too large. Please select an image under 10MB.');
            return;
        }

        this.currentImageFile = file;
        
        // Show preview
        const reader = new FileReader();
        reader.onload = (e) => {
            this.imagePreview.src = e.target.result;
            this.imagePreviewContainer.classList.add('show');
            this.updateImageButtonState();
        };
        reader.readAsDataURL(file);
    }

    removeImage() {
        this.currentImageFile = null;
        this.imageInput.value = '';
        this.imagePreviewContainer.classList.remove('show');
        this.imagePreview.src = '';
        this.updateImageButtonState();
    }

    updateImageButtonState() {
        const selectedOption = this.modelSelect.selectedOptions[0];
        const supportsVision = selectedOption && selectedOption.dataset.supportsVision === 'true';
        
        if (supportsVision) {
            this.imageBtn.disabled = false;
            this.imageBtn.title = 'Upload image for AI analysis';
        } else {
            this.imageBtn.disabled = true;
            this.imageBtn.title = 'Select a vision model to upload images';
            
            // Remove current image if model doesn't support vision
            if (this.currentImageFile) {
                this.removeImage();
            }
        }
    }

    // ComfyUI Integration Methods
    async checkComfyUIStatus() {
        try {
            const response = await fetch(`${this.apiBase}/comfyui/status`);
            const status = await response.json();
            
            this.updateComfyUIStatus(status.connected, status.system_info);
            this.updateGenerateButton();
        } catch (error) {
            console.error('Error checking ComfyUI status:', error);
            this.updateComfyUIStatus(false);
        }
    }

    updateComfyUIStatus(connected, systemInfo = null) {
        if (connected) {
            this.comfyuiStatus.textContent = 'Connected';
            this.comfyuiStatus.classList.add('connected');
            
            if (systemInfo) {
                const version = systemInfo.comfyui_version || 'Unknown';
                this.comfyuiStatus.title = `ComfyUI v${version} - Ready for image generation`;
            }
        } else {
            this.comfyuiStatus.textContent = 'Disconnected';
            this.comfyuiStatus.classList.remove('connected');
            this.comfyuiStatus.title = 'ComfyUI not available';
        }
    }

    updateGenerateButton() {
        const hasPrompt = this.imagePrompt.value.trim().length > 0;
        const isConnected = this.comfyuiStatus.classList.contains('connected');
        
        this.generateBtn.disabled = !hasPrompt || !isConnected || this.isGenerating;
    }

    async generateImage() {
        if (this.isGenerating) return;
        
        const prompt = this.imagePrompt.value.trim();
        if (!prompt) {
            alert('Please enter a prompt for image generation');
            return;
        }

        this.isGenerating = true;
        this.showGenerationProgress();
        this.updateGenerateButton();

        try {
            const formData = new FormData();
            formData.append('prompt', prompt);
            formData.append('negative_prompt', this.negativePrompt.value.trim());
            formData.append('width', this.imageWidth.value);
            formData.append('height', this.imageHeight.value);
            formData.append('steps', this.imageSteps.value);
            formData.append('cfg', this.imageCfg.value);

            this.updateProgress(0, 'Preparing generation...');

            const response = await fetch(`${this.apiBase}/comfyui/generate`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`Generation failed: ${response.statusText}`);
            }

            this.updateProgress(50, 'Processing...');

            const result = await response.json();

            if (result.success) {
                this.updateProgress(100, 'Complete!');
                
                // Add generated image to chat
                this.addGeneratedImageToChat(result.image_filename, prompt);
                
                // Clear the prompt
                this.imagePrompt.value = '';
                
                setTimeout(() => {
                    this.hideGenerationProgress();
                }, 2000);
            } else {
                throw new Error('Generation failed');
            }

        } catch (error) {
            console.error('Error generating image:', error);
            this.updateProgress(0, 'Generation failed');
            alert(`Error generating image: ${error.message}`);
            
            setTimeout(() => {
                this.hideGenerationProgress();
            }, 3000);
        } finally {
            this.isGenerating = false;
            this.updateGenerateButton();
        }
    }

    showGenerationProgress() {
        this.generationProgress.style.display = 'block';
        this.generateBtn.querySelector('.btn-text').style.display = 'none';
        this.generateBtn.querySelector('.btn-spinner').style.display = 'inline';
    }

    hideGenerationProgress() {
        this.generationProgress.style.display = 'none';
        this.generateBtn.querySelector('.btn-text').style.display = 'inline';
        this.generateBtn.querySelector('.btn-spinner').style.display = 'none';
    }

    updateProgress(percentage, text) {
        this.progressFill.style.width = `${percentage}%`;
        this.progressText.textContent = text;
    }

    addGeneratedImageToChat(imageFilename, prompt) {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'message assistant';
        
        const timestamp = new Date().toLocaleTimeString();
        
        messageDiv.innerHTML = `
            <div class="message-content">
                <div class="message-text">🎨 Generated image: "${prompt}"</div>
                <div class="message-image">
                    <img src="${this.apiBase}/images/${imageFilename}" alt="Generated image" style="max-width: 400px; border-radius: 8px; margin-top: 0.5rem;">
                </div>
                <div class="message-timestamp">${timestamp}</div>
                <div class="message-actions">
                    <button class="action-btn" onclick="this.downloadImage('${imageFilename}')">
                        💾 Download
                    </button>
                </div>
            </div>
        `;
        
        this.messagesContainer.appendChild(messageDiv);
        this.scrollToBottom();
    }

    downloadImage(filename) {
        const link = document.createElement('a');
        link.href = `${this.apiBase}/images/${filename}`;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
    }
}

// Initialize the application when the page loads
document.addEventListener('DOMContentLoaded', () => {
    new OpenChat();
});