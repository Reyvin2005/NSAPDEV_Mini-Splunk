"""
Mini-Splunk CLI Forwarder Client
Course & Section: NSAPDEV | S12B/S31
Authors: Joshua Benedict B. Co and Reyvin Matthew T. Tan

Usage: python client.py

Then type commands at the prompt. Type 'help' for a full list.
"""

import socket
import os


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


def send_simple_command(command):
    """
    Open a new connection, send a single-line command ending with newline,
    and return the server response string.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.sendall((command + "\n").encode("utf-8"))
            return recv_response(sock)
    except ConnectionRefusedError:
        return (
            f"ERROR: Connection refused. "
            f"Is the server running on {SERVER_HOST}:{SERVER_PORT}?"
        )
    except Exception as exc:
        return f"ERROR: {exc}"


# ============================================================
# Command Implementations
# ============================================================

def cmd_ingest(filepath):
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
            sock.connect((SERVER_HOST, SERVER_PORT))
            sock.sendall(header)
            sock.sendall(content_bytes)
            response = recv_response(sock)
        print(f"[INGEST]          {response}")
    except ConnectionRefusedError:
        print(
            f"[ERROR] Connection refused. "
            f"Is the server running on {SERVER_HOST}:{SERVER_PORT}?"
        )
    except Exception as exc:
        print(f"[ERROR] {exc}")


def cmd_search_date(date):
    """SEARCH_DATE: filter logs whose timestamp contains <date>."""
    response = send_simple_command(f"QUERY|SEARCH_DATE|{date}")
    print(f"[SEARCH_DATE]     Results for '{date}':\n{response}")


def cmd_search_host(hostname):
    """SEARCH_HOST: filter logs by exact hostname match."""
    response = send_simple_command(f"QUERY|SEARCH_HOST|{hostname}")
    print(f"[SEARCH_HOST]     Results for '{hostname}':\n{response}")


def cmd_search_daemon(daemon):
    """SEARCH_DAEMON: filter logs by daemon name."""
    response = send_simple_command(f"QUERY|SEARCH_DAEMON|{daemon}")
    print(f"[SEARCH_DAEMON]   Results for '{daemon}':\n{response}")


def cmd_search_severity(level):
    """SEARCH_SEVERITY: filter logs by severity level (INFO, ERR, WARNING, ...)."""
    response = send_simple_command(f"QUERY|SEARCH_SEVERITY|{level}")
    print(f"[SEARCH_SEVERITY] Results for '{level}':\n{response}")


def cmd_search_keyword(word):
    """SEARCH_KEYWORD: filter logs whose message contains <word>."""
    response = send_simple_command(f"QUERY|SEARCH_KEYWORD|{word}")
    print(f"[SEARCH_KEYWORD]  Results for '{word}':\n{response}")


def cmd_count_keyword(word):
    """COUNT_KEYWORD: count how many log entries contain <word> in the message."""
    response = send_simple_command(f"QUERY|COUNT_KEYWORD|{word}")
    print(f"[COUNT_KEYWORD]   Entries containing '{word}': {response}")


def cmd_purge():
    """PURGE: clear all log entries from the server store."""
    response = send_simple_command("ADMIN|PURGE")
    print(f"[PURGE]           {response}")


# ============================================================
# CLI Shell
# ============================================================

HELP_TEXT = """
Mini-Splunk CLI Forwarder  -  Available Commands
=================================================
  INGEST <filepath>            Upload a syslog file to the server
  SEARCH_DATE <date>           Search logs by date     (e.g. Feb 22)
  SEARCH_HOST <hostname>       Search logs by hostname (e.g. WEBSVR1)
  SEARCH_DAEMON <daemon>       Search logs by daemon   (e.g. nginx)
  SEARCH_SEVERITY <level>      Search logs by severity (INFO ERR WARNING CRIT NOTICE DEBUG EMERG ALERT)
  SEARCH_KEYWORD <word>        Search logs by keyword in the message field
  COUNT_KEYWORD <word>         Count log entries containing a keyword
  PURGE                        Clear all logs from the server store
  HELP                         Show this help message
  EXIT                         Exit the CLI forwarder
"""

COMMAND_MAP = {
    "INGEST":           (cmd_ingest,          "Usage: INGEST <filepath>"),
    "SEARCH_DATE":      (cmd_search_date,     "Usage: SEARCH_DATE <date>"),
    "SEARCH_HOST":      (cmd_search_host,     "Usage: SEARCH_HOST <hostname>"),
    "SEARCH_DAEMON":    (cmd_search_daemon,   "Usage: SEARCH_DAEMON <daemon>"),
    "SEARCH_SEVERITY":  (cmd_search_severity, "Usage: SEARCH_SEVERITY <level>"),
    "SEARCH_KEYWORD":   (cmd_search_keyword,  "Usage: SEARCH_KEYWORD <word>"),
    "COUNT_KEYWORD":    (cmd_count_keyword,   "Usage: COUNT_KEYWORD <word>"),
    "PURGE":            (cmd_purge,           None),
}

NO_ARG_COMMANDS = {"PURGE"}


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

        tokens = raw.split(" ", 1)
        cmd = tokens[0].upper()
        arg = tokens[1].strip() if len(tokens) > 1 else ""

        if cmd == "EXIT":
            print("[CLIENT] Goodbye!")
            break

        if cmd == "HELP":
            print(HELP_TEXT)
            continue

        if cmd not in COMMAND_MAP:
            print(f"[ERROR] Unknown command '{cmd}'. Type 'help' for available commands.")
            continue

        handler, usage_hint = COMMAND_MAP[cmd]

        if cmd in NO_ARG_COMMANDS:
            handler()
        elif not arg:
            print(f"[ERROR] {usage_hint}")
        else:
            handler(arg)


if __name__ == "__main__":
    main()
