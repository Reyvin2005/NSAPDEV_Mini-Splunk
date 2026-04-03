# Mini-Splunk Execution & Testing Guide

**Project**: Mini-Splunk Concurrent Syslog Analytics Server  
**Course**: NSAPDEV [S12B/S31]  
**Created**: April 2, 2026

---

## Table of Contents

1. [Pre-Flight Checklist](#pre-flight-checklist)
2. [Running Individual Programs](#running-individual-programs)
3. [Running the Complete System](#running-the-complete-system)
4. [Testing the Complete System](#testing-the-complete-system)
5. [Troubleshooting](#troubleshooting)

---

## Pre-Flight Checklist

Before running any program, verify the following:

### System Requirements
- [ ] Windows PC with PowerShell or Linux/macOS with bash
- [ ] Python 3.6+ installed (`python --version`)
- [ ] TCP port 9514 available (server port)
- [ ] TCP port 19514 available (test server port)

### File Verification
```powershell
# Windows PowerShell
ls c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk\

# Expected output:
# - server.py
# - client.py
# - test_mini_splunk.py
# - dummy_syslog.txt
```

### Python Installation Check
```powershell
python --version
# Expected: Python 3.6 or higher

python -c "import socket; import threading; import re; print('All required modules available')"
# Expected: All required modules available
```

---

## Running Individual Programs

### Program 1: test_mini_splunk.py (Automated Testing)

**What it does**: Runs 57 automated tests covering all modules and commands. This is the **recommended starting point**.

**Steps**:

```powershell
# Navigate to project directory
cd c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk

# Run the test suite
python test_mini_splunk.py

# Expected output: All 57 tests should PASS
# Example final output:
# ============================================================
#   Results: 57 passed, 0 failed  (57 total)
# ============================================================
```

**Test Sections Executed**:
1. **Parsing Module** (17 tests)
   - RFC 3164 syslog parsing
   - Severity mapping
   - Bad input handling

2. **Data Storage** (7 tests)
   - Thread-safe list operations
   - RLock synchronization
   - Snapshot pattern

3. **Query Engine** (10 tests)
   - Date/host/daemon/severity filtering
   - Keyword search
   - Keyword counting
   - Case insensitivity

4. **TCP Protocol** (12 tests)
   - INGEST command
   - All SEARCH commands
   - PURGE command
   - Error handling
   - Length-prefixed responses

5. **Concurrency** (2 tests)
   - 5 simultaneous uploads
   - Thread safety verification

6. **Code Quality** (9 tests)
   - No semicolons constraint
   - No double-hyphens constraint
   - Proper file formatting

**Success Criteria**: All 57 tests display `[PASS]` and exit code 0

---

### Program 2: server.py (Server Instance)

**What it does**: Starts the Mini-Splunk server listening on port 9514.

**Steps**:

```powershell
# Terminal 1: Start the server
cd c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk
python server.py

# Expected output:
# ============================================================
#   Mini-Splunk Concurrent Syslog Analytics Server
#   Listening on 0.0.0.0:9514
#   Press Ctrl+C to shut down
# ============================================================
```

**Server Running State**:
- Server is ready when you see "Listening on 0.0.0.0:9514"
- Server will display connection/command logs in real-time
- To stop: Press `Ctrl+C`

**Expected Activity Log Format**:
```
[CONNECT]    127.0.0.1:12345
[COMMAND]    127.0.0.1:12345 -> INGEST|<file_content>...
[RESPONSE]   127.0.0.1:12345 <- SUCCESS: Ingested 18 log entries
[THREADS]    Active worker threads: 1
[DISCONNECT] 127.0.0.1:12345
```

**Troubleshooting**:
- *Address already in use*: Port 9514 is already in use. Stop other instances or use a different port.
- *Permission denied*: You may need administrator privileges to bind to port 9514.

---

### Program 3: client.py (Interactive CLI)

**What it does**: Provides an interactive command-line interface to communicate with the server.

**Prerequisites**:
- Server must be running on localhost:9514 (see Program 2)

**Steps**:

```powershell
# Terminal 2: Start the client (keep Terminal 1 running with server)
cd c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk
python client.py

# Expected output:
# ============================================================
#   Mini-Splunk CLI Forwarder
#   Target server: 127.0.0.1:9514
#   Type 'help' for available commands or 'exit' to quit.
# ============================================================
# mini-splunk>
```

**Interactive Commands**:

```
# 1. Display help
mini-splunk> help
# Shows all available commands

# 2. Upload a syslog file
mini-splunk> INGEST dummy_syslog.txt
[INGEST]          SUCCESS: File received and 18 syslog entries parsed and indexed.

# 3. Search by date
mini-splunk> SEARCH_DATE Feb 22
[SEARCH_DATE]     Results for 'Feb 22':
[Feb 22 00:05:38] SYSSVR1 systemd [INFO] Started OpenBSD Secure Shell server daemon
[Feb 22 01:15:22] WEBSVR1 nginx [ERR] Connect failed on port 80 address already in use
...

# 4. Search by hostname
mini-splunk> SEARCH_HOST WEBSVR1
[SEARCH_HOST]     Results for 'WEBSVR1':
[Feb 22 00:05:38] SYSSVR1 systemd [INFO] Started OpenBSD Secure Shell server daemon
...

# 5. Search by daemon/process
mini-splunk> SEARCH_DAEMON nginx
[SEARCH_DAEMON]   Results for 'nginx':
[Feb 22 01:15:22] WEBSVR1 nginx [ERR] Connect failed on port 80 address already in use
...

# 6. Search by severity level
mini-splunk> SEARCH_SEVERITY ERR
[SEARCH_SEVERITY] Results for 'ERR':
[Feb 22 01:15:22] WEBSVR1 nginx [ERR] Connect failed on port 80 address already in use
...

# 7. Search by keyword in message
mini-splunk> SEARCH_KEYWORD Failed
[SEARCH_KEYWORD]  Results for 'Failed':
[Feb 23 03:45:12] APPSVR1 sshd [ERR] Failed password for invalid user admin from 192.168.1.100 port 22
...

# 8. Count keyword occurrences
mini-splunk> COUNT_KEYWORD process
[COUNT_KEYWORD]   Entries containing 'process': 2

# 9. Clear all logs
mini-splunk> PURGE
[PURGE]           SUCCESS: 18 indexed log entries have been erased.

# 10. Exit the client
mini-splunk> EXIT
[CLIENT] Goodbye!
```

**Features**:
- Interactive `mini-splunk>` prompt
- Command-line argument parsing (space-separated parameters)
- Case-insensitive commands
- Built-in help system
- Graceful error handling
- Support for file paths with spaces (use quotes)

**Error Handling Examples**:
```
mini-splunk> INGEST nonexistent.txt
[ERROR] File not found: nonexistent.txt

mini-splunk> SEARCH_HOST
[ERROR] Usage: SEARCH_HOST <hostname>

mini-splunk> CONNECTION_ERROR
[ERROR] Unknown command 'CONNECTION_ERROR'. Type 'help' for available commands.
```

**Exit the Client**:
```
mini-splunk> EXIT
[CLIENT] Goodbye!
# Returns to PowerShell prompt
```

---

## Running the Complete System

### End-to-End Workflow

**Step 1: Start the Server**
```powershell
# Terminal 1
cd c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk
python server.py
# Wait for: "Listening on 0.0.0.0:9514"
```

**Step 2: Start the Client (in new terminal)**
```powershell
# Terminal 2
cd c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk
python client.py
# Wait for: "mini-splunk>" prompt
```

**Step 3: Execute Commands**
```powershell
# In client terminal (Terminal 2)
mini-splunk> INGEST dummy_syslog.txt
mini-splunk> SEARCH_DATE Feb 22
mini-splunk> SEARCH_HOST WEBSVR1
mini-splunk> SEARCH_DAEMON nginx
mini-splunk> SEARCH_SEVERITY ERR
mini-splunk> SEARCH_KEYWORD Failed
mini-splunk> COUNT_KEYWORD process
mini-splunk> PURGE
mini-splunk> EXIT
```

**Step 4: Observe Server Logs**
```
# Terminal 1 will display:
[CONNECT]    127.0.0.1:55555
[COMMAND]    127.0.0.1:55555 -> UPLOAD|1596|<134>Feb 22 00:05:38...
[RESPONSE]   127.0.0.1:55555 <- SUCCESS: Ingested 18 log entries into the store
[THREADS]    Active worker threads: 1
[DISCONNECT] 127.0.0.1:55555
```

**Step 5: Stop the Server**
```powershell
# In Terminal 1, press Ctrl+C
# Expected output:
# [SERVER] Interrupt received. Shutting down gracefully...
# [SERVER] Socket closed. Goodbye.
```

---

## Testing the Complete System

### Test Scenario 1: Basic Functionality

```powershell
# Terminal 1
python server.py

# Terminal 2
python client.py

# Terminal 2 commands:
mini-splunk> INGEST dummy_syslog.txt
# Expected: SUCCESS: File received and 18 syslog entries parsed and indexed.

mini-splunk> COUNT_KEYWORD systemd
# Expected: [COUNT_KEYWORD]   Entries containing 'systemd': 3

mini-splunk> PURGE
# Expected: [PURGE]           SUCCESS: 18 indexed log entries have been erased.

mini-splunk> COUNT_KEYWORD systemd
# Expected: [COUNT_KEYWORD]   Entries containing 'systemd': 0
```

### Test Scenario 2: Multiple Clients (Concurrency)

```powershell
# Terminal 1
python server.py

# Terminal 2
python client.py
mini-splunk> INGEST dummy_syslog.txt
mini-splunk> SEARCH_DATE Feb 22
# Keep terminal open

# Terminal 3 (new)
python client.py
mini-splunk> INGEST dummy_syslog.txt
mini-splunk> SEARCH_HOST WEBSVR1
# Should work simultaneously without errors

# Terminal 4 (new)
python client.py
mini-splunk> COUNT_KEYWORD Failed
# Should also work simultaneously
```

**Expected**: All three clients work simultaneously without errors or data corruption. Server should handle all connections smoothly.

### Test Scenario 3: Automated Test Suite (Most Comprehensive)

```powershell
# This test runs all 57 tests automatically
python test_mini_splunk.py

# Expected output shows:
# - 57 passed tests
# - 0 failed tests
# - All 6 test sections completed successfully
# - Exit code: 0
```

---

## Verifying Correct Behavior

### Success Indicators

**Server Console Output**:
- ✓ "Listening on 0.0.0.0:9514"
- ✓ Real-time connection logs: `[CONNECT]`, `[COMMAND]`, `[RESPONSE]`, `[DISCONNECT]`
- ✓ Thread count reporting: `[THREADS]    Active worker threads: #`

**Client Console Output**:
- ✓ "mini-splunk>" prompt appears
- ✓ Commands execute without "[ERROR]" messages (unless intentional)
- ✓ Search results formatted with timestamps and log content
- ✓ PURGE confirms number of entries removed

**Test Suite Output**:
- ✓ All sections print `[PASS]` for each test
- ✓ Final count: "57 passed, 0 failed (57 total)"
- ✓ Test runs complete in < 5 seconds
- ✓ No socket exceptions or connection errors

### Performance Expectations

| Operation | Expected Time | Typical Result |
|-----------|---------------|-----------------|
| INGEST 18 logs | < 100ms | 18 entries parsed |
| SEARCH_DATE | < 50ms | Results returned instantly |
| SEARCH_HOST | < 50ms | Results returned instantly |
| COUNT_KEYWORD | < 50ms | Count returned instantly |
| 5 concurrent uploads | < 500ms | All 90 entries in store (5 × 18) |
| Full test suite | 2-5 seconds | 57 tests complete |

---

## Troubleshooting

### Issue: "Connection refused" on client startup

**Cause**: Server is not running or listening on wrong port  
**Solution**:
```powershell
# Verify server is running:
netstat -ano | findstr :9514
# Should show LISTENING

# If not, start server:
python server.py
```

### Issue: "Address already in use" error

**Cause**: Another instance of server.py is running or port 9514 is in use  
**Solution**:
```powershell
# Find what's using port 9514:
netstat -ano | findstr :9514

# Kill the process (replace PID with actual ID):
taskkill /PID <PID> /F

# Or use a different port by editing server.py:
# Change: PORT = 9514
# To: PORT = 9515
```

### Issue: Tests failing or hanging

**Cause**: Port 19514 already in use (for test server)  
**Solution**:
```powershell
# Kill process on port 19514:
netstat -ano | findstr :19514
taskkill /PID <PID> /F

# Then re-run tests:
python test_mini_splunk.py
```

### Issue: "No such file or directory: dummy_syslog.txt"

**Cause**: Not running from correct directory  
**Solution**:
```powershell
# Verify you're in the right directory:
cd c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk
ls dummy_syslog.txt
# Should list the file

# Then run client with absolute path:
python client.py
mini-splunk> INGEST c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk\dummy_syslog.txt
```

### Issue: Incomplete search results

**Cause**: Case sensitivity or search parameter mismatch  
**Solution**:
```powershell
# All searches are case-INSENSITIVE, so these work the same:
mini-splunk> SEARCH_SEVERITY ERR
mini-splunk> SEARCH_SEVERITY err
mini-splunk> SEARCH_SEVERITY Err
# All return the same results

# For hostname, check exact case:
mini-splunk> SEARCH_HOST websvr1
# Lowercase works (case-insensitive)

mini-splunk> SEARCH_DAEMON NGINX
# Uppercase works (case-insensitive)
```

### Issue: Need to test with custom syslog file

**Steps**:
1. Create file with RFC 3164 format:
```
<134>Feb 22 14:30:00 MYHOST myapp[123]: Custom log message
<131>Feb 22 14:31:00 MYHOST myapp[123]: Error occurred here
```

2. Upload it:
```powershell
mini-splunk> INGEST C:\path\to\custom.txt
```

3. Query it:
```powershell
mini-splunk> SEARCH_HOST MYHOST
mini-splunk> SEARCH_DAEMON myapp
mini-splunk> COUNT_KEYWORD Error
```

---

## Performance Testing

### Stress Test: Multiple Concurrent Clients

```powershell
# Terminal 1
python server.py

# Terminal 2
python test_mini_splunk.py
# This automatically runs 5 concurrent uploads
# Expected: All complete successfully with 90 total entries
```

### Latency Test: Individual Command Timing

```powershell
# Terminal 1
python server.py

# Terminal 2
python client.py
mini-splunk> INGEST dummy_syslog.txt
# Time should be < 100ms

mini-splunk> SEARCH_KEYWORD process
# Time should be < 50ms (even measuring from Python)

mini-splunk> SEARCH_DATE Feb
# Time should be < 50ms
```

---

## Data Persistence & Durability

### Storage Model
- **Type**: In-memory only (no disk persistence)
- **Lifetime**: From server startup to shutdown
- **Durability**: Data lost when server stops (by design)

### Clearing Data
```powershell
mini-splunk> PURGE
# Clears all logs from memory safely
# Server continues running
```

### Fresh Start
```powershell
# Stop server: Ctrl+C in Terminal 1
# Restart server:
python server.py
# Fresh empty log store
```

---

## Summary

### Quick Reference: How to Run Everything

**Option 1: Run Automated Tests (Recommended for Verification)**
```powershell
cd c:\Users\LENOVO\Documents\GitHub\NSAPDEV_Mini-Splunk
python test_mini_splunk.py
# Expected: 57 passed, 0 failed
```

**Option 2: Manual Testing with Server + Client**
```powershell
# Terminal 1
python server.py

# Terminal 2
python client.py

# In Terminal 2:
mini-splunk> INGEST dummy_syslog.txt
mini-splunk> SEARCH_DATE Feb 22
mini-splunk> EXIT
```

**Option 3: Stress Testing with Concurrency**
```powershell
# Terminal 1
python server.py

# Terminal 2, 3, 4 (simultaneously)
python client.py
# Each issues INGEST commands
# Server handles all concurrently without errors
```

---

## Conclusion

The Mini-Splunk system is fully operational and ready for production use. Follow these guides to:
- ✓ Verify implementation completeness
- ✓ Test individual components
- ✓ Run end-to-end system tests
- ✓ Validate concurrent performance
- ✓ Troubleshoot any issues

For detailed technical documentation, see:
- **VERIFICATION_REPORT.md** - Compliance analysis
- **Project Specification PDF** - Original requirements
- **Architecture Design PDF** - System design details

Good luck with your NSAPDEV project!
