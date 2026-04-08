# Mini-Splunk: Concurrent Syslog Analytics Server

A high-performance, thread-safe syslog analytics server with RFC 3164 and RFC 5424 support, built for concurrent log ingestion and distributed querying.

**Course:** NSAPDEV | S31/S12B  
**Authors:** Joshua Benedict B. Co and Reyvin Matthew T. Tan

---

## Overview

Mini-Splunk is a concurrent TCP syslog server that enables multiple clients to simultaneously upload log files and query them using a rich set of search filters. The server uses a thread-per-connection architecture with reentrant locking to ensure thread-safe log storage and retrieval.

### Key Features

- **Concurrent Architecture**: Thread-per-connection model handles multiple clients simultaneously
- **RFC 3164 & RFC 5424 Support**: Parses both BSD syslog and modern IETF syslog formats
- **Intelligent Severity Inference**: Extracts severity from PRI fields or infers from message content using keyword matching
- **Advanced Query Engine**: Search logs by date, hostname, daemon, severity level, or keyword
- **Pagination Support**: Query results are paginated with metadata for easy navigation
- **Memory-Efficient Upload**: Streams file content in 4KB chunks—no limit on log file size
- **Thread-Safe Operations**: Uses `threading.RLock()` to protect all shared data access

---

## Architecture

### Core Modules

#### 1. **Data Storage Module**
- Maintains a shared global log list protected by a reentrant lock
- Operations: `append_logs()`, `purge_logs()`, `get_snapshot()`

#### 2. **Parsing Module**
- **RFC 3164 Parser**: Handles traditional BSD syslog format
  - Format: `Mmm dd hh:mm:ss hostname tag[pid]: message`
  - Flexible timestamp parsing with optional space variations
  
- **RFC 5424 Parser**: Handles modern IETF syslog format
  - Format: `<PRI>VERSION TIMESTAMP HOSTNAME APPNAME PROCID MSGID STRUCTURED-DATA [MSG]`
  - ISO 8601 timestamps with optional fractional seconds and timezone
  
- **Severity Resolution**: Two-tier approach
  1. Extract from PRI field if present (bits 0-2 of priority value)
  2. Fall back to keyword inference scanning the message text

#### 3. **Query Engine**
- Five search filters: date, hostname, daemon, severity, keyword
- Count operation for keyword frequency analysis
- Thread-safe snapshot-based queries

#### 4. **Connection Handler**
- `recv_message()`: Reads length-prefixed commands from clients
- Handles both simple commands and multi-megabyte file uploads
- Dispatches to specialized processors: `process_upload()`, `process_query()`, `process_admin()`

#### 5. **Network Module**
- TCP server bound to `0.0.0.0:8080` (configurable)
- Spawn a daemon thread per accepted connection
- Graceful shutdown on Ctrl+C

---

## Installation & Requirements

### Prerequisites

- Python 3.7+
- Standard library only (no external dependencies)
  - `socket`
  - `threading`
  - `re`
  - `json`
  - `io`

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd NSAPDEV_Mini-Splunk

# Run the server
python server_cotan15.py

# In another terminal, run the client
python client_cotan15.py
```

---

## Usage

### Server

**Start the server:**

```bash
python server_cotan15.py
```

The server listens on `0.0.0.0:8080` by default. Configuration constants at the top of the file:

```python
HOST = "0.0.0.0"
PORT = 8080
RESULTS_PER_PAGE = 100
```

### Client CLI

The client provides a command-line interface for uploading logs and querying the server.

**Start the client:**

```bash
python client_cotan15.py
```

Default remote server: `103.231.240.136:11334` (configurable in code)

#### Available Commands

##### Upload Logs
```
INGEST <filepath> <IP_or_DNS>:<Port>
```
Example:
```
mini-splunk> INGEST ./syslogs/demo/sample1.txt 127.0.0.1:8080
```

##### Search Queries

**Search by date:**
```
QUERY <IP_or_DNS>:<Port> SEARCH_DATE <date>
```
Example: `QUERY 127.0.0.1:8080 SEARCH_DATE "Feb 22"`

**Search by hostname:**
```
QUERY <IP_or_DNS>:<Port> SEARCH_HOST <hostname>
```
Example: `QUERY 127.0.0.1:8080 SEARCH_HOST SYSSVR1`

**Search by daemon:**
```
QUERY <IP_or_DNS>:<Port> SEARCH_DAEMON <daemon>
```
Example: `QUERY 127.0.0.1:8080 SEARCH_DAEMON nginx`

**Search by severity:**
```
QUERY <IP_or_DNS>:<Port> SEARCH_SEVERITY <level>
```
Levels: `EMERG`, `ALERT`, `CRIT`, `ERR`, `WARNING`, `NOTICE`, `INFO`, `DEBUG`  
Example: `QUERY 127.0.0.1:8080 SEARCH_SEVERITY ERR`

**Search by keyword:**
```
QUERY <IP_or_DNS>:<Port> SEARCH_KEYWORD <keyword_or_phrase>
```
Example: `QUERY 127.0.0.1:8080 SEARCH_KEYWORD "Failed password"`

**Count keyword occurrences:**
```
QUERY <IP_or_DNS>:<Port> COUNT_KEYWORD <keyword_or_phrase>
```
Example: `QUERY 127.0.0.1:8080 COUNT_KEYWORD error`

##### Administration
```
PURGE <IP_or_DNS>:<Port>
```
Clears all logs from the server store.

##### Other Commands
- `HELP` — Display available commands
- `EXIT` — Exit the CLI client

---

## Protocol Specification

### Message Format

All commands are pipe-delimited and newline-terminated.

#### Simple Commands
```
COMMAND|PARAM1|PARAM2|...\n
```

#### Upload Command
The server supports streaming uploads for arbitrary file sizes:
```
Header:  UPLOAD|<filesize>|\n
Body:    <filesize raw bytes of syslog content>
```

The server acknowledges each upload and processes the content immediately.

### Response Format

All responses use length-prefixed encoding to safely support multi-line payloads:
```
<byte_length>\n<response_body>
```

Query responses are JSON with pagination metadata:
```json
{
  "metadata": {
    "total_results": 150,
    "page": 1,
    "per_page": 100,
    "total_pages": 2,
    "has_next": true,
    "has_prev": false,
    "results_on_page": 100
  },
  "logs": "[timestamp] hostname daemon [severity] message\n..."
}
```

---

## RFC Syslog Formats

### RFC 3164 (BSD Syslog)
```
<PRI>Mmm dd hh:mm:ss hostname tag[pid]: message
```

**Supported characteristics:**
- Optional PRI field
- Flexible timestamp with 1-2 digit day (single-digit days may have 1-2 spaces after month)
- Daemon name with optional PID in square brackets
- Free-form message text

**Example:**
```
<34>Feb 22 10:15:30 SYSSVR1 sshd[12345]: Failed password for invalid user admin
```

### RFC 5424 (IETF Syslog)
```
<PRI>VERSION TIMESTAMP HOSTNAME APPNAME PROCID MSGID STRUCTURED-DATA [MSG]
```

**Supported characteristics:**
- Required PRI and VERSION (1-999)
- ISO 8601 timestamp with optional fractional seconds and timezone
- NILVALUE ("-") support for optional fields
- Structured data with bracket notation
- Optional message

**Example:**
```
<134>1 2024-02-22T10:15:30.123+05:30 SYSSVR1 nginx 12345 - - [exampleSDID@32473 requestID="12345"] GET /api/users HTTP/1.1 200
```

---

## Severity Levels

Severity is resolved using the PRI field (bits 0-2) or inferred from message keywords:

| Value | Level | Keyword Triggers |
|-------|-------|------------------|
| 0 | EMERG | emerg |
| 1 | ALERT | alert |
| 2 | CRIT | crit |
| 3 | ERR | error, err |
| 4 | WARNING | warning, warn |
| 5 | NOTICE | notice |
| 6 | INFO | info |
| 7 | DEBUG | debug |

If no PRI field is found, the message is scanned (case-insensitive) for the first matching keyword in order of specificity.

---

## Thread Safety

The server uses **`threading.RLock()`** (reentrant lock) to protect all access to the shared log store:

- **Write Operations**: `append_logs()`, `purge_logs()` acquire exclusive locks
- **Read Operations**: `get_snapshot()` returns a shallow copy under lock
- **Query Operations**: Always work on snapshots to avoid blocking writers

This design allows:
- Concurrent uploads from multiple clients
- Concurrent queries without blocking uploads
- Safe purge operations that don't corrupt active queries

---

## Performance Considerations

### Memory Usage
- **Upload streaming**: Log files are read in 4KB chunks, never fully loaded into RAM
- **Query snapshots**: Queries operate on shallow copies of the log store (list reference counts)
- **Pagination**: Results are sliced on-demand, not materialized for all results

### Throughput
- Each client connection runs in its own thread—no GIL contention for I/O
- Lock contention limited to brief `extend()` and `clear()` operations on the log list
- Suitable for hundreds of concurrent connections on modern hardware

---

## Example Workflow

1. **Start the server:**
   ```bash
   python server_cotan15.py
   ```

2. **Start the client:**
   ```bash
   python client_cotan15.py
   ```

3. **Upload logs:**
   ```
   mini-splunk> INGEST ./syslogs/demo/sample1.txt 127.0.0.1:8080
   [INGEST] Successfully parked 523 entries
   ```

4. **Query logs:**
   ```
   mini-splunk> QUERY 127.0.0.1:8080 SEARCH_HOST SYSSVR1
   ```
   Navigate pages with `[N]ext`, `[P]revious`, or `[E]xit`.

5. **Count occurrences:**
   ```
   mini-splunk> QUERY 127.0.0.1:8080 COUNT_KEYWORD "Failed"
   [COUNT_KEYWORD] Entries containing 'Failed': 45
   ```

6. **Clear all logs:**
   ```
   mini-splunk> PURGE 127.0.0.1:8080
   [PURGE] All log entries have been cleared.
   ```

---

## License

Course project for NSAPDEV | S31/S12B | A.Y. 2025-2026

---

## Authors

- **Joshua Benedict B. Co**
- **Reyvin Matthew T. Tan**

