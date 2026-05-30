/**
 * ResolveAI Web Chat Widget
 *
 * Drop this script on any page to embed a floating chat window backed by
 * the ResolveAI WebSocket endpoint (/ws/chat/{session_id}).
 *
 * Usage:
 *   <script src="/static/widget.js" data-api="https://your-domain.com"></script>
 */
(function () {
  "use strict";

  const API_BASE =
    document.currentScript?.dataset.api ||
    window.location.origin;

  // ── Generate or restore a stable session ID ──────────────────────────────
  const SESSION_KEY = "resolveai_session_id";
  let sessionId = sessionStorage.getItem(SESSION_KEY);
  if (!sessionId) {
    sessionId =
      "web-" +
      Date.now().toString(36) +
      "-" +
      Math.random().toString(36).slice(2, 9);
    sessionStorage.setItem(SESSION_KEY, sessionId);
  }

  // ── Build DOM ─────────────────────────────────────────────────────────────
  const style = document.createElement("style");
  style.textContent = `
    #resolveai-widget {
      position: fixed; bottom: 24px; right: 24px; z-index: 9999;
      font-family: system-ui, sans-serif; font-size: 14px;
    }
    #resolveai-toggle {
      width: 56px; height: 56px; border-radius: 50%;
      background: #2563eb; color: #fff; border: none; cursor: pointer;
      font-size: 26px; box-shadow: 0 4px 12px rgba(0,0,0,.25);
      display: flex; align-items: center; justify-content: center;
    }
    #resolveai-box {
      display: none; flex-direction: column;
      width: 340px; height: 480px; background: #fff;
      border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,.18);
      margin-bottom: 8px; overflow: hidden;
    }
    #resolveai-box.open { display: flex; }
    #resolveai-header {
      background: #2563eb; color: #fff;
      padding: 14px 16px; font-weight: 600; font-size: 15px;
    }
    #resolveai-messages {
      flex: 1; overflow-y: auto; padding: 12px;
      display: flex; flex-direction: column; gap: 8px;
    }
    .ra-msg {
      max-width: 80%; padding: 8px 12px; border-radius: 16px; line-height: 1.45;
    }
    .ra-msg.user {
      align-self: flex-end; background: #2563eb; color: #fff;
      border-bottom-right-radius: 4px;
    }
    .ra-msg.agent {
      align-self: flex-start; background: #f1f5f9; color: #1e293b;
      border-bottom-left-radius: 4px;
    }
    #resolveai-input-row {
      display: flex; gap: 8px; padding: 10px 12px;
      border-top: 1px solid #e2e8f0;
    }
    #resolveai-input {
      flex: 1; border: 1px solid #cbd5e1; border-radius: 8px;
      padding: 8px 10px; outline: none; resize: none;
    }
    #resolveai-send {
      background: #2563eb; color: #fff; border: none;
      border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 14px;
    }
    #resolveai-send:disabled { background: #94a3b8; cursor: not-allowed; }
  `;
  document.head.appendChild(style);

  const widget = document.createElement("div");
  widget.id = "resolveai-widget";
  widget.innerHTML = `
    <div id="resolveai-box">
      <div id="resolveai-header">ResolveAI Support</div>
      <div id="resolveai-messages"></div>
      <div id="resolveai-input-row">
        <textarea id="resolveai-input" rows="1"
          placeholder="Type a message…"></textarea>
        <button id="resolveai-send">Send</button>
      </div>
    </div>
    <button id="resolveai-toggle" title="Chat with us">💬</button>
  `;
  document.body.appendChild(widget);

  const box = widget.querySelector("#resolveai-box");
  const toggle = widget.querySelector("#resolveai-toggle");
  const messages = widget.querySelector("#resolveai-messages");
  const input = widget.querySelector("#resolveai-input");
  const sendBtn = widget.querySelector("#resolveai-send");

  // ── Toggle open / close ───────────────────────────────────────────────────
  toggle.addEventListener("click", () => {
    box.classList.toggle("open");
    if (box.classList.contains("open")) {
      connectWs();
      input.focus();
    }
  });

  // ── WebSocket ─────────────────────────────────────────────────────────────
  let ws = null;

  function connectWs() {
    if (ws && ws.readyState <= WebSocket.OPEN) return;

    const proto = API_BASE.startsWith("https") ? "wss" : "ws";
    const host = API_BASE.replace(/^https?:\/\//, "");
    const url = `${proto}://${host}/ws/chat/${sessionId}`;

    ws = new WebSocket(url);

    ws.onopen = () => {
      sendBtn.disabled = false;
    };

    ws.onmessage = (event) => {
      appendMessage("agent", event.data);
    };

    ws.onclose = () => {
      sendBtn.disabled = true;
      appendMessage("agent", "Connection closed. Refresh to reconnect.");
    };

    ws.onerror = () => {
      appendMessage("agent", "Connection error. Please try again.");
    };
  }

  function appendMessage(role, text) {
    const el = document.createElement("div");
    el.className = `ra-msg ${role}`;
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  function sendMessage() {
    const text = input.value.trim();
    if (!text || !ws || ws.readyState !== WebSocket.OPEN) return;
    appendMessage("user", text);
    ws.send(JSON.stringify({ content: text, session_id: sessionId }));
    input.value = "";
  }

  sendBtn.addEventListener("click", sendMessage);

  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
})();
