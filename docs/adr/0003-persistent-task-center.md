# ADR 0003: Persistent local task center and bounded history

- Status: accepted for M1
- Date: 2026-08-10

## Context

Document and video conversions can run for minutes, invoke several external programs, and fail
independently. The desktop application needs per-file progress, cancellation, retry, crash recovery,
and long-lived history without requiring a server or storing users' document contents.

The application remains a single-user Windows desktop tool. It intentionally does not implement
distributed workers, cloud queues, accounts, or parallel media encoding.

## Decision

### Queue execution

Use a typed in-process scheduler that executes queued items sequentially and isolates each failure.
Sequential execution avoids multiple Office COM sessions and prevents simultaneous FFmpeg jobs from
unexpectedly exhausting CPU, memory, or disk bandwidth. Every item uses the same cancellation token
from the UI through the service and converter layers to the process adapter.

FFmpeg's supported `-progress pipe:1` protocol is streamed through the process adapter. The program
parses `out_time_us` against ffprobe duration rather than scraping human console output. When duration
cannot be read, stage progress and FFmpeg's final `progress=end` remain available.

### Persistence

Persist only recoverable queue state in a versioned UTF-8 JSON file under application data. Writes go
to a sibling temporary file and commit with `os.replace`, so a crash retains either the previous or
new complete state. A corrupt state file is quarantined instead of preventing startup. `running`
items load as `interrupted`; no conversion is silently resumed.

SQLite was considered. It is mature and part of Python, but the queue has one writer, a bounded number
of small records, and no relational query requirement. Atomic JSON keeps the file inspectable and
reduces migration surface. Reconsider SQLite if later requirements introduce concurrent writers or
thousands of active queue items.

Celery, RQ, Redis, and similar server-oriented queues were rejected because they require services and
deployment concepts that conflict with the local-first Windows product boundary.

### History and deletion boundaries

Completed task history remains separate from recoverable queue state. Each central manifest records
paths, timestamps, attempts, operation parameters, status, and detected tool versions, but never the
document body or extracted private text.

History search reads these bounded manifests. Retention and capacity cleanup remove oldest record
folders only. Source files and formal outputs can be referenced but are never deletion targets.
Preview caches live under the application cache root and require a separate explicit confirmation.
Resolved-path containment checks prevent a manifest from deleting a cache path outside that root.

### Disk safety

Before starting a batch, estimate output size using conservative operation-specific factors and retain
a configurable free-space margin. An insufficient-space result leaves tasks waiting and does not call
the converter. Estimates are intentionally warnings/guards rather than exact promises because media
compression depends on source content.

## Consequences

- The queue is deterministic, recoverable, testable without Qt, and safe for paths containing spaces
  or Chinese characters.
- A single long task delays later tasks, which is deliberate for M1. Controlled concurrency can be a
  future decision only with resource limits and Office-specific exclusion.
- In-process MarkItDown and local OCR cannot always be interrupted in the middle of a Python call; the
  token is checked before and after those stages, while external tools can be terminated immediately.
- History scans are linear in the bounded history directory. The 90-day/512-MB defaults keep that cost
  predictable; a database index can be introduced later if real usage demonstrates a need.
