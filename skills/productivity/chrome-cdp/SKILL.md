---
name: chrome-cdp
description: Browser automation via Chrome DevTools Protocol. Launch Chrome, navigate, click, type, screenshot, evaluate JS, manage cookies. Works on Linux, Mac, Windows, and WSL2.
tags: [chrome, cdp, browser, automation, scraping]
---

# Chrome CDP - Browser Automation Skill

Full browser automation via Chrome DevTools Protocol. No external services, no Selenium, no Playwright — just raw CDP over WebSocket.

## Quick Start

```bash
# 1. Launch Chrome with debugging
python3 skills/productivity/chrome-cdp/scripts/cdp_connector.py launch

# 2. Navigate
python3 scripts/cdp_connector.py navigate https://example.com

# 3. Screenshot
python3 scripts/cdp_connector.py screenshot /tmp/page.png
```

## Platform Setup

### Linux (native)
Works out of the box. Launches `google-chrome` or `chromium`.

### Mac
Works out of the box. Launches Google Chrome from Applications.

### Windows (native)
Works out of the box. Uses `chrome.exe` from Program Files.

### WSL2 (Windows Subsystem for Linux)
WSL2 cannot reach Windows localhost directly due to network isolation. Two options:

**Option A:** Launch Chrome inside WSL (if installed):
```bash
python3 scripts/cdp_connector.py launch --in-wsl
```

**Option B:** Launch Chrome on Windows side, use Windows host IP:
```bash
# Find Windows host IP (usually the default gateway)
ip route show | grep default
# Example output: default via 172.25.112.1 dev eth0 ...
# Use that IP as --host: 172.25.112.1

# Launch Chrome on Windows via PowerShell
powershell.exe -Command 'Start-Process chrome.exe -ArgumentList "--remote-debugging-port=9222","--remote-debugging-address=0.0.0.0","--no-first-run"'

# Then use connector with that host IP
python3 scripts/cdp_connector.py status --host 172.25.112.1
```

## Commands

### launch
Start Chrome with remote debugging enabled.
```bash
python3 scripts/cdp_connector.py launch [--port 9222] [--profile /path/to/profile] [--in-wsl] [--headless]
```
- `--port`: Debugging port (default: 9222)
- `--profile`: Chrome user data directory (creates temp if omitted)
- `--in-wsl`: Use WSL-friendly flags
- `--headless`: Run without GUI (server use)

### status
Check if Chrome CDP is reachable.
```bash
python3 scripts/cdp_connector.py status [--host 127.0.0.1] [--port 9222]
```

### tabs
List open tabs.
```bash
python3 scripts/cdp_connector.py tabs [--host 127.0.0.1] [--port 9222]
```

### navigate
Open URL in a tab (uses first tab if none specified).
```bash
python3 scripts/cdp_connector.py navigate <url> [--tab TAB_ID] [--wait 5] [--host 127.0.0.1] [--port 9222]
```
- `--wait`: Seconds to wait for page load (default: 5)

### open
Open URL in a new tab.
```bash
python3 scripts/cdp_connector.py open <url> [--host 127.0.0.1] [--port 9222]
```

### screenshot
Capture page screenshot.
```bash
python3 scripts/cdp_connector.py screenshot <output_path> [--tab TAB_ID] [--full] [--host 127.0.0.1] [--port 9222]
```
- `--full`: Capture full page (not just viewport)

### click
Click an element by CSS selector.
```bash
python3 scripts/cdp_connector.py click <selector> [--tab TAB_ID] [--host 127.0.0.1] [--port 9222]
```

### type
Type text into an element.
```bash
python3 scripts/cdp_connector.py type <selector> <text> [--tab TAB_ID] [--clear] [--host 127.0.0.1] [--port 9222]
```
- `--clear`: Clear field before typing

### press
Press a keyboard key.
```bash
python3 scripts/cdp_connector.py press <key> [--tab TAB_ID] [--host 127.0.0.1] [--port 9222]
```
Keys: Enter, Tab, Escape, Backspace, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, etc.

### eval
Evaluate JavaScript and return result.
```bash
python3 scripts/cdp_connector.py eval <js_code> [--tab TAB_ID] [--host 127.0.0.1] [--port 9222]
```

### cookies
Get all cookies from the browser.
```bash
python3 scripts/cdp_connector.py cookies [--host 127.0.0.1] [--port 9222]
```

### set-cookie
Set a cookie.
```bash
python3 scripts/cdp_connector.py set-cookie <name> <value> [--domain .example.com] [--path /] [--host 127.0.0.1] [--port 9222]
```

### close-tab
Close a specific tab.
```bash
python3 scripts/cdp_connector.py close-tab <tab_id> [--host 127.0.0.1] [--port 9222]
```

## Typical Workflow

```bash
# Full example: login to a site, take screenshot
python3 scripts/cdp_connector.py launch
python3 scripts/cdp_connector.py navigate https://example.com/login
python3 scripts/cdp_connector.py type input[name="email"] user@example.com
python3 scripts/cdp_connector.py type input[name="password"] secret123
python3 scripts/cdp_connector.py click button[type="submit"]
python3 scripts/cdp_connector.py screenshot /tmp/logged_in.png --wait 5
```

## Dependencies

- Python 3.8+
- `websockets` library (install via pip)
- Chrome/Chromium installed on the machine

## Pitfalls

- **Port conflicts**: If port 9222 is in use, Chrome launch will fail. Kill existing Chrome or use a different port.
- **Tab IDs change**: After navigation, tab IDs may change. Get fresh ones via `tabs` command.
- **Headless mode**: Add `--headless` flag to launch for server use (no GUI needed).
- **WSL2 networking**: Cannot reach Windows localhost directly. Use the default gateway IP from `ip route show`.
- **Chrome accumulation**: Chrome spawns many processes. Kill all Chrome before fresh launch if things get weird.
- **Selector syntax**: Uses CSS selectors. For XPath, use `eval` with `document.evaluate()`.
- **Anti-automation detection**: Some sites detect CDP. Add `--disable-blink-features=AutomationControlled` in launch flags to reduce detection.

## Verification

1. `python3 scripts/cdp_connector.py status` should return `{"connected": true}`
2. `python3 scripts/cdp_connector.py tabs` should return a JSON array of tabs
3. `python3 scripts/cdp_connector.py navigate https://example.com` should return success
4. `python3 scripts/cdp_connector.py screenshot /tmp/test.png` should create an image file
