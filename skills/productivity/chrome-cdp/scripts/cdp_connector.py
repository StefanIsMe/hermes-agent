#!/usr/bin/env python3
"""
Chrome CDP Connector - Universal browser automation via Chrome DevTools Protocol.

Works on Linux, Mac, Windows natively, and WSL2 with --host flag.
No Selenium, no Playwright — raw CDP over HTTP + WebSocket.

Requirements: pip install websockets
"""

import argparse
import base64
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error

try:
    import websockets
    import asyncio
except ImportError:
    print("Error: 'websockets' library required. Install with: pip install websockets")
    sys.exit(1)


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9222


def http_get(host, port, path):
    """Make an HTTP GET request to Chrome CDP."""
    url = f"http://{host}:{port}{path}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except (urllib.error.URLError, ConnectionRefusedError) as e:
        return None


def get_tabs(host, port):
    """Get list of open tabs."""
    tabs = http_get(host, port, "/json")
    return tabs or []


def get_first_tab_id(host, port):
    """Get the first available tab ID."""
    tabs = get_tabs(host, port)
    if not tabs:
        return None
    for tab in tabs:
        if tab.get("type") == "page":
            return tab.get("id")
    return tabs[0].get("id") if tabs else None


def find_tab_by_url(host, port, url_substring):
    """Find a tab whose URL contains the given substring."""
    tabs = get_tabs(host, port)
    for tab in tabs:
        if url_substring in tab.get("url", ""):
            return tab.get("id")
    return None


async def cdp_send(ws_url, method, params=None, timeout=10):
    """Send a CDP command over WebSocket and return the result."""
    msg_id = int(time.time() * 1000) % 100000
    message = {"id": msg_id, "method": method}
    if params:
        message["params"] = params

    try:
        async with websockets.connect(ws_url, max_size=50 * 1024 * 1024) as ws:
            await ws.send(json.dumps(message))
            while True:
                response = await asyncio.wait_for(ws.recv(), timeout=timeout)
                data = json.loads(response)
                if data.get("id") == msg_id:
                    return data
    except Exception as e:
        return {"error": str(e)}


def run_cdp(host, port, tab_id, method, params=None, timeout=10):
    """Run a CDP command on a specific tab."""
    ws_url = f"ws://{host}:{port}/devtools/page/{tab_id}"
    return asyncio.run(cdp_send(ws_url, method, params, timeout))


def cmd_status(args):
    """Check if Chrome CDP is reachable."""
    tabs = get_tabs(args.host, args.port)
    if tabs is not None:
        result = {
            "connected": True,
            "host": args.host,
            "port": args.port,
            "tabs_count": len(tabs),
            "platform": platform.system(),
        }
        print(json.dumps(result, indent=2))
        return 0
    else:
        print(json.dumps({"connected": False, "host": args.host, "port": args.port}))
        return 1


def cmd_tabs(args):
    """List open tabs."""
    tabs = get_tabs(args.host, args.port)
    if tabs is None:
        print("Error: Cannot connect to Chrome CDP", file=sys.stderr)
        return 1
    print(json.dumps(tabs, indent=2))
    return 0


def cmd_launch(args):
    """Launch Chrome with remote debugging."""
    system = platform.system()
    port = args.port
    profile = args.profile or os.path.join(tempfile.gettempdir(), "chrome_cdp_profile")
    os.makedirs(profile, exist_ok=True)

    flags = [
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--disable-default-apps",
        f"--user-data-dir={profile}",
    ]

    if args.headless:
        flags.append("--headless=new")

    if args.in_wsl or (system == "Linux" and "microsoft" in platform.release().lower()):
        flags.append("--remote-debugging-address=0.0.0.0")
        # WSL-specific: use Xvfb if no display
        if not os.environ.get("DISPLAY"):
            os.environ["DISPLAY"] = ":0"

    if system == "Windows":
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        chrome = next((p for p in chrome_paths if os.path.exists(p)), None)
        if not chrome:
            print("Error: Chrome not found", file=sys.stderr)
            return 1
        cmd = [chrome] + flags
    elif system == "Darwin":
        chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        cmd = [chrome] + flags
    else:  # Linux
        for binary in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
            try:
                subprocess.run(["which", binary], capture_output=True, check=True)
                cmd = [binary] + flags
                break
            except subprocess.CalledProcessError:
                continue
        else:
            print("Error: Chrome/Chromium not found. Install with: apt install chromium-browser", file=sys.stderr)
            return 1

    print(f"Launching Chrome on port {port}...")
    print(f"Profile: {profile}")
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Wait for Chrome to be ready
    for i in range(10):
        time.sleep(1)
        if get_tabs(args.host, port) is not None:
            print(json.dumps({"launched": True, "port": port, "profile": profile}))
            return 0

    print("Error: Chrome launched but CDP not reachable", file=sys.stderr)
    return 1


def cmd_navigate(args):
    """Navigate to a URL."""
    tab_id = args.tab or get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    result = run_cdp(args.host, args.port, tab_id, "Page.navigate", {"url": args.url})
    if result and "error" not in result:
        if args.wait:
            time.sleep(args.wait)
        print(json.dumps({"navigated": True, "url": args.url, "tab": tab_id}))
        return 0
    else:
        print(json.dumps({"error": result.get("error", "Navigation failed")}))
        return 1


def cmd_open(args):
    """Open URL in a new tab."""
    result = http_get(args.host, args.port, f"/json/new?{args.url}")
    if result:
        print(json.dumps(result, indent=2))
        return 0
    else:
        print("Error: Failed to open new tab", file=sys.stderr)
        return 1


def cmd_screenshot(args):
    """Take a screenshot."""
    tab_id = args.tab or get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    if args.wait:
        time.sleep(args.wait)

    params = {"format": "png"}
    if args.full:
        # Get page metrics for full screenshot
        metrics = run_cdp(args.host, args.port, tab_id, "Page.getLayoutMetrics")
        if metrics and "result" in metrics:
            content = metrics["result"].get("contentSize", {})
            params["clip"] = {
                "x": 0,
                "y": 0,
                "width": content.get("width", 1920),
                "height": content.get("height", 1080),
                "scale": 1,
            }
            params["captureBeyondViewport"] = True

    result = run_cdp(args.host, args.port, tab_id, "Page.captureScreenshot", params)
    if result and "result" in result:
        img_data = base64.b64decode(result["result"]["data"])
        output_path = os.path.abspath(args.output)
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(img_data)
        print(json.dumps({"screenshot": True, "path": output_path, "size": len(img_data)}))
        return 0
    else:
        print(json.dumps({"error": result.get("error", "Screenshot failed")}))
        return 1


def cmd_click(args):
    """Click an element by CSS selector."""
    tab_id = args.tab or get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    # Use Runtime.evaluate to click via JS (more reliable than CDP Input.dispatchMouseEvent)
    js = f"""
    (() => {{
        const el = document.querySelector('{args.selector}');
        if (!el) return {{error: 'Element not found: {args.selector}'}};
        el.click();
        return {{clicked: true, tag: el.tagName}};
    }})()
    """
    result = run_cdp(args.host, args.port, tab_id, "Runtime.evaluate", {
        "expression": js,
        "returnByValue": True,
    })
    if result and "result" in result:
        print(json.dumps(result["result"].get("value", {}), indent=2))
        return 0
    else:
        print(json.dumps({"error": result.get("error", "Click failed")}))
        return 1


def cmd_type(args):
    """Type text into an element."""
    tab_id = args.tab or get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    # Focus the element and optionally clear it
    clear_js = ".value = '';" if args.clear else ""
    js = f"""
    (() => {{
        const el = document.querySelector('{args.selector}');
        if (!el) return {{error: 'Element not found: {args.selector}'}};
        el.focus();
        {clear_js}
        return {{focused: true, tag: el.tagName}};
    }})()
    """
    run_cdp(args.host, args.port, tab_id, "Runtime.evaluate", {
        "expression": js,
        "returnByValue": True,
    })

    # Type each character via Input.dispatchKeyEvent
    for char in args.text:
        run_cdp(args.host, args.port, tab_id, "Input.dispatchKeyEvent", {
            "type": "keyDown",
            "text": char,
            "key": char,
        })
        run_cdp(args.host, args.port, tab_id, "Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": char,
        })

    print(json.dumps({"typed": True, "selector": args.selector, "length": len(args.text)}))
    return 0


def cmd_press(args):
    """Press a keyboard key."""
    tab_id = args.tab or get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    key_map = {
        "Enter": ("\r", "Enter"),
        "Tab": ("\t", "Tab"),
        "Escape": ("", "Escape"),
        "Backspace": ("", "Backspace"),
        "Delete": ("", "Delete"),
        "ArrowUp": ("", "ArrowUp"),
        "ArrowDown": ("", "ArrowDown"),
        "ArrowLeft": ("", "ArrowLeft"),
        "ArrowRight": ("", "ArrowRight"),
        "Home": ("", "Home"),
        "End": ("", "End"),
        "PageUp": ("", "PageUp"),
        "PageDown": ("", "PageDown"),
    }

    text, key = key_map.get(args.key, (args.key, args.key))

    params = {"type": "keyDown", "key": key}
    if text:
        params["text"] = text
    run_cdp(args.host, args.port, tab_id, "Input.dispatchKeyEvent", params)

    params["type"] = "keyUp"
    run_cdp(args.host, args.port, tab_id, "Input.dispatchKeyEvent", params)

    print(json.dumps({"pressed": args.key}))
    return 0


def cmd_eval(args):
    """Evaluate JavaScript."""
    tab_id = args.tab or get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    result = run_cdp(args.host, args.port, tab_id, "Runtime.evaluate", {
        "expression": args.js_code,
        "returnByValue": True,
        "awaitPromise": True,
    })
    if result and "result" in result:
        value = result["result"].get("result", {}).get("value")
        print(json.dumps(value, indent=2) if value is not None else "undefined")
        return 0
    else:
        print(json.dumps({"error": result.get("error", "Eval failed")}))
        return 1


def cmd_cookies(args):
    """Get all cookies."""
    tab_id = get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    result = run_cdp(args.host, args.port, tab_id, "Network.getAllCookies")
    if result and "result" in result:
        cookies = result["result"].get("cookies", [])
        print(json.dumps(cookies, indent=2))
        return 0
    else:
        print(json.dumps({"error": result.get("error", "Failed to get cookies")}))
        return 1


def cmd_set_cookie(args):
    """Set a cookie."""
    tab_id = get_first_tab_id(args.host, args.port)
    if not tab_id:
        print("Error: No tabs available", file=sys.stderr)
        return 1

    params = {"name": args.name, "value": args.value}
    if args.domain:
        params["domain"] = args.domain
    if args.path:
        params["path"] = args.path

    result = run_cdp(args.host, args.port, tab_id, "Network.setCookie", params)
    if result and "result" in result:
        print(json.dumps(result["result"], indent=2))
        return 0
    else:
        print(json.dumps({"error": result.get("error", "Failed to set cookie")}))
        return 1


def cmd_close_tab(args):
    """Close a tab."""
    result = http_get(args.host, args.port, f"/json/close/{args.tab_id}")
    if result:
        print(json.dumps({"closed": True, "tab": args.tab_id}))
        return 0
    else:
        print("Error: Failed to close tab", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Chrome CDP Connector - Browser automation via Chrome DevTools Protocol",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help="Chrome host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Chrome debugging port (default: 9222)")

    sub = parser.add_subparsers(dest="command", help="Command to run")

    # launch
    p_launch = sub.add_parser("launch", help="Launch Chrome with debugging")
    p_launch.add_argument("--profile", help="Chrome user data directory")
    p_launch.add_argument("--in-wsl", action="store_true", help="WSL-friendly mode")
    p_launch.add_argument("--headless", action="store_true", help="Headless mode")

    # status
    sub.add_parser("status", help="Check CDP connection")

    # tabs
    sub.add_parser("tabs", help="List open tabs")

    # navigate
    p_nav = sub.add_parser("navigate", help="Navigate to URL")
    p_nav.add_argument("url", help="URL to navigate to")
    p_nav.add_argument("--tab", help="Tab ID (default: first tab)")
    p_nav.add_argument("--wait", type=float, default=5, help="Wait seconds after navigation")

    # open
    p_open = sub.add_parser("open", help="Open URL in new tab")
    p_open.add_argument("url", help="URL to open")

    # screenshot
    p_ss = sub.add_parser("screenshot", help="Take screenshot")
    p_ss.add_argument("output", help="Output file path")
    p_ss.add_argument("--tab", help="Tab ID")
    p_ss.add_argument("--full", action="store_true", help="Full page screenshot")
    p_ss.add_argument("--wait", type=float, help="Wait seconds before capture")

    # click
    p_click = sub.add_parser("click", help="Click element by CSS selector")
    p_click.add_argument("selector", help="CSS selector")
    p_click.add_argument("--tab", help="Tab ID")

    # type
    p_type = sub.add_parser("type", help="Type text into element")
    p_type.add_argument("selector", help="CSS selector")
    p_type.add_argument("text", help="Text to type")
    p_type.add_argument("--tab", help="Tab ID")
    p_type.add_argument("--clear", action="store_true", help="Clear field first")

    # press
    p_press = sub.add_parser("press", help="Press keyboard key")
    p_press.add_argument("key", help="Key name (Enter, Tab, Escape, etc.)")
    p_press.add_argument("--tab", help="Tab ID")

    # eval
    p_eval = sub.add_parser("eval", help="Evaluate JavaScript")
    p_eval.add_argument("js_code", help="JavaScript code to evaluate")
    p_eval.add_argument("--tab", help="Tab ID")

    # cookies
    sub.add_parser("cookies", help="Get all cookies")

    # set-cookie
    p_set_cookie = sub.add_parser("set-cookie", help="Set a cookie")
    p_set_cookie.add_argument("name", help="Cookie name")
    p_set_cookie.add_argument("value", help="Cookie value")
    p_set_cookie.add_argument("--domain", help="Cookie domain")
    p_set_cookie.add_argument("--path", default="/", help="Cookie path")

    # close-tab
    p_close = sub.add_parser("close-tab", help="Close a tab")
    p_close.add_argument("tab_id", help="Tab ID to close")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "status": cmd_status,
        "tabs": cmd_tabs,
        "launch": cmd_launch,
        "navigate": cmd_navigate,
        "open": cmd_open,
        "screenshot": cmd_screenshot,
        "click": cmd_click,
        "type": cmd_type,
        "press": cmd_press,
        "eval": cmd_eval,
        "cookies": cmd_cookies,
        "set-cookie": cmd_set_cookie,
        "close-tab": cmd_close_tab,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
