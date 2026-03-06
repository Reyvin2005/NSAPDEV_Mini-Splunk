"""
test_mini_splunk.py
-------------------
Self-contained integration and unit test suite for the Mini-Splunk project.

Run with:  python test_mini_splunk.py

The test starts the server on port 19514 (to avoid clashing with a live instance),
exercises every protocol command via raw TCP sockets, and validates each response.
It also unit-tests the Parsing Module directly without any network round-trip.
"""

import socket
import threading
import time
import sys
import os

TEST_PORT = 19514
TEST_HOST = "127.0.0.1"
DUMMY_FILE = os.path.join(os.path.dirname(__file__), "dummy_syslog.txt")

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []


def record(label, passed, detail=""):
    tag = PASS if passed else FAIL
    results.append((label, passed))
    print(f"  [{tag}]  {label}" + (f"  ({detail})" if detail else ""))


# ============================================================
# Import server internals (unit test layer)
# ============================================================

sys.path.insert(0, os.path.dirname(__file__))
import server as srv

# Point the server to the test port so start_server_thread() can reuse it.
srv.PORT = TEST_PORT


def reset_store():
    """Clear log_store between tests without going through the network."""
    with srv.store_lock:
        srv.log_store.clear()


# ============================================================
# Server thread (started once for all TCP tests)
# ============================================================

def start_server_thread():
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((TEST_HOST, TEST_PORT))
    server_sock.listen(10)
    server_sock.settimeout(3)

    def run():
        while not stop_event.is_set():
            try:
                conn, addr = server_sock.accept()
                t = threading.Thread(target=srv.handle_client, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except OSError:
                break
        server_sock.close()

    stop_event = threading.Event()
    t = threading.Thread(target=run, daemon=True)
    t.start()
    time.sleep(0.3)
    return stop_event


# ============================================================
# TCP helper (mirrors client transport)
# ============================================================

def tcp_send_recv(command_line, extra_bytes=b""):
    """Send a single command (+ optional extra bytes) and return the response."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((TEST_HOST, TEST_PORT))
        sock.sendall(command_line.encode("utf-8"))
        if extra_bytes:
            sock.sendall(extra_bytes)

        # Read length prefix
        length_buf = b""
        while True:
            b = sock.recv(1)
            if not b or b == b"\n":
                break
            length_buf += b
        length = int(length_buf.decode())

        # Read body
        body = b""
        while len(body) < length:
            chunk = sock.recv(min(4096, length - len(body)))
            if not chunk:
                break
            body += chunk
        return body.decode("utf-8")


# ============================================================
# SECTION 1: Parsing Module Unit Tests
# ============================================================

def test_parsing():
    print("\n=== Section 1: Parsing Module Unit Tests ===")

    # Basic INFO line
    line = "<134>Feb 22 00:05:38 SYSSVR1 systemd[1]: Started OpenBSD Secure Shell server daemon"
    entry = srv.parse_line(line)
    record("parse_line returns dict", isinstance(entry, dict))
    record("schema key: timestamp", entry is not None and entry.get("timestamp") == "Feb 22 00:05:38")
    record("schema key: hostname",  entry is not None and entry.get("hostname") == "SYSSVR1")
    record("schema key: daemon",    entry is not None and entry.get("daemon") == "systemd")
    record("schema key: severity INFO (PRI 134)", entry is not None and entry.get("severity") == "INFO")
    record("schema key: message",   entry is not None and "Started OpenBSD" in entry.get("message", ""))

    # ERR severity (PRI 131 -> 131 & 7 = 3)
    line2 = "<131>Feb 22 01:15:22 WEBSVR1 nginx[1234]: Connect failed on port 80 address already in use"
    e2 = srv.parse_line(line2)
    record("severity ERR (PRI 131)", e2 is not None and e2.get("severity") == "ERR")
    record("daemon without suffix nginx", e2 is not None and e2.get("daemon") == "nginx")

    # CRIT severity (PRI 130 -> 130 & 7 = 2)
    line3 = "<130>Feb 22 11:00:00 DBSVR1 kernel[0]: Out of memory: Kill process 4512 (mysqld) score 911"
    e3 = srv.parse_line(line3)
    record("severity CRIT (PRI 130)", e3 is not None and e3.get("severity") == "CRIT")
    record("message with embedded colon", e3 is not None and "Out of memory: Kill" in e3.get("message", ""))

    # WARNING (PRI 132 -> 132 & 7 = 4)
    line4 = "<132>Feb 22 02:30:11 DBSVR1 mysql[567]: InnoDB buffer pool resized from 256M to 512M"
    e4 = srv.parse_line(line4)
    record("severity WARNING (PRI 132)", e4 is not None and e4.get("severity") == "WARNING")

    # DEBUG (PRI 135 -> 135 & 7 = 7)
    line5 = "<135>Feb 22 09:45:55 APPSVR1 rsyslog[23]: Acquired UNIX socket /dev/log for logging"
    e5 = srv.parse_line(line5)
    record("severity DEBUG (PRI 135)", e5 is not None and e5.get("severity") == "DEBUG")

    # NOTICE (PRI 133 -> 133 & 7 = 5)
    line6 = "<133>Feb 22 13:20:44 SYSSVR1 sudo[3456]: User1 ran privileged command as root via sudo"
    e6 = srv.parse_line(line6)
    record("severity NOTICE (PRI 133)", e6 is not None and e6.get("severity") == "NOTICE")

    # Bad line returns None
    record("bad line returns None", srv.parse_line("this is not syslog") is None)
    record("empty string returns None", srv.parse_line("") is None)

    # parse_stream on dummy file
    with open(DUMMY_FILE, "r", encoding="utf-8") as fh:
        content = fh.read()
    entries = srv.parse_stream(content)
    record("parse_stream: 18 entries from dummy file", len(entries) == 18,
           f"got {len(entries)}")
    all_have_keys = all(
        {"timestamp", "hostname", "daemon", "severity", "message"} <= set(e.keys())
        for e in entries
    )
    record("parse_stream: every entry has all 5 schema keys", all_have_keys)


# ============================================================
# SECTION 2: Data Storage Module Unit Tests
# ============================================================

def test_data_storage():
    print("\n=== Section 2: Data Storage Module Unit Tests ===")
    reset_store()

    record("store starts empty after reset", len(srv.log_store) == 0)

    sample = [{"timestamp": "Feb 22 00:00:00", "hostname": "H1",
               "daemon": "d1", "severity": "INFO", "message": "hello"}]
    srv.append_logs(sample)
    record("append_logs adds one entry", len(srv.log_store) == 1)

    snapshot = srv.get_snapshot()
    record("get_snapshot returns a list copy", isinstance(snapshot, list) and snapshot is not srv.log_store)
    record("snapshot contains the entry", len(snapshot) == 1)

    srv.purge_logs()
    record("purge_logs clears the store", len(srv.log_store) == 0)
    record("prior snapshot unaffected by purge", len(snapshot) == 1)

    # Verify RLock is used (not a plain Lock)
    record("store_lock is threading.RLock instance",
           isinstance(srv.store_lock, type(threading.RLock())))


# ============================================================
# SECTION 3: Query Engine Module Unit Tests
# ============================================================

def test_query_engine():
    print("\n=== Section 3: Query Engine Module Unit Tests ===")
    reset_store()

    with open(DUMMY_FILE, "r", encoding="utf-8") as fh:
        entries = srv.parse_stream(fh.read())
    srv.append_logs(entries)

    # SEARCH_DATE
    result = srv.search_by_date("Feb 22")
    lines = [l for l in result.splitlines() if l]
    record("search_by_date('Feb 22') returns 7 entries", len(lines) == 7, f"got {len(lines)}")

    # SEARCH_HOST
    result = srv.search_by_host("WEBSVR1")
    lines = [l for l in result.splitlines() if l]
    record("search_by_host('WEBSVR1') returns 4 entries", len(lines) == 4, f"got {len(lines)}")

    # SEARCH_DAEMON
    result = srv.search_by_daemon("cron")
    lines = [l for l in result.splitlines() if l]
    record("search_by_daemon('cron') returns 2 entries", len(lines) == 2, f"got {len(lines)}")

    # SEARCH_SEVERITY
    result = srv.search_by_severity("ERR")
    lines = [l for l in result.splitlines() if l]
    record("search_by_severity('ERR') returns 4 entries", len(lines) == 4, f"got {len(lines)}")

    result_lower = srv.search_by_severity("err")
    record("search_by_severity is case-insensitive", result == result_lower)

    # SEARCH_KEYWORD
    result = srv.search_by_keyword("root")
    record("search_by_keyword('root') finds matches", result != "NO_RESULTS")

    result_none = srv.search_by_keyword("xyzzy_no_match_99")
    record("search_by_keyword with no match returns NO_RESULTS", result_none == "NO_RESULTS")

    # COUNT_KEYWORD
    count_str = srv.count_keyword("failed")
    record("count_keyword returns a digit string", count_str.isdigit())
    record("count_keyword('failed') >= 1", int(count_str) >= 1, f"got {count_str}")

    zero_str = srv.count_keyword("xyzzy_no_match_99")
    record("count_keyword with no match returns '0'", zero_str == "0")


# ============================================================
# SECTION 4: TCP Protocol Integration Tests
# ============================================================

def test_protocol():
    print("\n=== Section 4: TCP Protocol Integration Tests ===")
    reset_store()

    # --- INGEST ---
    with open(DUMMY_FILE, "r", encoding="utf-8") as fh:
        content = fh.read()
    content_bytes = content.encode("utf-8")
    filesize = len(content_bytes)
    header_line = f"UPLOAD|{filesize}|\n"

    response = tcp_send_recv(header_line, extra_bytes=content_bytes)
    record("INGEST: server returns SUCCESS", response.startswith("SUCCESS"),
           repr(response[:60]))
    record("INGEST: store populated (18 entries)", len(srv.log_store) == 18,
           f"got {len(srv.log_store)}")

    # --- SEARCH_DATE ---
    response = tcp_send_recv("QUERY|SEARCH_DATE|Feb 22\n")
    lines = [l for l in response.splitlines() if l]
    record("SEARCH_DATE|Feb 22: returns 7 lines", len(lines) == 7, f"got {len(lines)}")

    # --- SEARCH_HOST ---
    response = tcp_send_recv("QUERY|SEARCH_HOST|DBSVR1\n")
    lines = [l for l in response.splitlines() if l]
    record("SEARCH_HOST|DBSVR1: returns 4 lines", len(lines) == 4, f"got {len(lines)}")

    # --- SEARCH_DAEMON ---
    response = tcp_send_recv("QUERY|SEARCH_DAEMON|nginx\n")
    lines = [l for l in response.splitlines() if l]
    record("SEARCH_DAEMON|nginx: returns 2 lines", len(lines) == 2, f"got {len(lines)}")

    # --- SEARCH_SEVERITY ---
    response = tcp_send_recv("QUERY|SEARCH_SEVERITY|INFO\n")
    lines = [l for l in response.splitlines() if l]
    record("SEARCH_SEVERITY|INFO: returns 6 lines", len(lines) == 6, f"got {len(lines)}")

    # --- SEARCH_KEYWORD ---
    response = tcp_send_recv("QUERY|SEARCH_KEYWORD|Failed\n")
    record("SEARCH_KEYWORD|Failed: not NO_RESULTS", response != "NO_RESULTS")
    record("SEARCH_KEYWORD is case-insensitive",
           tcp_send_recv("QUERY|SEARCH_KEYWORD|failed\n") == response)

    # --- COUNT_KEYWORD ---
    count_resp = tcp_send_recv("QUERY|COUNT_KEYWORD|process\n")
    record("COUNT_KEYWORD|process: returns digit string", count_resp.strip().isdigit(),
           repr(count_resp))
    record("COUNT_KEYWORD|process: count >= 1", int(count_resp.strip()) >= 1)

    # --- PURGE ---
    purge_resp = tcp_send_recv("ADMIN|PURGE\n")
    record("PURGE: server returns SUCCESS", purge_resp.startswith("SUCCESS"),
           repr(purge_resp[:60]))
    record("PURGE: store is now empty", len(srv.log_store) == 0)

    # Post-purge search returns NO_RESULTS
    response = tcp_send_recv("QUERY|SEARCH_SEVERITY|INFO\n")
    record("Post-PURGE search returns NO_RESULTS", response == "NO_RESULTS")

    # --- Unknown command error handling ---
    response = tcp_send_recv("BOGUS|COMMAND\n")
    record("Unknown command type returns ERROR", response.startswith("ERROR"))


# ============================================================
# SECTION 5: Concurrency / Thread Safety Smoke Test
# ============================================================

def test_concurrency():
    print("\n=== Section 5: Concurrency / Thread Safety Smoke Test ===")
    reset_store()

    with open(DUMMY_FILE, "r", encoding="utf-8") as fh:
        content = fh.read()
    content_bytes = content.encode("utf-8")
    filesize = len(content_bytes)

    errors = []

    def ingest_worker():
        try:
            tcp_send_recv(f"UPLOAD|{filesize}|\n", extra_bytes=content_bytes)
        except Exception as exc:
            errors.append(str(exc))

    threads = [threading.Thread(target=ingest_worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    record("5 concurrent INGESTs: no socket exceptions", len(errors) == 0,
           str(errors) if errors else "")
    total = len(srv.log_store)
    record("5 concurrent INGESTs: store has exactly 90 entries (5 x 18)",
           total == 90, f"got {total}")


# ============================================================
# SECTION 6: RFC 3164 / No-Semicolon / No-Double-Hyphen Audit
# ============================================================

def test_file_constraints():
    print("\n=== Section 6: Formatting Constraint Audit ===")

    for filename in ("server.py", "client.py", "dummy_syslog.txt"):
        path = os.path.join(os.path.dirname(__file__), filename)
        text = open(path, "r", encoding="utf-8").read()

        has_semicolon = ";" in text
        has_dbl_hyphen = "--" in text

        record(f"{filename}: no semicolons", not has_semicolon,
               "FOUND ;" if has_semicolon else "")
        record(f"{filename}: no double-hyphens", not has_dbl_hyphen,
               "FOUND --" if has_dbl_hyphen else "")

    # Verify dummy file has >= 15 lines
    with open(DUMMY_FILE, "r", encoding="utf-8") as fh:
        non_empty = [l for l in fh if l.strip()]
    record(f"dummy_syslog.txt has >= 15 lines", len(non_empty) >= 15,
           f"found {len(non_empty)}")


# ============================================================
# Main runner
# ============================================================

def main():
    print("=" * 60)
    print("  Mini-Splunk Integration Test Suite")
    print("=" * 60)

    stop_event = start_server_thread()

    try:
        test_parsing()
        test_data_storage()
        test_query_engine()
        test_protocol()
        test_concurrency()
        test_file_constraints()
    finally:
        stop_event.set()

    passed = sum(1 for _, ok in results if ok)
    failed = len(results) - passed

    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed, {failed} failed  ({len(results)} total)")
    print("=" * 60)

    if failed:
        print("\nFailed tests:")
        for label, ok in results:
            if not ok:
                print(f"  - {label}")
        sys.exit(1)
    else:
        print("\nAll tests passed.")


if __name__ == "__main__":
    main()
