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


HOST = "0.0.0.0"
PORT = 9514

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
# Converts RFC 3164 syslog strings into structured dictionaries.
# ============================================================

SYSLOG_REGEX = re.compile(
    r"^(?:<(\d+)>)?"                         # PRI field (optional) e.g. <134>
    r"(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"  # TIMESTAMP e.g. Feb 22 00:05:38
    r"\s+(\S+)"                              # HOSTNAME  e.g. SYSSVR1
    r"\s+(\S+?)(?:\[\d+\])?:\s+"            # DAEMON[PID]: e.g. systemd[1]:
    r"(.+)$"                                 # MESSAGE
)


def parse_line(line):
    """
    Parse a single RFC 3164 syslog line into a structured dictionary.
    Returns None if the line does not match the expected format.
    """
    line = line.strip()
    match = SYSLOG_REGEX.match(line)
    if not match:
        return None

    # PRI field is optional. If not present, default to INFO (severity 6)
    priority_str = match.group(1)
    if priority_str is None:
        severity = "INFO"
    else:
        priority = int(priority_str)
        severity_num = priority & 0x07
        severity = SEVERITY_MAP.get(severity_num, "UNKNOWN")

    return {
        "timestamp": match.group(2),
        "hostname":  match.group(3),
        "daemon":    match.group(4),
        "severity":  severity,
        "message":   match.group(5),
    }


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


def search_by_date(date):
    results = [e for e in get_snapshot() if date in e["timestamp"]]
    return format_entries(results)


def search_by_host(hostname):
    results = [e for e in get_snapshot() if e["hostname"].lower() == hostname.lower()]
    return format_entries(results)


def search_by_daemon(daemon):
    results = [e for e in get_snapshot() if e["daemon"].lower() == daemon.lower()]
    return format_entries(results)


def search_by_severity(level):
    results = [e for e in get_snapshot() if e["severity"].upper() == level.upper()]
    return format_entries(results)


def search_by_keyword(word):
    results = [e for e in get_snapshot() if word.lower() in e["message"].lower()]
    return format_entries(results)


def count_keyword(word):
    total = sum(1 for e in get_snapshot() if word.lower() in e["message"].lower())
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
    parts = message.split("|", 2)
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

        query_dispatch = {
            "SEARCH_DATE":     lambda: search_by_date(param),
            "SEARCH_HOST":     lambda: search_by_host(param),
            "SEARCH_DAEMON":   lambda: search_by_daemon(param),
            "SEARCH_SEVERITY": lambda: search_by_severity(param),
            "SEARCH_KEYWORD":  lambda: search_by_keyword(param),
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
