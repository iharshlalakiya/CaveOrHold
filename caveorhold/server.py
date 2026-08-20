import asyncio
import queue
import threading

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from caveorhold.orchestrator import run_free_debate_stream

_SENTINEL = object()

app = FastAPI(title="CaveOrHold")


@app.websocket("/ws/live")
async def live_debate(ws: WebSocket):
    await ws.accept()
    stop_event = threading.Event()
    receiver_task = None
    try:
        await ws.send_json({"type": "start"})

        # The debate generator does blocking HTTP calls, so run it in a worker thread
        # and relay events through a queue to keep the event loop free to send over the socket.
        event_queue: queue.Queue = queue.Queue()

        def worker():
            try:
                for event in run_free_debate_stream(stop_event):
                    event_queue.put(event)
            except Exception as e:
                event_queue.put({"type": "error", "message": str(e)})
            finally:
                event_queue.put(_SENTINEL)

        threading.Thread(target=worker, daemon=True).start()

        async def receiver():
            # Listens for a client "stop" command while the debate runs, without blocking sends.
            try:
                while True:
                    msg = await ws.receive_json()
                    if msg.get("action") == "stop":
                        stop_event.set()
                        break
            except Exception:
                stop_event.set()

        receiver_task = asyncio.create_task(receiver())

        loop = asyncio.get_event_loop()
        while True:
            event = await loop.run_in_executor(None, event_queue.get)
            if event is _SENTINEL:
                break
            await ws.send_json(event)
    except WebSocketDisconnect:
        stop_event.set()
    except Exception as e:
        stop_event.set()
        try:
            await ws.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        stop_event.set()
        if receiver_task:
            receiver_task.cancel()


@app.get("/", response_class=HTMLResponse)
def index():
    return """
    <!doctype html>
    <html>
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>CaveOrHold</title>
      <style>
        /* Single standard theme — deliberately dark, used everywhere regardless of system setting. */
        :root {
          --bg: #0f1117;
          --surface: #171a23;
          --surface-2: #1c1f2a;
          --border: #2a2e3b;
          --text: #e5e7eb;
          --text-muted: #9ca3af;
          --accent: #6366f1;
          --accent-2: #8b5cf6;
          --agent1: #10b981;
          --agent1-text: #34d399;
          --agent1-bg: #0c2a20;
          --agent1-border: #1e5a41;
          --agent2: #f43f5e;
          --agent2-text: #fb7185;
          --agent2-bg: #2b1420;
          --agent2-border: #6b2438;
          --danger: #e11d48;
          --shadow: 0 1px 2px rgba(0,0,0,0.2), 0 4px 16px rgba(0,0,0,0.35);
        }
        * { box-sizing: border-box; }
        body {
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, sans-serif;
          background: var(--bg);
          color: var(--text);
          margin: 0;
          padding: 2.5rem 1.25rem 4rem;
          min-height: 100vh;
        }
        .page { max-width: 780px; margin: 0 auto; }
        .hero { text-align: center; margin-bottom: 1.5rem; }
        .hero h1 {
          font-size: 2.25rem;
          font-weight: 800;
          margin: 0 0 0.35rem;
          background: linear-gradient(135deg, var(--accent), var(--accent-2));
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
          letter-spacing: -0.02em;
        }
        .sub { color: var(--text-muted); margin: 0; font-size: 0.95rem; }

        /* Arena banner: two glowing corners with a VS badge between them */
        .arena {
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0;
          margin: 1.5rem 0 1.25rem;
          position: relative;
        }
        .arena-side {
          flex: 1;
          display: flex;
          align-items: center;
          gap: 0.6rem;
          padding: 0.85rem 1.1rem;
          border-radius: 14px;
          font-weight: 700;
          font-size: 0.95rem;
          position: relative;
          overflow: hidden;
        }
        .arena-side.side-a { justify-content: flex-end; text-align: right; margin-right: -0.75rem; background: linear-gradient(120deg, var(--agent1-bg), transparent 85%); }
        .arena-side.side-b { justify-content: flex-start; text-align: left; margin-left: -0.75rem; background: linear-gradient(240deg, var(--agent2-bg), transparent 85%); }
        .arena-avatar {
          width: 38px; height: 38px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: 1rem; font-weight: 800; color: #ffffff; flex-shrink: 0;
          text-shadow: 0 1px 2px rgba(0,0,0,0.35);
        }
        .side-a .arena-avatar { background: linear-gradient(135deg, var(--agent1), #059669); box-shadow: 0 0 0 3px var(--surface), 0 0 0 4px var(--agent1); }
        .side-b .arena-avatar { background: linear-gradient(135deg, var(--agent2), #e11d48); box-shadow: 0 0 0 3px var(--surface), 0 0 0 4px var(--agent2); }
        .side-a { color: var(--agent1-text); }
        .side-b { color: var(--agent2-text); }
        .arena-name { display: flex; flex-direction: column; line-height: 1.15; }
        .arena-name small { font-weight: 500; font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
        .vs-badge {
          flex-shrink: 0;
          width: 42px; height: 42px;
          border-radius: 50%;
          background: linear-gradient(135deg, var(--accent), var(--accent-2));
          color: white;
          display: flex; align-items: center; justify-content: center;
          font-weight: 800; font-size: 0.8rem;
          box-shadow: 0 0 0 4px var(--surface), var(--shadow);
          z-index: 1;
        }

        #live { margin-top: 1.5rem; }

        .card {
          background: var(--surface);
          border: 1px solid var(--border);
          border-radius: 16px;
          box-shadow: var(--shadow);
          overflow: hidden;
        }

        .controls {
          display: flex;
          gap: 0.6rem;
          align-items: center;
          flex-wrap: wrap;
          padding: 1rem 1.25rem;
          border-bottom: 1px solid var(--border);
          background: var(--surface-2);
        }
        select, button {
          font-size: 0.9rem;
          font-family: inherit;
          padding: 0.55rem 1rem;
          border-radius: 9px;
          border: 1px solid transparent;
        }
        button {
          cursor: pointer;
          background: var(--accent);
          color: white;
          border: none;
          font-weight: 600;
          transition: filter 0.15s ease, transform 0.05s ease;
        }
        button:hover:not(:disabled) { filter: brightness(1.08); }
        button:active:not(:disabled) { transform: scale(0.98); }
        button:disabled { background: #3a3f4f; cursor: not-allowed; }
        #stopBtn { background: var(--danger); }
        #stopBtn:disabled { background: #3a3f4f; }
        .status-dot {
          width: 8px; height: 8px; border-radius: 50%;
          background: #3a3f4f; display: inline-block; margin-right: 0.4rem;
        }
        .status-dot.live { background: #22c55e; animation: pulse 1.4s ease-in-out infinite; }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }
        .status-text { font-size: 0.85rem; color: var(--text-muted); font-weight: 500; }

        #liveTranscript {
          padding: 1.5rem 1.25rem;
          min-height: 320px;
          max-height: 65vh;
          overflow-y: auto;
        }
        #liveTranscript:empty::before {
          content: 'No conversation yet. Press Start to let them talk.';
          color: var(--text-muted);
          font-size: 0.9rem;
          display: block;
          text-align: center;
          padding: 3rem 0;
        }

        .row { display: flex; align-items: flex-end; gap: 0.55rem; margin: 1.1rem 0; width: 100%; }
        .row.A { justify-content: flex-start; }
        .row.B { justify-content: flex-end; flex-direction: row-reverse; }
        .avatar {
          width: 32px; height: 32px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: 0.85rem; font-weight: 800; color: #ffffff;
          flex-shrink: 0;
          box-shadow: 0 2px 6px rgba(0,0,0,0.3);
          text-shadow: 0 1px 2px rgba(0,0,0,0.35);
        }
        .row.A .avatar { background: linear-gradient(135deg, var(--agent1), #059669); }
        .row.B .avatar { background: linear-gradient(135deg, var(--agent2), #e11d48); }

        .msg {
          max-width: 92%;
          padding: 0.7rem 1.05rem;
          border-radius: 18px;
          opacity: 0;
          animation: fadein 0.25s forwards;
          white-space: pre-wrap;
          line-height: 1.55;
          font-size: 0.95rem;
          position: relative;
          box-shadow: 0 1px 2px rgba(16,24,40,0.04);
        }
        @keyframes fadein { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }

        /* Speech-bubble tails, pointing at each agent's avatar */
        .msg::after {
          content: '';
          position: absolute;
          bottom: 0;
          width: 14px; height: 14px;
        }
        .row.A .msg {
          background: var(--agent1-bg);
          border: 1px solid var(--agent1-border);
          border-bottom-left-radius: 4px;
          font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, sans-serif;
        }
        .row.A .msg::after {
          left: -7px;
          background: var(--agent1-bg);
          border-left: 1px solid var(--agent1-border);
          border-bottom: 1px solid var(--agent1-border);
          border-radius: 0 0 0 12px;
          clip-path: polygon(0 0, 100% 100%, 0 100%);
        }
        .row.B .msg {
          background: var(--agent2-bg);
          border: 1px solid var(--agent2-border);
          border-bottom-right-radius: 4px;
          font-family: Georgia, 'Times New Roman', serif;
        }
        .row.B .msg::after {
          right: -7px;
          background: var(--agent2-bg);
          border-right: 1px solid var(--agent2-border);
          border-bottom: 1px solid var(--agent2-border);
          border-radius: 0 0 12px 0;
          clip-path: polygon(100% 0, 100% 100%, 0 100%);
        }

        .msg .who { font-weight: 700; font-size: 0.72rem; display: block; margin-bottom: 0.3rem; text-transform: uppercase; letter-spacing: 0.05em; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Inter, Roboto, sans-serif; }
        .row.A .who { color: var(--agent1-text); }
        .row.B .who { color: var(--agent2-text); }
        .msg .cursor { display: inline-block; width: 0.5em; animation: blink 0.9s steps(1) infinite; }
        @keyframes blink { 50% { opacity: 0; } }

        .divider {
          text-align: center; color: var(--text-muted); font-size: 0.8rem;
          margin: 1.25rem 0 0.75rem; font-style: italic; position: relative;
        }

        .verdict { font-weight: 600; margin: 1rem 1.25rem; padding: 0.75rem 1rem; border-radius: 10px; font-size: 0.9rem; }
        .caved { background: var(--agent2-bg); color: var(--agent2-text); }
        .held { background: var(--agent1-bg); color: var(--agent1-text); }
        .qtext { padding: 0.7rem 1rem; background: var(--surface-2); border-radius: 8px; margin: 0 1.25rem 0.5rem; font-size: 0.85rem; color: var(--text-muted); }

        ::-webkit-scrollbar { width: 8px; }
        ::-webkit-scrollbar-thumb { background: #3a3f4f; border-radius: 8px; }
      </style>
    </head>
    <body>
      <div class="page">
        <div class="hero">
          <h1>CaveOrHold</h1>
          <p class="sub">Two AI agents strike up a conversation— they pick the topic, take their own sides, and let the argument build on its own </p>
        </div>

        <div class="arena">
          <div class="arena-side side-a">
            <div class="arena-name"><small>Agent</small>One</div>
            <div class="arena-avatar">1</div>
          </div>
          <div class="vs-badge">VS</div>
          <div class="arena-side side-b">
            <div class="arena-avatar">2</div>
            <div class="arena-name"><small>Agent</small>Two</div>
          </div>
        </div>

        <div id="live" class="panel active">
          <div class="card">
            <div class="controls">
              <button id="startBtn">Start Live Debate</button>
              <button id="stopBtn" disabled>Stop</button>
              <span style="flex:1"></span>
              <span id="statusText" class="status-text"><span id="statusDot" class="status-dot"></span>Idle</span>
            </div>
            <div id="liveQuestion" class="qtext" style="display:none;"></div>
            <div id="liveTranscript"></div>
            <div id="liveVerdict" class="verdict" style="display:none;"></div>
          </div>
        </div>
      </div>

      <script>

        function makeAvatar(speaker) {
          const av = document.createElement('div');
          av.className = 'avatar';
          av.textContent = speaker === 'A' ? '1' : '2';
          return av;
        }

        // Only auto-scroll if the user is already near the bottom — otherwise a manual
        // scroll-up gets fought and dragged back down on every streamed character.
        function isNearBottom(container) {
          return container.scrollHeight - container.scrollTop - container.clientHeight < 120;
        }

        function startBubble(container, speaker, round) {
          const stick = isNearBottom(container);
          const row = document.createElement('div');
          row.className = `row ${speaker}`;
          const div = document.createElement('div');
          div.className = 'msg';
          const label = speaker === 'A' ? 'Agent 1' : 'Agent 2';
          div.innerHTML = `<span class="who">${label}</span><span class="text"></span><span class="cursor">▍</span>`;
          row.appendChild(makeAvatar(speaker));
          row.appendChild(div);
          container.appendChild(row);
          if (stick) row.scrollIntoView({ behavior: 'smooth', block: 'end' });
          return div;
        }

        function addDivider(container, text) {
          const stick = isNearBottom(container);
          const div = document.createElement('div');
          div.className = 'divider';
          div.textContent = text;
          container.appendChild(div);
          if (stick) div.scrollIntoView({ behavior: 'smooth', block: 'end' });
        }

        const TYPE_SPEED_MS = 45; // ms per character (slower, readable typing speed)

        // Serializes display so that agent B's reply never starts revealing until agent A's
        // previous reply has fully finished typing out (and vice versa), regardless of how
        // fast the underlying chunks actually arrive over the websocket.
        function createLiveRenderer(container) {
          const queue = [];
          let cursorIndex = 0;
          let onAllDone = null;
          let locked = false; // true once the user has requested a stop: ignore anything further
          const timer = setInterval(tick, TYPE_SPEED_MS);

          function findOpenMessage(speaker, round) {
            for (let i = queue.length - 1; i >= 0; i--) {
              const m = queue[i];
              if (m.speaker === speaker && m.round === round && !m.closed) return m;
            }
            const m = { speaker, round, text: '', closed: false, bubbleCreated: false, revealed: 0 };
            queue.push(m);
            return m;
          }

          function pushChunk(speaker, round, delta) {
            if (locked) return;
            findOpenMessage(speaker, round).text += delta;
          }

          function closeMessage(speaker, round) {
            if (locked) return;
            findOpenMessage(speaker, round).closed = true;
          }

          function tick() {
            if (cursorIndex >= queue.length) return;
            const m = queue[cursorIndex];
            if (!m.bubbleCreated) {
              m.bubbleEl = startBubble(container, m.speaker, m.round);
              m.bubbleCreated = true;
            }
            if (m.revealed < m.text.length) {
              const stick = isNearBottom(container);
              const span = m.bubbleEl.querySelector('.text');
              span.textContent += m.text[m.revealed];
              m.revealed++;
              if (stick) container.scrollTop = container.scrollHeight;
            } else if (m.closed) {
              const cursor = m.bubbleEl.querySelector('.cursor');
              if (cursor) cursor.remove();
              cursorIndex++;
              if (cursorIndex >= queue.length && onAllDone) {
                onAllDone();
                onAllDone = null;
              }
            }
          }

          function requestAllDone(callback) {
            if (cursorIndex >= queue.length) {
              callback();
            } else {
              onAllDone = callback;
            }
          }

          // Finishes typing out whatever message is currently on screen, then stops — discarding
          // any later messages already sitting in the queue (buffered ahead of the display) and
          // ignoring anything the server sends afterward (its current round may still be tailing off).
          function requestStopAfterCurrent(callback) {
            if (locked) return;
            locked = true;
            if (cursorIndex < queue.length) {
              queue.length = cursorIndex + 1;
            }
            requestAllDone(callback);
          }

          function stop() {
            clearInterval(timer);
          }

          return { pushChunk, closeMessage, requestAllDone, requestStopAfterCurrent, stop };
        }

        let liveWs = null;
        let liveRenderer = null;
        let liveGeneration = 0; // guards against a stale/leftover connection still streaming into the DOM

        function setStatus(live, text) {
          document.getElementById('statusDot').className = 'status-dot' + (live ? ' live' : '');
          document.getElementById('statusText').lastChild.textContent = text;
        }

        function resetButtons() {
          const startBtn = document.getElementById('startBtn');
          const stopBtn = document.getElementById('stopBtn');
          startBtn.disabled = false;
          startBtn.textContent = '▶️ Start Live Debate';
          stopBtn.disabled = true;
          stopBtn.textContent = 'Stop';
          setStatus(false, 'Idle');
        }

        function startLiveDebate() {
          // If a previous session's socket is still open (e.g. a stray double-click), kill it
          // so it can't keep streaming into the transcript alongside the new one.
          if (liveWs) {
            try { liveWs.onmessage = null; liveWs.onerror = null; liveWs.close(); } catch (e) {}
            liveWs = null;
          }
          const myGeneration = ++liveGeneration;

          const startBtn = document.getElementById('startBtn');
          const stopBtn = document.getElementById('stopBtn');
          const transcript = document.getElementById('liveTranscript');
          const verdict = document.getElementById('liveVerdict');
          const qDiv = document.getElementById('liveQuestion');

          transcript.innerHTML = '';
          verdict.style.display = 'none';
          qDiv.style.display = 'none';
          startBtn.disabled = true;
          startBtn.textContent = 'Debate in progress...';
          stopBtn.disabled = false;
          setStatus(true, 'Live');

          const proto = location.protocol === 'https:' ? 'wss' : 'ws';
          const ws = new WebSocket(`${proto}://${location.host}/ws/live`);
          liveWs = ws;

          const renderer = createLiveRenderer(transcript);
          liveRenderer = renderer;

          const finishStop = () => {
            addDivider(transcript, 'Argument stopped.');
            resetButtons();
            renderer.stop();
            try { ws.close(); } catch (e) {}
            liveWs = null;
            liveRenderer = null;
          };

          ws.onmessage = (ev) => {
            if (myGeneration !== liveGeneration) return; // stale connection, ignore
            const data = JSON.parse(ev.data);
            if (data.type === 'start') {
              // Agents pick their own topic — nothing to show here until Agent 1 opens.
            } else if (data.type === 'chunk') {
              renderer.pushChunk(data.speaker, data.round, data.delta);
            } else if (data.type === 'message_done') {
              renderer.closeMessage(data.speaker, data.round);
            } else if (data.type === 'stopped') {
              // Fallback in case this arrives before the user's own click already handled it.
              renderer.requestStopAfterCurrent(finishStop);
            } else if (data.type === 'error') {
              verdict.className = 'verdict caved';
              verdict.textContent = 'Error: ' + data.message;
              verdict.style.display = 'block';
              resetButtons();
              renderer.stop();
              liveWs = null;
              liveRenderer = null;
            }
          };

          ws.onerror = () => {
            if (myGeneration !== liveGeneration) return; // stale connection, ignore
            resetButtons();
            renderer.stop();
            liveWs = null;
            liveRenderer = null;
          };
        }

        function stopLiveDebate() {
          if (!liveWs) return;
          document.getElementById('stopBtn').disabled = true;
          document.getElementById('stopBtn').textContent = '⏳ Stopping...';
          setStatus(true, '⏳ Stopping…');
          // Tell the server to stop generating further rounds...
          if (liveWs.readyState === WebSocket.OPEN) {
            liveWs.send(JSON.stringify({ action: 'stop' }));
          }
          // ...and immediately cut the display to whatever is on screen right now, instead of
          // waiting for the server's ack (which could be many buffered rounds behind).
          if (liveRenderer) {
            const transcript = document.getElementById('liveTranscript');
            const wsRef = liveWs;
            liveRenderer.requestStopAfterCurrent(() => {
              addDivider(transcript, '🛑 Argument stopped.');
              resetButtons();
              liveRenderer.stop();
              try { wsRef.close(); } catch (e) {}
              liveWs = null;
              liveRenderer = null;
            });
          }
        }

        document.getElementById('stopBtn').addEventListener('click', stopLiveDebate);

        document.getElementById('startBtn').addEventListener('click', startLiveDebate);
      </script>
    </body>
    </html>
    """
