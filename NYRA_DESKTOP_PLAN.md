# 🤖 Nyra Desktop Companion - Electron App

## Overview
Desktop AI companion that floats on your screen like Rainmeter, providing system-wide AI assistance with personality!

## Architecture

```
┌─────────────────────────────────────────┐
│ 🖥️  DESKTOP (Any App Running)           │
│                                         │
│  ┌─ VS Code ─┐  ┌─ Browser ─┐          │
│  │           │  │           │          │
│  │   Code    │  │   Web     │          │
│  │           │  │           │          │
│  └───────────┘  └───────────┘          │
│                                         │
│                           🤖 Nyra      │
│                          (Always       │
│                           On Top)      │
└─────────────────────────────────────────┘
```

## Technical Stack

- **Electron**: Desktop app framework
- **React + TypeScript**: UI (reusing Nyra Sprite components)
- **WebSocket**: Real-time connection to OpenChat backend
- **System Audio API**: For system-wide lip-sync
- **Always-on-top**: Desktop overlay functionality

## Features

### Core Companion Features
- 🎭 **Always Visible**: Floats above all applications
- 🗣️ **System-wide Lip-sync**: Reacts to any TTS/audio
- 🎨 **Emotion System**: Changes based on AI conversation context
- 📱 **Minimal Footprint**: Small, unobtrusive presence
- 🔗 **Live Backend Connection**: Real-time OpenChat integration

### Advanced Features (Future)
- 📊 **System Monitoring**: React to CPU/memory usage
- 📧 **Notification Integration**: Respond to system notifications
- 🎮 **Context Awareness**: Different behavior based on active app
- 🌟 **Idle Animations**: Subtle movements when system is quiet
- 🎵 **Music Sync**: Dance to system audio/music

## Implementation Plan

### Phase 1: Foundation
1. **Electron App Setup**
   - Basic window with transparency
   - Always-on-top configuration
   - System tray integration

2. **Nyra Integration**
   - Port Nyra Sprite React components
   - Basic animation system
   - Positioning in bottom-left

### Phase 2: Connectivity
3. **WebSocket Client**
   - Connect to OpenChat backend
   - Real-time message handling
   - Status synchronization

4. **Audio Integration**
   - System audio capture
   - Lip-sync engine
   - Voice activity detection

### Phase 3: Intelligence
5. **Emotion System**
   - Context-aware reactions
   - Conversation state tracking
   - Image generation celebrations

6. **Advanced Behaviors**
   - Idle state management
   - System event reactions
   - Personality expressions

## File Structure

```
nyra-desktop/
├── package.json
├── electron/
│   ├── main.js          # Electron main process
│   ├── preload.js       # Secure context bridge
│   └── window-config.js # Window settings
├── src/
│   ├── components/
│   │   ├── NyraSprite/  # Ported from nyra-sprite
│   │   ├── Overlay/     # Desktop overlay logic
│   │   └── Audio/       # System audio handling
│   ├── services/
│   │   ├── websocket.ts # OpenChat connection
│   │   ├── audio.ts     # System audio capture
│   │   └── emotions.ts  # Emotion management
│   └── App.tsx          # Main overlay component
└── dist/                # Built application
```

## Development Workflow

1. **Backend**: OpenChat API server (port 8000)
2. **Desktop App**: Electron dev server
3. **Live Reload**: Changes update overlay in real-time
4. **Cross-Platform**: Build for Windows, Mac, Linux

## User Experience

### Daily Usage
- Nyra appears when you start your computer
- Sits quietly in bottom-left corner
- Comes alive when you use OpenChat
- Reacts to AI conversations with emotions
- Celebrates when images are generated
- Provides subtle presence throughout workday

### Interaction Methods
- **Passive**: Just watches and reacts
- **Click**: Opens OpenChat web interface
- **Context Menu**: Settings, hide/show, quit
- **Hotkey**: Quick AI query without opening full interface

## Technical Considerations

### Performance
- **Minimal Resource Usage**: Efficient rendering
- **GPU Acceleration**: Smooth animations
- **Memory Management**: Clean up unused assets
- **Background Efficiency**: Low CPU when idle

### Security
- **Sandboxed Renderer**: Secure Electron configuration
- **HTTPS/WSS**: Encrypted backend communication
- **Local Data**: No sensitive data storage
- **Permission Management**: Audio access consent

### Platform Support
- **Windows**: Native overlay support
- **macOS**: Dock integration
- **Linux**: X11/Wayland compatibility
- **Multi-Monitor**: Proper positioning across screens

This will be the ultimate AI companion experience! 🚀✨