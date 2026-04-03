"""
Mini-Splunk CLI Forwarder Client
Course & Section: NSAPDEV | S12B/S31
Authors: Joshua Benedict B. Co and Reyvin Matthew T. Tan

Usage: python client.py

Then type commands at the prompt. Type 'help' for a full list.
"""

import socket
import os
import shlex


SERVER_HOST = "127.0.0.1"
SERVER_PORT = 9514


# ============================================================
# Transport Helpers
# ============================================================

def recv_response(sock):
    """
    Receive a length-prefixed response from the server.
    Protocol: "<byte_length>\n<response_body>"
    """
    length_buf = b""
    while True:
        byte = sock.recv(1)
        if not byte or byte == b"\n":
            break
        length_buf += byte

    try:
        length = int(length_buf.decode("utf-8").strip())
    except ValueError:
        return "ERROR: Received malformed length prefix from server"

    resp_buf = b""
    while len(resp_buf) < length:
        chunk = sock.recv(min(4096, length - len(resp_buf)))
        if not chunk:
            break
        resp_buf += chunk

    return resp_buf.decode("utf-8")


def parse_endpoint(endpoint):
    """Parse <IP_or_DNS>:<Port> and return (host, port)."""
    if ":" not in endpoint:
        raise ValueError("Endpoint must be in the form <IP_or_DNS>:<Port>")

    host, port_str = endpoint.rsplit(":", 1)
    if not host:
        raise ValueError("Endpoint host cannot be empty")

    try:
        port = int(port_str)
    except ValueError as exc:
        raise ValueError("Endpoint port must be an integer") from exc

    if port < 1 or port > 65535:
        raise ValueError("Endpoint port must be between 1 and 65535")

    return host, port


def send_simple_command(command, host, port):
    """
    Open a new connection, send a single-line command ending with newline,
    and return the server response string.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
            sock.sendall((command + "\n").encode("utf-8"))
            return recv_response(sock)
    except ConnectionRefusedError:
        return (
            f"ERROR: Connection refused. "
            f"Is the server running on {host}:{port}?"
        )
    except Exception as exc:
        return f"ERROR: {exc}"


# ============================================================
# Command Implementations
# ============================================================

def cmd_ingest(filepath, host, port):
    """
    INGEST command.
    Protocol: UPLOAD|<filesize>|\n  followed immediately by <filesize> bytes of content.
    """
    if not os.path.exists(filepath):
        print(f"[ERROR] File not found: {filepath}")
        return

    with open(filepath, "r", encoding="utf-8") as fh:
        content = fh.read()

    content_bytes = content.encode("utf-8")
    filesize = len(content_bytes)
    header = f"UPLOAD|{filesize}|\n".encode("utf-8")

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((host, port))
            sock.sendall(header)
            sock.sendall(content_bytes)
            response = recv_response(sock)
        print(f"[INGEST]          {response}")
    except ConnectionRefusedError:
        print(
            f"[ERROR] Connection refused. "
            f"Is the server running on {host}:{port}?"
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")


def cmd_query(host, port, query_type, query_arg):
    """Execute QUERY commands against a specific endpoint."""
    print(f"[SYSTEM] Sending query to {host}:{port}...")
    response = send_simple_command(f"QUERY|{query_type}|{query_arg}", host, port)

    if query_type == "COUNT_KEYWORD":
        print(f"[{query_type}] {response}")
    else:
        print(f"[{query_type}]\n{response}")


def cmd_purge(host, port):
    """PURGE: clear all log entries from the server store."""
    response = send_simple_command("ADMIN|PURGE", host, port)
    print(f"[PURGE]           {response}")


# ============================================================
# CLI Shell
# ============================================================

HELP_TEXT = """
Mini-Splunk CLI Forwarder  -  Available Commands
=================================================
  INGEST <filepath> <IP_or_DNS>:<Port>
      Upload a syslog file to the target server

  QUERY <IP_or_DNS>:<Port> SEARCH_DATE <date>
  QUERY <IP_or_DNS>:<Port> SEARCH_HOST <hostname>
  QUERY <IP_or_DNS>:<Port> SEARCH_DAEMON <daemon>
  QUERY <IP_or_DNS>:<Port> SEARCH_SEVERITY <level>
  QUERY <IP_or_DNS>:<Port> SEARCH_KEYWORD <keyword_or_phrase>
  QUERY <IP_or_DNS>:<Port> COUNT_KEYWORD <keyword_or_phrase>

  PURGE <IP_or_DNS>:<Port>
      Clear all logs from the target server store

  Notes:
      Use quotes for multi-word values, e.g. "Feb 22" or "Failed password"

  HELP                         Show this help message
  EXIT                         Exit the CLI forwarder
"""

QUERY_TYPES = {
    "SEARCH_DATE",
    "SEARCH_HOST",
    "SEARCH_DAEMON",
    "SEARCH_SEVERITY",
    "SEARCH_KEYWORD",
    "COUNT_KEYWORD",
}


def main():
    print("=" * 60)
    print("  Mini-Splunk CLI Forwarder")
    print(f"  Target server: {SERVER_HOST}:{SERVER_PORT}")
    print("  Type 'help' for available commands or 'exit' to quit.")
    print("=" * 60)

    while True:
        try:
            raw = input("mini-splunk> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[CLIENT] Exiting...")
            break

        if not raw:
            continue

        try:
            tokens = shlex.split(raw)
        except ValueError as exc:
            print(f"[ERROR] Invalid command syntax: {exc}")
            continue

        if not tokens:
            continue

        cmd = tokens[0].upper()

        if cmd == "EXIT":
            print("[CLIENT] Goodbye!")
            break

        if cmd == "HELP":
            print(HELP_TEXT)
            continue

        if cmd == "INGEST":
            if len(tokens) < 3:
                print("[ERROR] Usage: INGEST <filepath> <IP_or_DNS>:<Port>")
                continue

            filepath = tokens[1]
            endpoint = tokens[2]
            try:
                host, port = parse_endpoint(endpoint)
            except ValueError as exc:
                print(f"[ERROR] {exc}")
                continue

            print(f"[SYSTEM] Connecting to {host}:{port}...")
            cmd_ingest(filepath, host, port)
            continue

        if cmd == "QUERY":
            if len(tokens) < 4:
                print("[ERROR] Usage: QUERY <IP_or_DNS>:<Port> <QUERY_TYPE> <value>")
                continue

            endpoint = tokens[1]
            query_type = tokens[2].upper()
            query_arg = " ".join(tokens[3:]).strip()

            if query_type not in QUERY_TYPES:
                print(f"[ERROR] Unknown query type '{query_type}'. Type 'help' for valid QUERY types.")
                continue

            if not query_arg:
                print("[ERROR] Query value cannot be empty")
                continue

            try:
                host, port = parse_endpoint(endpoint)
            except ValueError as exc:
                print(f"[ERROR] {exc}")
                continue

            cmd_query(host, port, query_type, query_arg)
            continue

        if cmd == "PURGE":
            if len(tokens) != 2:
                print("[ERROR] Usage: PURGE <IP_or_DNS>:<Port>")
                continue

            endpoint = tokens[1]
            try:
                host, port = parse_endpoint(endpoint)
            except ValueError as exc:
                print(f"[ERROR] {exc}")
                continue

            print(f"[SYSTEM] Connecting to {host}:{port} to purge records...")
            cmd_purge(host, port)
            continue

        print(f"[ERROR] Unknown command '{cmd}'. Type 'help' for available commands.")


if __name__ == "__main__":
    main()
