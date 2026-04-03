# Mini-Splunk Pagination Feature

## Overview

The Mini-Splunk system now supports **pagination for search results**. When queries return many log entries, results are automatically split into pages of 100 entries each, with metadata showing the total count, current page, and navigation options.

## Key Features

✓ **Automatic Pagination**: Search results are limited to 100 entries per page  
✓ **Rich Metadata**: Every response includes statistics about total results and pagination state  
✓ **Interactive Navigation**: CLI clients can navigate between pages using [Next], [Previous], or [Exit]  
✓ **Programmable Pages**: API consumers can request specific pages directly  
✓ **Thread-Safe**: Pagination maintains thread safety with existing locking mechanisms  

## Technical Implementation

### Server Changes

#### 1. Enhanced Query Protocol

Queries now support an optional page parameter:

```
QUERY|<type>|<param>|<page>
```

Examples:
- `QUERY|SEARCH_HOST|SYSSVR1` → Page 1 (default)
- `QUERY|SEARCH_HOST|SYSSVR1|2` → Page 2
- `QUERY|SEARCH_KEYWORD|error|1` → Page 1

#### 2. JSON Response Format

All search queries return JSON with metadata and paginated results:

```json
{
  "metadata": {
    "total_results": 250,
    "page": 1,
    "per_page": 100,
    "total_pages": 3,
    "has_next": true,
    "has_prev": false,
    "results_on_page": 100
  },
  "logs": "[entry1]\n[entry2]\n...[entry100]"
}
```

**Metadata Fields:**
- `total_results`: Total number of matching log entries
- `page`: Current page number (1-indexed)
- `per_page`: Number of results per page (100)
- `total_pages`: Total number of pages available
- `has_next`: Whether a next page exists
- `has_prev`: Whether a previous page exists
- `results_on_page`: Number of entries on current page

#### 3. Modified Query Functions

All search functions now accept a `page` parameter:

```python
def search_by_host(hostname, page=1):
    results = [e for e in get_snapshot() if e["hostname"].lower() == hostname.lower()]
    return format_paginated_response(results, page)
```

### Client Changes

#### 1. Interactive Pagination Display

The CLI client displays paginated results with an interactive interface:

```
======================================================================
Query Results: SEARCH_HOST | Param: SYSSVR1
======================================================================
Total Results: 250 | Page 1/3 | Showing 100 entries
----------------------------------------------------------------------
[Feb 22 00:05:38] SYSSVR1 systemd [INFO] Started OpenBSD Secure Shell...
[Feb 22 00:06:10] SYSSVR1 nginx [ERR] Connection refused...
... (98 more entries)
----------------------------------------------------------------------
Options: [N]ext | [E]xit
Enter command (n/p/e):
```

#### 2. Navigation Commands

Users can navigate through pages:
- `[N]ext` or `N` → Go to next page
- `[P]revious` or `P` → Go to previous page  
- `[E]xit` or `E` → Exit pagination and return to prompt

#### 3. Updated Command Functions

Query commands now use the pagination display handler:

```python
def cmd_search_host(hostname):
    """SEARCH_HOST: filter logs by exact hostname match."""
    response = send_simple_command(f"QUERY|SEARCH_HOST|{hostname}")
    display_paginated_results("SEARCH_HOST", hostname, response)
```

## Usage Examples

### Interactive CLI Example

```bash
$ python client.py
============================================================
  Mini-Splunk CLI Forwarder
  Target server: 127.0.0.1:9514
  Type 'help' for available commands or 'exit' to quit.
============================================================

mini-splunk> SEARCH_HOST SYSSVR1
======================================================================
Query Results: SEARCH_HOST | Param: SYSSVR1
======================================================================
Total Results: 250 | Page 1/3 | Showing 100 entries
----------------------------------------------------------------------
[Feb 22 00:05:38] SYSSVR1 systemd [INFO] Started...
... (98 more)
----------------------------------------------------------------------
Options: [N]ext | [E]xit
Enter command (n/p/e): n

======================================================================
Query Results: SEARCH_HOST | Param: SYSSVR1
======================================================================
Total Results: 250 | Page 2/3 | Showing 100 entries
----------------------------------------------------------------------
[Feb 22 08:30:15] SYSSVR1 nginx [ERR] Connection...
... (98 more)
----------------------------------------------------------------------
Options: [P]revious | [N]ext | [E]xit
Enter command (n/p/e): e

mini-splunk>
```

### Programmatic API Example

```python
import socket
import json

def query_page(query_type, param, page=1):
    command = f"QUERY|{query_type}|{param}|{page}\n"
    with socket.socket() as sock:
        sock.connect(("127.0.0.1", 9514))
        sock.sendall(command.encode())
        response = recv_response(sock)
    return json.loads(response)

# Fetch page 2 of SEARCH_DATE results
data = query_page("SEARCH_DATE", "Feb 22", 2)
print(f"Page {data['metadata']['page']} of {data['metadata']['total_pages']}")
print(f"Total matches: {data['metadata']['total_results']}")
print(data['logs'])
```

## Backward Compatibility

- **COUNT_KEYWORD** returns plain integer (no pagination)
- **UPLOAD/INGEST** unchanged
- **ADMIN|PURGE** unchanged
- Search queries always return JSON with pagination metadata

## Configuration

The pagination size can be modified in `server.py`:

```python
RESULTS_PER_PAGE = 100  # Change this to adjust page size
```

## Testing

All existing tests have been updated to handle JSON responses:

```bash
$ python test_mini_splunk.py
============================================================
Results: 57 passed, 0 failed  (57 total)
============================================================
```

## Demonstration

A pagination demonstration script is provided:

```bash
# Terminal 1: Start the server
$ python server.py

# Terminal 2: Run the pagination demo
$ python pagination_demo.py
```

This will:
1. Generate 150 synthetic syslog entries
2. Upload them to the server
3. Demonstrate querying page 1 and page 2
4. Show metadata for each page

## Benefits

1. **Better UX**: No overwhelming output for large result sets
2. **Lower Bandwidth**: Only requested pages are transmitted
3. **Faster Response Times**: Smaller responses return faster
4. **Clear Progress Indication**: Users know how many total results exist
5. **Flexible Navigation**: Easy to navigate between pages interactively

## Thread Safety

The pagination implementation maintains thread safety:
- The `get_snapshot()` function acquires the lock once per query
- Filter operations happen on the snapshot with no lock held
- Pagination slicing happens on the local copy

This design minimizes lock contention while maintaining correctness.
