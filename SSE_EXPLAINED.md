# How live progress works (SSE) — simple explanation

## What is SSE?

**SSE (Server-Sent Events)** is a way for the server to **keep talking to the browser** over one open connection, instead of answering only once at the end.

Think of ordering food:

- **Without SSE:** you order, then stare at the counter for 2 minutes with no idea what's happening, until the food suddenly appears.
- **With SSE:** you order, and the staff call out *"cooking… packing… ready!"* as each step happens.

In this app, SSE is what shows the **live checklist with timers** while a video is being analyzed.

---

## The big picture

```
        +----------------------------+
        |  You click "Analyze Video" |
        +-------------+--------------+
                      |
                      v
        +----------------------------+
        | Browser sends the video    |
        | to the backend             |
        +-------------+--------------+
                      |
                      v
        +----------------------------+
        | Backend starts working and |
        | keeps the connection open  |
        +-------------+--------------+
                      |
                      v
        +----------------------------+
   +--->| A step starts: backend     |
   |    | sends a short message      |
   |    +-------------+--------------+
   |                  |
   |                  v
   |    +----------------------------+
   |    | Browser adds a line to the |
   |    | checklist (with a timer)   |
   |    +-------------+--------------+
   |                  |
   |        more steps?
   +------- yes ------+
                      | no
                      v
        +----------------------------+
        | Backend sends the finished |
        | roadmap, connection closes |
        +-------------+--------------+
                      |
                      v
        +----------------------------+
        | Browser shows the results  |
        +----------------------------+
```

---

## Keep-alive

While the backend is waiting on the AI (which can take a while), it sends a tiny **keep-alive** message every 15 seconds. It isn't shown to you — it just stops the network from thinking the connection is dead and closing it.

---

## What the messages look like

The backend sends plain text lines like these, one at a time:

```
data: {"type": "progress", "step": "analyze", "message": "Watching the video and building your roadmap…"}

: keep-alive

data: {"type": "progress", "step": "resources", "message": "Finding related videos for each topic…"}

data: {"type": "progress", "step": "save", "message": "Saving to your history…"}

data: {"type": "result", "data": { ...the roadmap... }}
```

There are only **3 kinds** of messages:

| Type | Meaning | What the browser does |
|---|---|---|
| `progress` | "I've started a new step" | Ticks the previous step, adds the new one with a timer |
| `result` | "All done, here's the roadmap" | Shows the results |
| `error` | "Something went wrong" (with a plain message) | Shows the error |

---

## What happens inside the backend

The backend does two things **at the same time**:

```
   WORKER (does the analysis)             SENDER (talks to the browser)
   --------------------------             -----------------------------

   +------------------------+
   | Analyze video with AI  |--progress--+
   +-----------+------------+            |
               v                         |
   +------------------------+            |
   | Find related videos    |--progress--+
   +-----------+------------+            |       +------------------------+
               v                         +------>|  MESSAGE BOX (queue)   |
   +------------------------+            |       +-----------+------------+
   | Save to history        |--progress--+                   |
   +-----------+------------+            |                   v
               v                         |       +------------------------+
   +------------------------+            |  +--->| Anything new in box?   |
   | Put result in the box  |--result----+  |    +--+---------+--------+--+
   +------------------------+               |       |         |        |
                                            |      yes    nothing   finished
                                            |       |     for 15 s     |
                                            |       v         v        v
                                            |  +---------+ +--------+ +---------+
                                            |  | Send it | | Send   | | Close   |
                                            |  | to the  | | keep-  | | the     |
                                            |  | browser | | alive  | | connec- |
                                            |  +----+----+ +---+----+ | tion    |
                                            |       |          |      +---------+
                                            +-------+----------+
```

- The **worker** drops a message into a **box** (a queue) every time it starts a step.
- The **sender** takes messages out of the box and sends them to the browser as they arrive.
- The whole analysis has a **4-minute limit**. If it runs out, the sender sends an `error` message instead of the result.

---

## Where it is in the code

### Backend — `backend/main.py`

| What | Where |
|---|---|
| The live-progress address the browser calls | `@app.post("/api/analyze/stream")` → `analyze_video_stream()` |
| The analysis steps (the worker) | `_analysis_pipeline()` |
| Putting a progress message in the box | `emit()` |
| Running the work with the 4-minute limit | `run()` |
| Sending messages + keep-alives (the sender) | `events()` |
| Telling the browser "this is a live stream" | `StreamingResponse(..., media_type="text/event-stream")` |
| Keep-alive interval | `SSE_KEEPALIVE_SECONDS = 15` |

### Frontend — `frontend/src/routes/+page.svelte`

| What | Where |
|---|---|
| Sending the video and opening the stream | `handleAnalyze()` |
| Reading the messages one by one | `readAnalyzeStream()` |
| Updating the checklist and timers | `addProgress()` |
| The checklist you see | `<ol class="progress-steps">` |
| Backup if the backend is an older version | falls back to `/api/analyze` (no live progress) |

> **Why not the browser's built-in `EventSource`?**
> `EventSource` can only *fetch* data — it can't *upload* a video file or send your login token. So the page uses a normal `fetch()` and reads the stream itself. The messages are still standard SSE.

---

## One more place SSE appears (you don't need to touch it)

The backend talks to its **MCP tool server** using MCP's "streamable HTTP" connection, which can also use SSE behind the scenes. That's handled entirely by the MCP library:

- Server: `backend/mcp_server/video_details_server.py` → `mcp.run(transport="streamable-http", ...)`
- Client: `backend/services/mcp_client.py` → `streamable_http_client(...)`

That's why you see `GET /mcp` and `POST /mcp` lines in the backend logs.

---

## Summary in one line

**The browser asks once, the backend replies many times** — one short message per step — so you can watch the analysis happen live instead of waiting in silence.
