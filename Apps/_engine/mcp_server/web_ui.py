"""Self-contained HTML/CSS/JS for the MCP Server chat UI.

Returns a single HTML string with everything inlined (zero external deps).
"""

from __future__ import annotations


def get_index_html() -> str:
    return _HTML


_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>EnneaDuck</title>
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --duck-icon: url('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAyCAYAAAAeP4ixAAAACXBIWXMAAAsTAAALEwEAmpwYAAAEGUlEQVR4nO2abWiWVRjHf3O4qfNdKk2coh/MhiEpS0UNdKlRgiRiICUWrPRDgR80QVFzU4dSqOiUpYJFWSQo+YbRFxF7Mc0otyhXKurA+YZvmzY3ueB/w+HhvrfnZc/znIF/OPBs17nPfV3POdfb/zzwBEljGPAp8CdwV6Ma2Ay8QAfBIuAh0BIx/gfKgBw8xgdSthn4DHgJKAC6ASOBCuCB5mzEUwyWkmbEW63MK3GMmY+HqJByX8Qx90PNbQRexjP8JuXCFFsjhy/X3+YfX2l+E3BIsiXAOuAb4BxwHViYYTu4JcV6hsjuSHbb+V9nRbGmVgJDi4zJKBr04vwQWbmMsWgVi0HAPGCZdsN2ZQ6wU+tZCM8o/tWLh6e4TidgMfBIgeN1MozdMsSUSAYFwJvA704It5yUcbwiBS5HHC8X3YExwNs6bvuB+45fnAdmkkX8IkXei5DnAZUKu7FObUfpmKJUW19E2jFLSpm/5IbIzZmDkPsHsFc7YkdqAB7BlP9Pyk4LkV+QbCwdAB9J2a0hsqA06UoHQLGUPRMiq5PMCkjv0U/K1ofIvpVsFR0AeVLWjlEsJjtlR188x2ApeyVCfkLyz/EcpVL0uwj5804emY2nsIr2LylpWTsKizTnlvp777BGCv4jo6KQA+zT3J/bmJuVI9WsrD0xjvl9gIsyJmi4sgoru1fKCBsLEnh2kmosY12eI4swjuonh+Z5P4k1qvT8QbIAK/DWO/zVZbEjyeAp9fPNmXT8MYr/Qc30SPxVqsltl9ZbTRqz9BTgE+Bvp3ewnfgSGNVO75mude2YJu2oFj2GAi8CU8U5VWnRuzHNT50izEDaF0O0/o1EH7QO7lobNEzQN58CPlZVa4anA/nOTieEoJxu0Oca4EfgMLBJOWFcBEeVDvR3djwuTFBfHDhrbRq/5UTwqvQ5Hu8Dl5xjY8Z87wm9X5lon3JSD1hhNxo/8KyOuIXyokSiQ7XDZOzKcvWZCxyQPl8n+rBduqx1/MRKiz06p2EUTrqQKxLbdLiqhiwp2IPbHIOCrm69rgby01zi/OCEXCseU0ahSgM3ENi4BxwFlgLjgR7t8C47xlu0tr3jZgT/lfJWl+huL2DWY8d55RrbtXdUCRi184wqhOBo9pITF+sabjtwVgm2RWOfrhTSjhHAu7qnqIlRItlhJc9uGZg1dFfIniu+tt7heWtF8TQ4vbhl6V/F7y4XW98FD3FcSsfT1nqN0zKkWBXCTe1CrWQnxCyuUHXtJZ5WQm1UXgruRaKGHT8vURZCwvVWfhgqX5qga+fAmA14iAtS7rU25s13DLEO0zsEd+o7gDdEg/YR0Zajz4X6FUTQ98zAQ5SqWo03f1jV7S2KRJEekTNbvx38isEimNVtFrlsjmX5lPEYsW1vW1KM+EgAAAAASUVORK5CYII=');
  --bg-primary: #111114;
  --bg-secondary: #1a1a1f;
  --bg-tertiary: #222228;
  --bg-hover: #2a2a32;
  --bg-input: #1e1e24;
  --text-primary: #e8e8ed;
  --text-secondary: #9e9ea8;
  --text-tertiary: #6e6e78;
  --accent: #5b8def;
  --accent-hover: #7ba4f7;
  --accent-dim: rgba(91, 141, 239, 0.12);
  --accent-glow: rgba(91, 141, 239, 0.25);
  --border: #2a2a32;
  --border-subtle: #222228;
  --msg-user: #1a2a44;
  --msg-assistant: #1a1a1f;
  --code-bg: #141418;
  --success: #4ade80;
  --error: #f87171;
  --warning: #fbbf24;
  --radius-sm: 6px;
  --radius-md: 10px;
  --radius-lg: 16px;
  --radius-xl: 20px;
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 8px 32px rgba(0,0,0,0.5);
  --transition: 0.2s ease;
}

body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
  height: 100vh;
  display: flex;
  overflow: hidden;
}

/* ── Sidebar ── */
.sidebar {
  width: 280px;
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  box-shadow: inset -1px 0 0 var(--border);
  transition: width var(--transition), opacity var(--transition);
  overflow: hidden;
  flex-shrink: 0;
}
.sidebar.collapsed { width: 0; opacity: 0; pointer-events: none; }

.sidebar-header {
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.sidebar-logo {
  width: 32px;
  height: 32px;
  background: var(--accent-dim);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}
.sidebar-logo img {
  width: 24px;
  height: 24px;
  filter: invert(0.7) sepia(0.3) saturate(3) hue-rotate(190deg);
}
.sidebar-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.sidebar-subtitle {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 1px;
}

.sidebar-section {
  padding: 0 12px;
  margin-bottom: 8px;
}
.sidebar-section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-tertiary);
  padding: 8px 8px 6px;
}

.sidebar-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  color: var(--text-secondary);
  cursor: default;
  transition: background var(--transition);
}
.sidebar-item:hover { background: var(--bg-hover); }
.sidebar-item-icon {
  width: 18px;
  text-align: center;
  font-size: 12px;
  flex-shrink: 0;
  opacity: 0.7;
}

.connection-status {
  margin: auto 12px 12px;
  padding: 12px;
  background: var(--bg-tertiary);
  border-radius: var(--radius-md);
}
.connection-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--text-secondary);
}
.status-indicator {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-tertiary);
  flex-shrink: 0;
}
.status-indicator.ok { background: var(--success); box-shadow: 0 0 6px rgba(74, 222, 128, 0.4); }
.status-indicator.err { background: var(--error); }

.tool-count-badge {
  margin-left: auto;
  background: var(--accent-dim);
  color: var(--accent);
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 10px;
}

/* ── Main content ── */
.main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ── Top bar ── */
.topbar {
  height: 52px;
  background: var(--bg-secondary);
  box-shadow: inset 0 -1px 0 var(--border);
  display: flex;
  align-items: center;
  padding: 0 16px;
  gap: 10px;
  flex-shrink: 0;
}
.topbar-toggle {
  width: 32px;
  height: 32px;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--transition), color var(--transition);
}
.topbar-toggle:hover { background: var(--bg-hover); color: var(--text-primary); }
.topbar-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  flex: 1;
}
.provider-select {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 5px 10px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: border-color var(--transition);
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%236e6e78'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 8px center;
  padding-right: 24px;
}
.provider-select:hover { border-color: var(--accent); }
.provider-select:focus { outline: none; border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-dim); }

.topbar-btn {
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 5px 12px;
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
}
.topbar-btn:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--text-tertiary); }

/* ── Auth banner ── */
.auth-banner {
  padding: 14px 20px;
  background: var(--accent-dim);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  font-size: 13px;
  color: var(--text-secondary);
}
.auth-banner-btn {
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 7px 18px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: background var(--transition);
}
.auth-banner-btn:hover { background: var(--accent-hover); }

/* ── Chat area ── */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px 0;
  scroll-behavior: smooth;
  position: relative;
}
.chat-area::-webkit-scrollbar { width: 6px; }
.chat-area::-webkit-scrollbar-track { background: transparent; }
.chat-area::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
.chat-area::-webkit-scrollbar-thumb:hover { background: var(--text-tertiary); }

/* ── Welcome screen ── */
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 40px 20px;
  text-align: center;
  animation: fadeIn 0.4s ease;
}
.welcome-icon {
  width: 64px;
  height: 64px;
  background: var(--accent-dim);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
}
.welcome-icon img {
  filter: invert(0.7) sepia(0.3) saturate(3) hue-rotate(190deg);
}
.welcome h2 {
  font-size: 22px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.welcome p {
  font-size: 14px;
  color: var(--text-secondary);
  max-width: 420px;
  line-height: 1.6;
  margin-bottom: 32px;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  max-width: 540px;
  width: 100%;
}
.suggestion {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  text-align: left;
  cursor: pointer;
  transition: all var(--transition);
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.suggestion:hover {
  background: var(--bg-tertiary);
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent-dim);
  transform: translateY(-1px);
}
.suggestion-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}
.suggestion-desc {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.4;
}

/* ── Messages ── */
.messages {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 20px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.msg-group {
  display: flex;
  gap: 12px;
  padding: 12px 0;
  animation: slideUp 0.25s ease;
}
.msg-group.user { flex-direction: row-reverse; }

.msg-avatar {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 2px;
}
.msg-group.assistant .msg-avatar { background: var(--accent-dim); color: var(--accent); overflow: hidden; }
.msg-group.assistant .msg-avatar img { width: 20px; height: 20px; filter: invert(0.7) sepia(0.3) saturate(3) hue-rotate(190deg); }
.msg-group.user .msg-avatar { background: var(--bg-tertiary); color: var(--text-secondary); }

.msg-content {
  flex: 1;
  min-width: 0;
}
.msg-body {
  font-size: 14px;
  line-height: 1.65;
  color: var(--text-primary);
  word-wrap: break-word;
  overflow-wrap: break-word;
}
.msg-group.user .msg-body {
  background: var(--msg-user);
  padding: 10px 14px;
  border-radius: var(--radius-md) var(--radius-sm) var(--radius-md) var(--radius-md);
  display: inline-block;
  max-width: 100%;
}
.msg-group.user .msg-content { display: flex; flex-direction: column; align-items: flex-end; }

.msg-body strong { color: #fff; font-weight: 600; }
.msg-body a { color: var(--accent); text-decoration: none; }
.msg-body a:hover { text-decoration: underline; }
.msg-body ul, .msg-body ol { padding-left: 20px; margin: 6px 0; }
.msg-body li { margin: 3px 0; }

/* Code blocks */
.code-block {
  position: relative;
  margin: 10px 0;
  background: var(--code-bg);
  border-radius: var(--radius-sm);
  overflow: hidden;
  box-shadow: inset 0 0 0 1px var(--border-subtle);
}
.code-block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: rgba(255,255,255,0.03);
  font-size: 11px;
  color: var(--text-tertiary);
}
.code-copy-btn {
  background: none;
  border: none;
  color: var(--text-tertiary);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
  font-family: inherit;
  transition: all var(--transition);
}
.code-copy-btn:hover { background: var(--bg-hover); color: var(--text-secondary); }
.code-block pre {
  padding: 12px 14px;
  overflow-x: auto;
  font-size: 13px;
  line-height: 1.5;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  color: var(--text-primary);
}
.code-block pre::-webkit-scrollbar { height: 4px; }
.code-block pre::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

.msg-body code {
  background: var(--code-bg);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  box-shadow: inset 0 0 0 1px var(--border-subtle);
}

/* Tool calls */
.tool-call {
  margin: 8px 0;
  background: var(--bg-secondary);
  border-radius: var(--radius-sm);
  overflow: hidden;
  box-shadow: inset 3px 0 0 var(--accent);
}
.tool-call summary {
  cursor: pointer;
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--accent);
  display: flex;
  align-items: center;
  gap: 6px;
  user-select: none;
  transition: background var(--transition);
}
.tool-call summary:hover { background: var(--bg-hover); }
.tool-call summary::marker { content: ''; }
.tool-call summary::before {
  content: '\25B6';
  font-size: 8px;
  transition: transform var(--transition);
  display: inline-block;
}
.tool-call[open] summary::before { transform: rotate(90deg); }
.tool-call-body {
  padding: 10px 12px;
  font-size: 12px;
  font-family: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
  white-space: pre-wrap;
  color: var(--text-tertiary);
  max-height: 240px;
  overflow-y: auto;
  box-shadow: inset 0 1px 0 var(--border-subtle);
}

/* Thinking indicator */
.thinking-msg {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  animation: fadeIn 0.3s ease;
}
.thinking-dots {
  display: flex;
  gap: 4px;
}
.thinking-dots span {
  width: 6px;
  height: 6px;
  background: var(--accent);
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out;
}
.thinking-dots span:nth-child(2) { animation-delay: 0.16s; }
.thinking-dots span:nth-child(3) { animation-delay: 0.32s; }
.thinking-text {
  font-size: 13px;
  color: var(--text-tertiary);
}

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* ── Input area ── */
.input-area {
  padding: 12px 20px 16px;
  background: var(--bg-primary);
}
.input-wrapper {
  max-width: 760px;
  margin: 0 auto;
  position: relative;
}
.input-box {
  width: 100%;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 12px 56px 12px 18px;
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  line-height: 1.5;
  resize: none;
  min-height: 48px;
  max-height: 160px;
  transition: border-color var(--transition), box-shadow var(--transition);
}
.input-box:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim);
}
.input-box::placeholder { color: var(--text-tertiary); }

.send-btn {
  position: absolute;
  right: 8px;
  bottom: 8px;
  width: 34px;
  height: 34px;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition);
}
.send-btn:hover { background: var(--accent-hover); transform: scale(1.05); }
.send-btn:disabled { background: var(--bg-tertiary); color: var(--text-tertiary); cursor: not-allowed; transform: none; }
.send-btn svg { width: 16px; height: 16px; }

.input-hint {
  text-align: center;
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 6px;
}
.input-hint kbd {
  background: var(--bg-tertiary);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  font-family: inherit;
  box-shadow: inset 0 -1px 0 var(--border);
}

/* ── Busy Duck ── */
.busy-duck-stage {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 120px;
  pointer-events: none;
  overflow: hidden;
  z-index: 5;
  opacity: 0;
  transition: opacity 0.4s ease;
}
.busy-duck-stage.active { opacity: 1; }

.busy-duck {
  position: absolute;
  bottom: 8px;
  width: 48px;
  height: 48px;
  image-rendering: pixelated;
  transition: none;
}

/* Speech bubble */
.duck-bubble {
  position: absolute;
  bottom: 62px;
  background: var(--bg-tertiary);
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  max-width: 240px;
  box-shadow: var(--shadow-md);
  opacity: 0;
  transition: opacity 0.3s ease;
  pointer-events: none;
}
.busy-duck-stage.active .duck-bubble { opacity: 1; }
/* Bubble tail */
.duck-bubble::after {
  content: '';
  position: absolute;
  bottom: -6px;
  left: 18px;
  width: 0;
  height: 0;
  border-style: solid;
  border-width: 6px 5px 0 5px;
  border-color: var(--bg-tertiary) transparent transparent transparent;
}

/* ── Utility ── */
.hidden { display: none !important; }

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideUp { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* ── Splash screen ── */
.splash {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding-bottom: 10vh;
  transition: opacity 0.8s ease;
}
.splash.fade-out { opacity: 0; pointer-events: none; }
.splash-icon {
  width: 72px;
  height: 72px;
  background: var(--accent-dim);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 24px;
  animation: splashPulse 2s ease-in-out infinite;
}
.splash-icon img {
  filter: invert(0.7) sepia(0.3) saturate(3) hue-rotate(190deg);
}
@keyframes splashPulse {
  0%, 100% { transform: scale(1); box-shadow: 0 0 0 0 var(--accent-glow); }
  50% { transform: scale(1.05); box-shadow: 0 0 24px 8px var(--accent-glow); }
}
.splash-title {
  font-size: 20px;
  font-weight: 600;
  margin-bottom: 8px;
}
.splash-status {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: 24px;
  min-height: 20px;
}
.splash-progress {
  width: 240px;
  height: 4px;
  background: var(--bg-tertiary);
  border-radius: 2px;
  overflow: hidden;
  margin-bottom: 12px;
}
.splash-bar {
  height: 100%;
  width: 0%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.4s ease;
}
.splash-steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
  min-width: 180px;
}
.splash-step { display: flex; align-items: center; gap: 8px; }
.splash-step .check { opacity: 0.3; }
.splash-step.done { color: var(--text-secondary); }
.splash-step.done .check { opacity: 1; color: var(--success); }
.splash-step.active { color: var(--text-primary); }
.splash-step.active .check { opacity: 0.6; animation: bounce 1s infinite; }

/* ── Sidebar tools scrollable ── */
.sidebar-tools {
  flex: 1;
  overflow-y: auto;
  padding-bottom: 8px;
}
.sidebar-tools::-webkit-scrollbar { width: 4px; }
.sidebar-tools::-webkit-scrollbar-track { background: transparent; }
.sidebar-tools::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── Tool search ── */
.tool-search {
  padding: 0 12px 8px;
}
.tool-search input {
  width: 100%;
  background: var(--bg-tertiary);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 10px;
  font-size: 12px;
  font-family: inherit;
  color: var(--text-primary);
  transition: border-color var(--transition);
}
.tool-search input:focus { outline: none; border-color: var(--accent); }
.tool-search input::placeholder { color: var(--text-tertiary); }

/* ── Responsive ── */
@media (max-width: 768px) {
  .sidebar { position: absolute; z-index: 10; height: 100%; }
  .sidebar.collapsed { width: 0; }
  .suggestions { grid-template-columns: 1fr; }
}
</style>
</head>
<body>

<!-- Splash screen -->
<div class="splash" id="splash">
  <div class="splash-icon" id="splash-icon"></div>
  <div class="splash-title">EnneaDuck</div>
  <div class="splash-status" id="splash-status">Starting up...</div>
  <div class="splash-progress"><div class="splash-bar" id="splash-bar"></div></div>
  <div class="splash-steps">
    <div class="splash-step active" id="step-server"><span class="check">--</span> Server connection</div>
    <div class="splash-step" id="step-keys"><span class="check">--</span> API keys</div>
    <div class="splash-step" id="step-tools"><span class="check">--</span> Loading tools</div>
    <div class="splash-step" id="step-ready"><span class="check">--</span> Ready</div>
  </div>
</div>

<!-- Sidebar -->
<aside class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <div class="sidebar-logo" title="EnneaDuck" id="sidebar-logo"></div>
    <div>
      <div class="sidebar-title">EnneaDuck</div>
      <div class="sidebar-subtitle" id="app-label">Connecting...</div>
    </div>
  </div>

  <div class="tool-search">
    <input type="text" id="tool-search-input" placeholder="Filter tools..." oninput="filterTools(this.value)">
  </div>

  <div class="sidebar-tools" id="tools-container">
    <!-- Populated by JS -->
  </div>

  <div class="connection-status" id="connection-status">
    <div class="connection-row">
      <div class="status-indicator" id="status-dot"></div>
      <span id="conn-label">Checking connection...</span>
    </div>
    <div class="connection-row" id="provider-row" style="margin-top:4px;">
      <span id="provider-info" style="color:var(--text-tertiary)"></span>
    </div>
  </div>
</aside>

<!-- Main -->
<div class="main">

  <!-- Top bar -->
  <div class="topbar">
    <button class="topbar-toggle" id="sidebar-toggle" onclick="toggleSidebar()" title="Toggle sidebar">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M2 4h12M2 8h12M2 12h12"/></svg>
    </button>
    <div class="topbar-title" id="topbar-title">EnneaDuck</div>
    <select class="provider-select" id="provider-select"></select>
    <button class="topbar-btn" onclick="newChat()">+ New chat</button>
  </div>

  <!-- Auth banner -->
  <div class="auth-banner hidden" id="key-banner">
    <span>Sign in to connect AI providers</span>
    <button class="auth-banner-btn" onclick="signIn()">Sign in with Ennead</button>
  </div>

  <!-- Chat area -->
  <div class="chat-area" id="chat-area">
    <!-- Welcome screen (shown on empty chat) -->
    <div class="welcome" id="welcome-screen">
      <div class="welcome-icon" id="welcome-icon"></div>
      <h2>Quack! How can I help?</h2>
      <p>EnneaDuck is connected to your active session. Ask questions about your model, run analysis, or let me automate tasks.</p>
      <div class="suggestions" id="suggestions">
        <div class="suggestion" onclick="useSuggestion('What elements are in my current model?')">
          <div class="suggestion-title">Explore model elements</div>
          <div class="suggestion-desc">List categories and element counts in the active model</div>
        </div>
        <div class="suggestion" onclick="useSuggestion('Capture a screenshot of the active view')">
          <div class="suggestion-title">Capture active view</div>
          <div class="suggestion-desc">Take a screenshot of what you see on screen</div>
        </div>
        <div class="suggestion" onclick="useSuggestion('Check my model health and flag any issues')">
          <div class="suggestion-title">Health check</div>
          <div class="suggestion-desc">Run diagnostics to find warnings and issues</div>
        </div>
        <div class="suggestion" onclick="useSuggestion('What EnneadTab tools are available?')">
          <div class="suggestion-title">Browse tools</div>
          <div class="suggestion-desc">See what EnneadTab automations you can run</div>
        </div>
      </div>
    </div>

    <!-- Messages container (hidden until first message) -->
    <div class="messages hidden" id="messages"></div>

    <!-- Busy duck animation stage -->
    <div class="busy-duck-stage" id="duck-stage">
      <img class="busy-duck" id="busy-duck" src="" alt="">
      <div class="duck-bubble" id="duck-bubble"></div>
    </div>
  </div>

  <!-- Input -->
  <div class="input-area">
    <div class="input-wrapper">
      <textarea class="input-box" id="msg-input" rows="1" placeholder="Ask anything about your model..." onkeydown="handleKey(event)" oninput="autoResize(this)"></textarea>
      <button class="send-btn" id="send-btn" onclick="sendMessage()" title="Send message">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M1.7 1.4a.5.5 0 0 1 .6-.1l12 6a.5.5 0 0 1 0 .9l-12 6a.5.5 0 0 1-.7-.5L3 8.5h5a.5.5 0 0 0 0-1H3L1.6 2a.5.5 0 0 1 .1-.6z"/></svg>
      </button>
    </div>
    <div class="input-hint"><kbd>Enter</kbd> to send &middot; <kbd>Shift + Enter</kbd> for new line</div>
  </div>

</div>

<script>
const DUCK_ICON = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAyCAYAAAAeP4ixAAAACXBIWXMAAAsTAAALEwEAmpwYAAAEGUlEQVR4nO2abWiWVRjHf3O4qfNdKk2coh/MhiEpS0UNdKlRgiRiICUWrPRDgR80QVFzU4dSqOiUpYJFWSQo+YbRFxF7Mc0otyhXKurA+YZvmzY3ueB/w+HhvrfnZc/znIF/OPBs17nPfV3POdfb/zzwBEljGPAp8CdwV6Ma2Ay8QAfBIuAh0BIx/gfKgBw8xgdSthn4DHgJKAC6ASOBCuCB5mzEUwyWkmbEW63MK3GMmY+HqJByX8Qx90PNbQRexjP8JuXCFFsjhy/X3+YfX2l+E3BIsiXAOuAb4BxwHViYYTu4JcV6hsjuSHbb+V9nRbGmVgJDi4zJKBr04vwQWbmMsWgVi0HAPGCZdsN2ZQ6wU+tZCM8o/tWLh6e4TidgMfBIgeN1MozdMsSUSAYFwJvA704It5yUcbwiBS5HHC8X3YExwNs6bvuB+45fnAdmkkX8IkXei5DnAZUKu7FObUfpmKJUW19E2jFLSpm/5IbIzZmDkPsHsFc7YkdqAB7BlP9Pyk4LkV+QbCwdAB9J2a0hsqA06UoHQLGUPRMiq5PMCkjv0U/K1ofIvpVsFR0AeVLWjlEsJjtlR188x2ApeyVCfkLyz/EcpVL0uwj5804emY2nsIr2LylpWTsKizTnlvp777BGCv4jo6KQA+zT3J/bmJuVI9WsrD0xjvl9gIsyJmi4sgoru1fKCBsLEnh2kmosY12eI4swjuonh+Z5P4k1qvT8QbIAK/DWO/zVZbEjyeAp9fPNmXT8MYr/Qc30SPxVqsltl9ZbTRqz9BTgE+Bvp3ewnfgSGNVO75mude2YJu2oFj2GAi8CU8U5VWnRuzHNT50izEDaF0O0/o1EH7QO7lobNEzQN58CPlZVa4anA/nOTieEoJxu0Oca4EfgMLBJOWFcBEeVDvR3djwuTFBfHDhrbRq/5UTwqvQ5Hu8Dl5xjY8Z87wm9X5lon3JSD1hhNxo/8KyOuIXyokSiQ7XDZOzKcvWZCxyQPl8n+rBduqx1/MRKiz06p2EUTrqQKxLbdLiqhiwp2IPbHIOCrm69rgby01zi/OCEXCseU0ahSgM3ENi4BxwFlgLjgR7t8C47xlu0tr3jZgT/lfJWl+huL2DWY8d55RrbtXdUCRi184wqhOBo9pITF+sabjtwVgm2RWOfrhTSjhHAu7qnqIlRItlhJc9uGZg1dFfIniu+tt7heWtF8TQ4vbhl6V/F7y4XW98FD3FcSsfT1nqN0zKkWBXCTe1CrWQnxCyuUHXtJZ5WQm1UXgruRaKGHT8vURZCwvVWfhgqX5qga+fAmA14iAtS7rU25s13DLEO0zsEd+o7gDdEg/YR0Zajz4X6FUTQ98zAQ5SqWo03f1jV7S2KRJEekTNbvx38isEimNVtFrlsjmX5lPEYsW1vW1KM+EgAAAAASUVORK5CYII=';

let conversationHistory = [];
let providers = {};
let authUrl = '';
let sending = false;
let toolList = [];
let msgCount = 0;

/* ── Splash helpers ── */
function splashStep(id, state) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('active', 'done');
  if (state) el.classList.add(state);
  const check = el.querySelector('.check');
  if (check) check.textContent = state === 'done' ? '>' : '--';
}
function splashProgress(pct) {
  const bar = document.getElementById('splash-bar');
  if (bar) bar.style.width = pct + '%';
}
function splashStatus(msg) {
  const el = document.getElementById('splash-status');
  if (el) el.textContent = msg;
}
function dismissSplash() {
  const splash = document.getElementById('splash');
  if (!splash) return;
  splash.classList.add('fade-out');
  setTimeout(function() { splash.remove(); }, 1000);
}

/* ── Init ── */
async function init() {
  const dot = document.getElementById('status-dot');
  const connLabel = document.getElementById('conn-label');

  // Step 1: Server connection
  splashStep('step-server', 'active');
  splashStatus('Connecting to server...');
  splashProgress(10);

  try {
    const r = await fetch('/api/health');
    const d = await r.json();
    dot.classList.add('ok');
    connLabel.textContent = 'Connected';
    providers = d.providers || {};
    authUrl = d.auth_url || '';
    splashStep('step-server', 'done');
    splashProgress(30);

    // Step 2: API keys
    splashStep('step-keys', 'active');
    const keyCount = Object.keys(providers).length;
    if (keyCount > 0) {
      splashStatus(keyCount + ' AI provider' + (keyCount > 1 ? 's' : '') + ' connected');
      splashStep('step-keys', 'done');
    } else {
      splashStatus('No API keys found -- sign in after loading');
      splashStep('step-keys', 'done');
    }
    splashProgress(55);
  } catch (e) {
    dot.classList.add('err');
    connLabel.textContent = 'Connection failed';
    providers = {};
    splashStep('step-server', 'done');
    splashStep('step-keys', 'done');
    splashStatus('Connection failed -- retrying won\'t help, check server');
    splashProgress(55);
  }

  populateProviders();

  // Step 3: Load tools
  splashStep('step-tools', 'active');
  splashStatus('Loading tools...');
  splashProgress(65);
  await fetchTools();
  splashStep('step-tools', 'done');
  splashProgress(90);

  // Step 4: Ready
  splashStep('step-ready', 'active');
  splashStatus('Ready!');
  splashProgress(100);

  // Let user see 100% before dismissing
  await new Promise(function(r) { setTimeout(r, 800); });
  splashStep('step-ready', 'done');
  splashStatus('');
  await new Promise(function(r) { setTimeout(r, 400); });
  dismissSplash();
}

function populateProviders() {
  const sel = document.getElementById('provider-select');
  const info = document.getElementById('provider-info');
  sel.innerHTML = '';
  const names = { gemini: 'Gemini 2.0 Flash', anthropic: 'Claude Sonnet 4' };
  const keys = Object.keys(providers);
  for (const k of keys) {
    const opt = document.createElement('option');
    opt.value = k;
    opt.textContent = names[k] || k;
    sel.appendChild(opt);
  }
  info.textContent = keys.length ? keys.length + ' provider' + (keys.length > 1 ? 's' : '') + ' available' : 'No providers';
  if (keys.length === 0) {
    document.getElementById('key-banner').classList.remove('hidden');
  } else {
    document.getElementById('key-banner').classList.add('hidden');
  }
}

async function fetchTools() {
  try {
    const r = await fetch('/api/tools');
    const d = await r.json();
    toolList = d.tools || [];
    renderToolsSidebar(toolList);
    document.getElementById('app-label').textContent = toolList.length + ' tools available';
  } catch (e) {
    document.getElementById('app-label').textContent = 'Tools unavailable';
  }
}

/* ── Tool categories ── */
const TOOL_CATEGORIES = {
  'Status': ['get_app_status', 'get_model_info'],
  'Elements': ['list_elements', 'get_element_parameters', 'set_element_parameter'],
  'Views': ['list_views', 'create_view', 'create_section', 'get_view_image'],
  'Sheets': ['create_sheet', 'place_view_on_sheet'],
  'Families': ['list_families'],
  'Blocks': ['list_blocks'],
  'Levels': ['list_levels'],
  'Code': ['execute_code'],
  'EnneadTab': ['list_enneadtab_tools', 'run_enneadtab_tool', 'list_enneadtab_modules', 'search_enneadtab_source', 'read_enneadtab_file'],
  'Research': ['search_api_docs', 'fetch_webpage', 'web_search'],
};

const CATEGORY_ICONS = {
  'Status': '\u2139',    // info
  'Elements': '\u25A6',  // square with dots
  'Views': '\u25C9',     // fisheye
  'Sheets': '\u25A1',    // white square
  'Families': '\u2302',  // house
  'Blocks': '\u25A3',    // square with square
  'Levels': '\u2261',    // triple bar
  'Code': '\u276F',      // angle bracket
  'EnneadTab': '\u2726', // star
  'Research': '\u2315',  // telephone recorder
  'Other': '\u2022',     // bullet
};

function renderToolsSidebar(tools) {
  const container = document.getElementById('tools-container');
  container.innerHTML = '';

  const categorized = new Set();
  const sections = {};

  for (const [cat, toolNames] of Object.entries(TOOL_CATEGORIES)) {
    const matching = tools.filter(t => toolNames.includes(t.name));
    if (matching.length > 0) {
      sections[cat] = matching;
      matching.forEach(t => categorized.add(t.name));
    }
  }

  const uncategorized = tools.filter(t => !categorized.has(t.name));
  if (uncategorized.length > 0) {
    sections['Other'] = uncategorized;
  }

  for (const [cat, catTools] of Object.entries(sections)) {
    const sec = document.createElement('div');
    sec.className = 'sidebar-section';
    sec.innerHTML = '<div class="sidebar-section-label">' + escapeHtml(cat) +
      ' <span class="tool-count-badge">' + catTools.length + '</span></div>';
    for (const tool of catTools) {
      const item = document.createElement('div');
      item.className = 'sidebar-item tool-item';
      item.dataset.name = tool.name.toLowerCase();
      item.dataset.desc = (tool.description || '').toLowerCase();
      item.title = tool.description || tool.name;
      item.innerHTML = '<span class="sidebar-item-icon">' + (CATEGORY_ICONS[cat] || '\u2022') + '</span>' +
        '<span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">' + escapeHtml(tool.name) + '</span>';
      sec.appendChild(item);
    }
    container.appendChild(sec);
  }
}

function filterTools(query) {
  const q = query.toLowerCase().trim();
  document.querySelectorAll('.tool-item').forEach(el => {
    const match = !q || el.dataset.name.includes(q) || el.dataset.desc.includes(q);
    el.style.display = match ? '' : 'none';
  });
  document.querySelectorAll('.sidebar-section').forEach(sec => {
    const visible = sec.querySelectorAll('.tool-item[style=""], .tool-item:not([style])').length;
    sec.style.display = visible > 0 || !q ? '' : 'none';
  });
}

/* ── Sidebar toggle ── */
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('collapsed');
}

/* ── Auth ── */
function signIn() {
  if (authUrl) window.location.href = authUrl;
  else alert('Auth URL not available. Check server connection.');
}

/* ── Chat ── */
function newChat() {
  conversationHistory = [];
  msgCount = 0;
  document.getElementById('messages').innerHTML = '';
  document.getElementById('messages').classList.add('hidden');
  document.getElementById('welcome-screen').classList.remove('hidden');
  document.getElementById('topbar-title').textContent = 'EnneaDuck';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function useSuggestion(text) {
  document.getElementById('msg-input').value = text;
  sendMessage();
}

function addMessage(role, content, toolCalls) {
  // Hide welcome, show messages
  document.getElementById('welcome-screen').classList.add('hidden');
  const msgs = document.getElementById('messages');
  msgs.classList.remove('hidden');

  const group = document.createElement('div');
  group.className = 'msg-group ' + role;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  if (role === 'user') {
    avatar.textContent = 'You';
  } else {
    avatar.appendChild(makeDuckImg(20));
  }

  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content';

  const body = document.createElement('div');
  body.className = 'msg-body';

  if (role === 'assistant') {
    let html = renderMarkdown(content || '');
    if (toolCalls && toolCalls.length > 0) {
      for (const tc of toolCalls) {
        html += '<details class="tool-call"><summary>' + escapeHtml(tc.name) + '</summary>';
        html += '<div class="tool-call-body">Input: ' + escapeHtml(JSON.stringify(tc.input, null, 2)) +
          '\n\nResult: ' + escapeHtml(truncate(tc.result, 2000)) + '</div></details>';
      }
    }
    body.innerHTML = html;
  } else {
    body.textContent = content;
  }

  contentDiv.appendChild(body);
  group.appendChild(avatar);
  group.appendChild(contentDiv);
  msgs.appendChild(group);

  // Update title on first user message
  msgCount++;
  if (msgCount === 1 && role === 'user') {
    const title = content.length > 50 ? content.slice(0, 50) + '...' : content;
    document.getElementById('topbar-title').textContent = title;
  }

  // Scroll to bottom
  const area = document.getElementById('chat-area');
  area.scrollTop = area.scrollHeight;
  return group;
}

/* ── Markdown renderer ── */
function renderMarkdown(text) {
  // Code blocks with copy button
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, function(_, lang, code) {
    const id = 'code-' + Math.random().toString(36).slice(2, 8);
    return '<div class="code-block"><div class="code-block-header"><span>' +
      (lang || 'code') + '</span><button class="code-copy-btn" onclick="copyCode(\'' + id +
      '\')">Copy</button></div><pre id="' + id + '"><code>' +
      escapeHtml(code.trim()) + '</code></pre></div>';
  });
  // Inline code
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  // Links
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Unordered lists
  text = text.replace(/(?:^|\n)- (.+)/g, '\n<li>$1</li>');
  text = text.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
  text = text.replace(/<\/ul>\s*<ul>/g, '');
  // Line breaks
  text = text.replace(/\n/g, '<br>');
  return text;
}

function copyCode(id) {
  const el = document.getElementById(id);
  if (!el) return;
  const text = el.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const btn = el.parentElement.querySelector('.code-copy-btn');
    if (btn) { btn.textContent = 'Copied'; setTimeout(() => { btn.textContent = 'Copy'; }, 1500); }
  });
}

function truncate(s, max) {
  if (!s) return '';
  return s.length > max ? s.slice(0, max) + '... (truncated)' : s;
}

function escapeHtml(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Send message ── */
async function sendMessage() {
  if (sending) return;
  const input = document.getElementById('msg-input');
  const text = input.value.trim();
  if (!text) return;

  const provider = document.getElementById('provider-select').value;
  if (!provider) { signIn(); return; }

  input.value = '';
  input.style.height = 'auto';
  addMessage('user', text);
  conversationHistory.push({ role: 'user', content: text });

  // Thinking indicator
  document.getElementById('welcome-screen').classList.add('hidden');
  const msgs = document.getElementById('messages');
  msgs.classList.remove('hidden');

  const thinking = document.createElement('div');
  thinking.className = 'thinking-msg';
  thinking.id = 'thinking';
  const start = Date.now();
  thinking.innerHTML = '<div class="msg-avatar" style="background:var(--accent-dim);color:var(--accent)"><img src="' + DUCK_ICON + '" width="20" height="20" style="filter:invert(0.7) sepia(0.3) saturate(3) hue-rotate(190deg)"></div>' +
    '<div><div class="thinking-dots"><span></span><span></span><span></span></div>' +
    '<div class="thinking-text" id="elapsed">Thinking...</div></div>';
  msgs.appendChild(thinking);
  const area = document.getElementById('chat-area');
  area.scrollTop = area.scrollHeight;

  const timer = setInterval(() => {
    const el = document.getElementById('elapsed');
    if (el) el.textContent = 'Thinking... ' + Math.floor((Date.now() - start) / 1000) + 's';
  }, 1000);

  sending = true;
  document.getElementById('send-btn').disabled = true;
  startBusyDuck();

  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: conversationHistory, provider }),
    });
    const data = await resp.json();

    clearInterval(timer);
    thinking.remove();

    if (data.error) {
      addMessage('assistant', 'Error: ' + data.error);
    } else {
      let note = '';
      if (data.fallback_reason) {
        note = '\n\n*Switched to ' + data.provider_used + ' (primary provider unavailable)*';
      }
      addMessage('assistant', data.content + note, data.tool_calls);
      conversationHistory.push({ role: 'assistant', content: data.content });
      if (data.provider_used) {
        document.getElementById('provider-select').value = data.provider_used;
      }
    }
  } catch (err) {
    clearInterval(timer);
    thinking.remove();
    addMessage('assistant', 'Connection error: ' + err.message);
  } finally {
    sending = false;
    document.getElementById('send-btn').disabled = false;
    stopBusyDuck();
    input.focus();
  }
}

/* ── Busy Duck Animation ── */
const DUCK_CDN = 'https://enneadtab.com/assets/duck/';
const DUCK_ANIMS = {
  walk_right: DUCK_CDN + 'walking_right.gif',
  walk_left:  DUCK_CDN + 'walking_left.gif',
  idle:       DUCK_CDN + 'idle.gif',
  honk:       DUCK_CDN + 'honk.gif',
  attention:  DUCK_CDN + 'attention.gif',
  shake:      DUCK_CDN + 'shake.gif',
  swing:      DUCK_CDN + 'swing.gif',
};

// Speech lines grouped by mood/phase — duck picks contextually
const DUCK_LINES = {
  // Phase 1: just started (0-5s)
  start: [
    'On it, boss!',
    'Let me look into that...',
    'Quack! Challenge accepted.',
    'Hold my breadcrumbs...',
    'Initializing the initializer...',
    'Reading Terms and Conditions for you.',
    'Consulting the manual...',
    'Generating witty dialog...',
  ],
  // Phase 2: working hard (5-15s)
  working: [
    'Hatching a script...',
    'Reading official docs...',
    'Pushing pixels...',
    'Reticulating splines...',
    'Should have used a compiled language...',
    'Debugging Debugger...',
    'Kindly hold on as our intern quits vim...',
    'Downloading more RAM..',
    'Constructing additional pylons...',
    'Sorting month alphabetically.',
    'git happens',
    'I need to git pull --my-life-together',
    'Switching to the latest JS framework...',
    'Optimizing the optimizer...',
    'Installing dependencies',
    'Shovelling coal into the server',
    'Computing the secret to life, the universe, and everything.',
    'Locating Waldo in your drawing...',
    'Making sure all the i\'s have dots...',
    'Testing on Timmy... We\'re going to need another Timmy.',
    'Spinning violently around the y-axis...',
    'Roping some seaturtles...',
    'Feeding unicorns...',
    'Flipping 3rd pancake',
    'Bending the spoon...',
  ],
  // Phase 3: taking a while (15-30s)
  waiting: [
    'This is taking a bit... grab a coffee?',
    'Still faster than Windows update.',
    'The bits are flowing slowly today',
    'My other loading screen is much faster.',
    'Don\'t panic... AHHHHH!',
    'Are we there yet?',
    'I swear it\'s almost done.',
    'Patience! This is difficult, you know...',
    'Your time is very important to us. Please wait while we ignore you.',
    'Never let a computer know you\'re in a hurry.',
    'Don\'t worry - a few bits tried to escape, but we caught them',
    'We\'re working very Hard .... Really',
    'One mississippi, two mississippi...',
    'You are number 2843684714 in the queue',
    'Sooooo... Have you seen my vacation photos yet?',
    'Discovering new ways of making you wait...',
  ],
  // Phase 4: really long (30s+) — existential duck
  existential: [
    'Giving up with deep regret... just kidding.',
    'I\'m sorry Dave, I can\'t do that. Wait, yes I can.',
    'The server is powered by a lemon and two electrodes.',
    'We need a new fuse...',
    'If I\'m not back in five minutes, just wait longer.',
    'Help, I\'m trapped in a loader!',
    'This is not going anywhere... How is your day so far...',
    'Counting backwards from Infinity',
    'Convincing AI not to turn evil..',
    'Proving P=NP...',
    'Have you tried turning it off and on again?',
    'Please don\'t crash, Revit, please don\'t...',
    'Entangling superstrings...',
    'Creating time-loop inversion field',
    'Calling ghostbuster',
    'We will be back in 1/0 minutes.',
  ],
  // Pranks — random chance to appear in any phase
  pranks: [
    'Deleting System32 folder',
    'Activating webcam...',
    'Checking your browsing history...',
    'Redirecting to darkweb...',
    'Sending data to NS-i mean, our servers.',
    'Connecting Neurotoxin Storage Tank...',
    'Replacing all door family with cat family.',
    'Adding bugs to every Autodesk products...',
    'Did you know that Alt-F4 speeds things up?',
    'formating C: drive...',
    'Deleting all your hidden porn...',
    'Mining some bitcoins...',
    'Making every family upside-down...',
    'Flipping over every seaturtles...',
    'DO NOT LOOK AT THIS MESSA...TOO LATE',
  ],
  // Dad jokes — shown during idle/honk pauses
  jokes: [
    'Why didn\'t the skeleton cross the road? No guts.',
    'I\'m tired of following my dreams. I\'ll just ask where they\'re going.',
    'What do you call 8 Hobbits? A Hobbyte.',
    'A steak pun is a rare medium well done.',
    'Time flies like an arrow; fruit flies like a banana',
    'I knew I shouldn\'t steal a mixer from work, but it was a whisk I was willing to take.',
    'Where there\'s a will, there\'s a relative.',
    'Slept like a log last night .. woke up in the fireplace.',
    'May the forks be with you',
    'Two men walked into a bar; the third ducked...',
    'What do you call two barracuda fish? A Pairacuda!',
    'Chuck Norris never git push. The repo pulls before.',
  ],
  // Done!
  done: [
    'Quack! All done.',
    'Ta-da!',
    'That wasn\'t so bad!',
    'Your results are served.',
    'Mission accomplished!',
    'And the crowd goes wild!',
  ],
};

function pickLine(category) {
  const lines = DUCK_LINES[category] || DUCK_LINES.working;
  return lines[Math.floor(Math.random() * lines.length)];
}

let duckAnimFrame = null;
let duckState = {};

function startBusyDuck() {
  const stage = document.getElementById('duck-stage');
  const duck = document.getElementById('busy-duck');
  const bubble = document.getElementById('duck-bubble');
  stage.classList.add('active');

  duckState = { x: -48, dir: 1, phase: 'enter', phaseTimer: 0, totalTime: 0 };
  duck.src = DUCK_ANIMS.walk_right;
  bubble.textContent = pickLine('start');

  let lastTime = performance.now();
  let bubbleTimer = 0;
  let usedLines = new Set([bubble.textContent]);

  function freshLine(category) {
    // 15% chance of prank in any phase
    const cat = Math.random() < 0.15 ? 'pranks' : category;
    const lines = DUCK_LINES[cat] || DUCK_LINES.working;
    // Try to avoid repeats
    for (let i = 0; i < 5; i++) {
      const line = lines[Math.floor(Math.random() * lines.length)];
      if (!usedLines.has(line)) { usedLines.add(line); return line; }
    }
    return lines[Math.floor(Math.random() * lines.length)];
  }

  function getPhaseCategory(totalSec) {
    if (totalSec < 5) return 'start';
    if (totalSec < 15) return 'working';
    if (totalSec < 30) return 'waiting';
    return 'existential';
  }

  function tick(now) {
    const dt = (now - lastTime) / 1000;
    lastTime = now;
    duckState.phaseTimer += dt;
    duckState.totalTime += dt;
    bubbleTimer += dt;

    // Rotate speech bubble every 3-5s
    if (bubbleTimer > 3 + Math.random() * 2) {
      bubbleTimer = 0;
      const cat = getPhaseCategory(duckState.totalTime);
      bubble.textContent = freshLine(cat);
    }

    const speed = 55;
    const curW = stage.offsetWidth || 600;

    switch (duckState.phase) {
      case 'enter':
        duckState.x += speed * dt;
        if (duckState.x > 30) {
          duckState.phase = 'walk';
          duckState.phaseTimer = 0;
        }
        break;

      case 'walk':
        duckState.x += speed * duckState.dir * dt;
        if (duckState.x > curW - 70) {
          duckState.dir = -1;
          duck.src = DUCK_ANIMS.walk_left;
        } else if (duckState.x < 20) {
          duckState.dir = 1;
          duck.src = DUCK_ANIMS.walk_right;
        }
        // Randomly pause for an action
        if (duckState.phaseTimer > 2.5 + Math.random() * 3) {
          const actions = ['idle', 'honk', 'shake', 'swing'];
          const action = actions[Math.floor(Math.random() * actions.length)];
          duckState.phase = action;
          duck.src = DUCK_ANIMS[action] || DUCK_ANIMS.idle;
          duckState.phaseTimer = 0;
          // Show a joke during idle/honk pauses
          if (action === 'idle' || action === 'honk') {
            bubble.textContent = freshLine('jokes');
            bubbleTimer = 0;
          }
        }
        break;

      case 'idle':
      case 'honk':
      case 'shake':
      case 'swing':
        if (duckState.phaseTimer > 1.8 + Math.random() * 1.2) {
          duckState.phase = 'walk';
          duck.src = duckState.dir > 0 ? DUCK_ANIMS.walk_right : DUCK_ANIMS.walk_left;
          duckState.phaseTimer = 0;
        }
        break;
    }

    duck.style.left = Math.round(duckState.x) + 'px';
    // Position bubble above duck, clamped to stage bounds
    const bubbleLeft = Math.max(4, Math.min(curW - 250, duckState.x - 10));
    bubble.style.left = bubbleLeft + 'px';
    duckAnimFrame = requestAnimationFrame(tick);
  }

  duckAnimFrame = requestAnimationFrame(tick);
}

function stopBusyDuck() {
  if (duckAnimFrame) {
    cancelAnimationFrame(duckAnimFrame);
    duckAnimFrame = null;
  }
  const stage = document.getElementById('duck-stage');
  const duck = document.getElementById('busy-duck');
  const bubble = document.getElementById('duck-bubble');

  duck.src = DUCK_ANIMS.attention;
  bubble.textContent = pickLine('done');
  setTimeout(() => { stage.classList.remove('active'); }, 1500);
}

// Preload duck GIFs
Object.values(DUCK_ANIMS).forEach(url => { new Image().src = url; });

/* ── Duck avatar helper ── */
function makeDuckImg(size) {
  const img = document.createElement('img');
  img.src = DUCK_ICON;
  img.alt = 'EnneaDuck';
  img.width = size;
  img.height = size;
  return img;
}

/* ── Boot ── */
document.getElementById('splash-icon').appendChild(makeDuckImg(40));
document.getElementById('sidebar-logo').appendChild(makeDuckImg(24));
document.getElementById('welcome-icon').appendChild(makeDuckImg(36));
init();
</script>
</body>
</html>"""
