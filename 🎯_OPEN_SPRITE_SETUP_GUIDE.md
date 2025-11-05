🎯 OPEN SPRITE DESKTOP AI COMPANION - NETWORK SETUP GUIDE 🎯
═══════════════════════════════════════════════════════════════════

📍 SYSTEM ARCHITECTURE:
┌─────────────────────────────────────────────────────────────────┐
│  Mac Mini M1 (192.168.0.12)    ←→    Windows "Oasis" (192.168.0.45)  │
│  ├─ Electron Desktop App              ├─ WSL Ubuntu                    │
│  ├─ Nyra Overlay Component            ├─ OpenChat Backend             │
│  ├─ WebSocket Client                  ├─ FastAPI Server :8000         │
│  └─ Audio Services                    └─ RTX 3060 GPU + Ollama        │
└─────────────────────────────────────────────────────────────────┘

🔗 NETWORK CONNECTION FLOW:
Mac Mini → SSH (port 2222) → Windows Oasis → WSL Ubuntu → Backend (port 8000)

📋 CONNECTION DETAILS:
┌─────────────────────────────────────────────────────────────────┐
│ • Windows Machine: "Oasis" at 192.168.0.45                     │
│ • SSH Port Forward: 2222 → WSL                                 │
│ • WSL Internal IP: 172.18.170.88                               │
│ • Backend Port: 8000                                           │
│ • Mac Client IP: 192.168.0.12                                  │
└─────────────────────────────────────────────────────────────────┘

🚀 LAUNCH SEQUENCE:

1️⃣ START BACKEND (in WSL via SSH):
   cd /home/tkash/wsl_dev/open-chat
   source venv/bin/activate
   cd backend
   python main.py
   ✅ Should show: "Uvicorn running on http://0.0.0.0:8000"

2️⃣ TEST BACKEND (from WSL):
   curl http://localhost:8000/health
   ✅ Should return: {"status":"healthy","timestamp":"..."}

3️⃣ SETUP PORT FORWARDING (Windows PowerShell as Admin):
   netsh interface portproxy add v4tov4 listenport=8000 listenaddress=192.168.0.45 connectport=8000 connectaddress=172.18.170.88
   
   OR for SSH Port Forwarding (Mac Terminal):
   ssh -L 8000:localhost:8000 tkash@192.168.0.45 -p 2222

4️⃣ TEST FROM MAC MINI:
   curl http://localhost:8000/health        # If using SSH port forwarding
   curl http://192.168.0.45:8000/health     # If using Windows port forwarding
   curl http://172.18.170.88:8000/health    # Direct WSL IP (if accessible)

5️⃣ LAUNCH ELECTRON APP (Mac Mini):
   git clone https://github.com/xdrabbit/open-sprite.git
   cd open-sprite
   npm install
   npm run dev

🎯 EXPECTED BEHAVIOR:
├─ 🖥️ Desktop overlay appears in bottom-left corner of Mac screen
├─ 🔗 WebSocket connects to backend (watch terminal for connection logs)
├─ 😊 Nyra sprite shows emotions based on AI conversation context
├─ 🎵 Audio visualization for system-wide lip-sync
└─ 💬 Click sprite to open OpenChat interface in browser

🔧 TROUBLESHOOTING:
┌─────────────────────────────────────────────────────────────────┐
│ CONNECTION ISSUES:                                              │
│ 1. Check if backend is running: ps aux | grep python           │
│ 2. Test WSL connectivity: curl http://172.18.170.88:8000/health│
│ 3. Verify port forwarding: netsh interface portproxy show v4tov4│
│ 4. Check Windows firewall for port 8000                        │
│                                                                 │
│ ELECTRON APP ISSUES:                                            │
│ 1. Check if dependencies installed: npm list                   │
│ 2. Verify network config in src/config/network.ts             │
│ 3. Open developer tools in Electron for console errors        │
│                                                                 │
│ SSH ISSUES:                                                     │
│ 1. Ensure SSH connection is active with port forwarding        │
│ 2. Test: ssh -L 8000:localhost:8000 tkash@192.168.0.45 -p 2222│
└─────────────────────────────────────────────────────────────────┘

📂 REPOSITORY LOCATIONS:
├─ Backend: /home/tkash/wsl_dev/open-chat (WSL)
├─ Desktop App: https://github.com/xdrabbit/open-sprite.git (Mac)
└─ Nyra Components: /home/tkash/wsl_dev/open-chat/nyra-desktop/ (WSL)

🎨 CONFIGURATION FILES:
├─ Network Config: src/config/network.ts
├─ WebSocket Service: src/services/WebSocketService.ts
├─ Audio Service: src/services/AudioService.ts
└─ Main Component: src/components/NyraDesktopOverlay.tsx

💡 PRO TIPS:
├─ Keep SSH connection alive for port forwarding
├─ Use localhost:8000 on Mac if SSH port forwarding works
├─ Check 'netstat -an | grep 8000' to verify port binding
└─ Monitor backend logs for WebSocket connection attempts

🔥 LAUNCH COMMANDS SUMMARY:
┌─────────────────────────────────────────────────────────────────┐
│ WSL (Backend):                                                  │
│ cd /home/tkash/wsl_dev/open-chat && source venv/bin/activate && │
│ cd backend && python main.py                                    │
│                                                                 │
│ Mac (Frontend):                                                 │
│ git clone https://github.com/xdrabbit/open-sprite.git &&       │
│ cd open-sprite && npm install && npm run dev                   │
└─────────────────────────────────────────────────────────────────┘

🎯 SUCCESS INDICATORS:
✅ Backend: "Uvicorn running on http://0.0.0.0:8000"
✅ Health Check: {"status":"healthy","timestamp":"..."}
✅ Electron: Nyra sprite visible in bottom-left corner
✅ WebSocket: Connection established (check browser dev tools)
✅ Audio: Microphone permission granted for lip-sync

═══════════════════════════════════════════════════════════════════
🚀 READY TO LAUNCH REVOLUTIONARY DESKTOP AI COMPANION! 🚀
═══════════════════════════════════════════════════════════════════