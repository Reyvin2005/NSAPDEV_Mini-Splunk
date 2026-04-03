"""
Mini-Splunk Concurrent Syslog Analytics Server
Course & Section: NSAPDEV | S12B/S31
Authors: Joshua Benedict B. Co and Reyvin Matthew T. Tan

Architecture: Thread-per-Connection TCP server.

The main thread accepts connections and spawns a worker thread for each client.
threading.RLock() protects all writes and reads on the shared log store.
"""

import socket
import threading
import re
import json


HOST = "0.0.0.0"
PORT = 9514
RESULTS_PER_PAGE = 100

SEVERITY_MAP = {
    0: "EMERG",
    1: "ALERT",
    2: "CRIT",
    3: "ERR",
    4: "WARNING",
    5: "NOTICE",
    6: "INFO",
    7: "DEBUG",
}


# ============================================================
# Data Storage Module
# Manages the shared global log list and all locking logic.
# ============================================================

log_store = []
store_lock = threading.RLock()


def append_logs(entries):
    """Acquire write lock and extend the log store with new entries."""
    with store_lock:
        log_store.extend(entries)


def purge_logs():
    """Acquire exclusive write lock and clear the entire log store."""
    with store_lock:
        log_store.clear()


def get_snapshot():
    """Acquire read lock and return a shallow copy of the log store."""
    with store_lock:
        return list(log_store)


# ============================================================
# Parsing Module
# Supports RFC 3164 and RFC 5424 with relaxed whitespace handling
# ============================================================

# RFC 3164 – BSD syslog
# TIMESTAMP: "Mmm dd hh:mm:ss" where day may be 1-2 digits,
#            single-digit days may have one or two spaces after month.
#            Allow optional leading/trailing spaces.
RFC3164_REGEX = re.compile(
    r"^\s*"                                      # optional leading spaces
    r"(?:<(?P<pri>\d{1,3})>\s*)?"                # optional PRI, allow space after >
    r"(?P<timestamp>"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+"                                   # at least one space after month
        r"\d{1,2}"                               # day (1 or 2 digits)
        r"\s+"                                   # at least one space after day
        r"\d{1,2}:\d{2}:\d{2}"                   # time (hour can be 1-2 digits)
    r")\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<tag>[a-zA-Z0-9_./-]+)"                 # TAG - allow alnum, dot, slash, hyphen, underscore
    r"(?:\[(?P<pid>\d+)\])?"                     # optional [PID]
    r":\s*"
    r"(?P<msg>.*)$"
)

# RFC 5424 – modern syslog
# VERSION must be 1-3 digits.
# TIMESTAMP: NILVALUE '-' or ISO 8601 with optional fractional seconds and timezone.
# STRUCTURED-DATA: NILVALUE '-' or one or more '[name value pairs]'.
RFC5424_REGEX = re.compile(
    r"^\s*"                                      # optional leading spaces
    r"(?:<(?P<pri>\d{1,3})>)"                   # PRI (mandatory)
    r"(?P<version>[1-9]\d{0,2})\s+"             # VERSION
    r"(?P<timestamp>"
        r"-|"                                    # NILVALUE
        r"\d{4}-\d{2}-\d{2}T"
        r"\d{2}:\d{2}:\d{2}"
        r"(?:\.\d{1,6})?"                       # optional fractional seconds
        r"(?:Z|[+-]\d{2}:\d{2})"                # timezone
    r")\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<appname>\S+)\s+"
    r"(?P<procid>\S+)\s+"
    r"(?P<msgid>\S+)\s+"
    r"(?P<structured_data>"
        r"-|"                                    # NILVALUE
        r"(?:\[(?:\\.|[^\\\]])*\])+"            # one or more structured data elements
    r")"
    r"(?:\s+(?P<msg>.*))?$"                     # optional SP + MSG (free-form)
)

def parse_pri(priority_str):
    """Convert PRI (0..191) into severity using the low 3 bits."""
    if priority_str is None:
        return "INFO"
    try:
        priority = int(priority_str)
    except ValueError:
        return "INFO"
    severity_num = priority & 0x07
    return SEVERITY_MAP.get(severity_num, "UNKNOWN")

def parse_line(line):
    """
    Parse one syslog line as RFC 5424 first, then RFC 3164.
    Returns a dict with fields: timestamp, hostname, daemon, severity, message,
    format, structured_data (or None), raw.
    Returns None for non‑matching lines.
    """
    line = line.rstrip("\n\r")                  # remove newline and carriage return
    if not line.strip():
        return None

    # Try RFC 5424
    m = RFC5424_REGEX.match(line)
    if m:
        appname = m.group("appname")
        # Keep daemon normalized for stable SEARCH_DAEMON matching.
        daemon = appname

        return {
            "timestamp": m.group("timestamp"),
            "hostname": m.group("hostname"),
            "daemon": daemon,
            "severity": parse_pri(m.group("pri")),
            "message": m.group("msg") or "",
            "format": "RFC5424",
            "structured_data": m.group("structured_data"),
            "raw": line,
        }

    # Try RFC 3164
    m = RFC3164_REGEX.match(line)
    if m:
        tag = m.group("tag")
        daemon = tag

        return {
            "timestamp": m.group("timestamp"),
            "hostname": m.group("hostname"),
            "daemon": daemon,
            "severity": parse_pri(m.group("pri")),
            "message": m.group("msg") or "",
            "format": "RFC3164",
            "structured_data": None,
            "raw": line,
        }

    # If we reach here, the line didn't match either format.
    # Optionally log the failure for debugging (print or use logging)
    # print(f"DEBUG: Failed to parse: {line[:80]}")
    return None

def parse_stream(content):
    """Parse a multi-line syslog string and return a list of log dictionaries."""
    entries = []
    for line in content.splitlines():
        entry = parse_line(line)
        if entry:
            entries.append(entry)
    return entries


# ============================================================
# Query Engine Module
# All filter functions read from a snapshot to remain thread-safe.
# ============================================================

def format_entries(entries):
    """Format a list of log dictionaries into a human-readable string."""
    if not entries:
        return "NO_RESULTS"
    lines = [
        f"[{e['timestamp']}] {e['hostname']} {e['daemon']}"
        f" [{e['severity']}] {e['message']}"
        for e in entries
    ]
    return "\n".join(lines)


def normalize_whitespace(text):
    """Collapse repeated whitespace so date queries can match padded timestamps."""
    return re.sub(r"\s+", " ", text).strip().lower()


def format_paginated_response(all_results, page=1, per_page=RESULTS_PER_PAGE):
    """
    Format query results with pagination metadata.
    Returns a JSON response containing metadata and paginated results.
    """
    total = len(all_results)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    
    # Ensure page is valid
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_results = all_results[start_idx:end_idx]
    
    has_next = page < total_pages
    has_prev = page > 1
    
    metadata = {
        "total_results": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_prev": has_prev,
        "results_on_page": len(page_results),
    }
    
    formatted_logs = format_entries(page_results)
    
    return json.dumps({
        "metadata": metadata,
        "logs": formatted_logs,
    })


def search_by_date(date, page=1):
    needle = normalize_whitespace(date)
    results = [
        e for e in get_snapshot()
        if needle in normalize_whitespace(e["timestamp"])
    ]
    return format_paginated_response(results, page)


def search_by_host(hostname, page=1):
    needle = hostname.strip().lower()
    results = [
        e for e in get_snapshot()
        if e["hostname"].strip().lower() == needle
    ]
    return format_paginated_response(results, page)


def search_by_daemon(daemon, page=1):
    needle = daemon.strip().lower()
    results = [
        e for e in get_snapshot()
        if e["daemon"].strip().lower() == needle
    ]
    return format_paginated_response(results, page)


def search_by_severity(level, page=1):
    needle = level.strip().upper()
    results = [
        e for e in get_snapshot()
        if e["severity"].strip().upper() == needle
    ]
    return format_paginated_response(results, page)


def search_by_keyword(word, page=1):
    needle = word.strip().lower()
    results = [
        e for e in get_snapshot()
        if needle in e["message"].lower()
    ]
    return format_paginated_response(results, page)


def count_keyword(word):
    needle = word.strip().lower()
    total = sum(
        1 for e in get_snapshot()
        if needle in e["message"].lower()
    )
    return str(total)


# ============================================================
# Connection Handler
# Reads one request per connection and dispatches to the correct handler.
# ============================================================

def recv_message(conn):
    """
    Read a complete command message from the socket.

    For UPLOAD commands the protocol is:
        Header line:  UPLOAD|<filesize>|  followed by newline
        Body:         exactly <filesize> raw bytes of syslog content

    For all other commands:
        Single line ending with newline, e.g. QUERY|SEARCH_HOST|SYSSVR1
    """
    header_buf = b""
    while True:
        byte = conn.recv(1)
        if not byte or byte == b"\n":
            break
        header_buf += byte

    header_str = header_buf.decode("utf-8").strip()

    if not header_str.startswith("UPLOAD|"):
        return header_str

    # Parse the filesize from "UPLOAD|<N>|"
    second_pipe = header_str.index("|", 7)
    filesize = int(header_str[7:second_pipe])

    content_buf = b""
    while len(content_buf) < filesize:
        remaining = filesize - len(content_buf)
        chunk = conn.recv(min(4096, remaining))
        if not chunk:
            break
        content_buf += chunk

    content = content_buf.decode("utf-8")
    return f"UPLOAD|{filesize}|{content}"


def send_response(conn, response):
    """
    Send a length-prefixed response so multi-line payloads are received intact.
    Format: "<byte_length>\n<response_body>"
    """
    encoded = response.encode("utf-8")
    length_prefix = f"{len(encoded)}\n".encode("utf-8")
    conn.sendall(length_prefix)
    conn.sendall(encoded)


def process_command(message):
    """Route an incoming command string to the appropriate module function."""
    parts = message.split("|", 3)  # Allow up to 4 parts (command|type|param|page)
    if not parts or not parts[0]:
        return "ERROR: Empty command"

    command_type = parts[0].upper()

    if command_type == "UPLOAD":
        if len(parts) < 3:
            return "ERROR: Malformed UPLOAD command"
        try:
            content = parts[2]
            entries = parse_stream(content)
            append_logs(entries)
            return f"SUCCESS: Ingested {len(entries)} log entries into the store"
        except Exception as exc:
            return f"ERROR: {exc}"

    if command_type == "QUERY":
        if len(parts) < 3:
            return "ERROR: Malformed QUERY command"
        query_type = parts[1].upper()
        param = parts[2]
        
        # Extract page number if provided
        page = 1
        if len(parts) > 3:
            try:
                page = int(parts[3])
                if page < 1:
                    page = 1
            except ValueError:
                page = 1

        query_dispatch = {
            "SEARCH_DATE":     lambda: search_by_date(param, page),
            "SEARCH_HOST":     lambda: search_by_host(param, page),
            "SEARCH_DAEMON":   lambda: search_by_daemon(param, page),
            "SEARCH_SEVERITY": lambda: search_by_severity(param, page),
            "SEARCH_KEYWORD":  lambda: search_by_keyword(param, page),
            "COUNT_KEYWORD":   lambda: count_keyword(param),
        }

        handler = query_dispatch.get(query_type)
        if handler:
            return handler()
        return f"ERROR: Unknown query type '{query_type}'"

    if command_type == "ADMIN":
        if len(parts) < 2:
            return "ERROR: Malformed ADMIN command"
        admin_cmd = parts[1].upper()
        if admin_cmd == "PURGE":
            purge_logs()
            return "SUCCESS: Log store purged. All entries have been removed."
        return f"ERROR: Unknown admin command '{admin_cmd}'"

    return f"ERROR: Unknown command type '{command_type}'"


def handle_client(conn, addr):
    """Worker thread entry point. Handles one client connection."""
    client_id = f"{addr[0]}:{addr[1]}"
    print(f"[CONNECT]    {client_id}")
    try:
        message = recv_message(conn)
        if message:
            print(f"[COMMAND]    {client_id} -> {message[:80]}")
            response = process_command(message)
        else:
            response = "ERROR: Empty message received"
        send_response(conn, response)
        print(f"[RESPONSE]   {client_id} <- {response[:80]}")
    except Exception as exc:
        try:
            send_response(conn, f"ERROR: Server exception: {exc}")
        except Exception:
            pass
        print(f"[EXCEPTION]  {client_id} raised {exc}")
    finally:
        conn.close()
        print(f"[DISCONNECT] {client_id}")


# ============================================================
# Network Module
# Binds the server socket and dispatches accepted connections to worker threads.
# ============================================================

def start_server():
    """
    Main server loop. Binds to HOST:PORT, listens for TCP connections,
    and spawns a daemon worker thread for each accepted connection.
    """
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(10)

    print("=" * 60)
    print("  Mini-Splunk Concurrent Syslog Analytics Server")
    print(f"  Listening on {HOST}:{PORT}")
    print("  Press Ctrl+C to shut down")
    print("=" * 60)

    try:
        while True:
            conn, addr = server_sock.accept()
            worker = threading.Thread(
                target=handle_client,
                args=(conn, addr),
                daemon=True,
            )
            worker.start()
            active = threading.active_count() - 1
            print(f"[THREADS]    Active worker threads: {active}")
    except KeyboardInterrupt:
        print("\n[SERVER] Interrupt received. Shutting down gracefully...")
    finally:
        server_sock.close()
        print("[SERVER] Socket closed. Goodbye.")


if __name__ == "__main__":
    start_server()
