#!/usr/bin/env python3
"""
X/Twitter CLI Setup Wizard - Universal setup for twitter-cli authentication.

Supports two auth methods:
  1. Chrome CDP extraction (automatic - reads cookies from Chrome)
  2. Manual entry (user provides auth_token and ct0 from browser DevTools)

Saves config to config.json and auth to auth.env.
"""

import json
import os
import stat
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
AUTH_ENV_PATH = os.path.join(SKILL_DIR, "auth.env")

DEFAULT_CONFIG = {
    "auth_method": None,
    "cdp_host": "127.0.0.1",
    "cdp_port": 9222,
    "wsl_proxy": False,
    "wsl_windows_python": "/mnt/c/Windows/py.exe",
    "rules": {
        "single_tweets_only": True,
        "freshness_days": 7,
        "min_delay_seconds": 1.5,
        "max_delay_seconds": 4.0,
    },
    "banned_topics": [],
    "notes": "Add your own content guidelines here"
}


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            config = json.load(f)
        merged = DEFAULT_CONFIG.copy()
        merged.update(config)
        return merged
    return DEFAULT_CONFIG.copy()


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)
    print(f"Config saved to {CONFIG_PATH}")


def save_auth_env(auth_token, ct0):
    """Save auth credentials to auth.env."""
    with open(AUTH_ENV_PATH, "w") as f:
        f.write(f'export TWITTER_AUTH_TOKEN="{auth_token}"\n')
        f.write(f'export TWITTER_CT0="{ct0}"\n')
    os.chmod(AUTH_ENV_PATH, 0o600)
    print(f"Auth saved to {AUTH_ENV_PATH}")


def verify_auth():
    """Verify credentials work with twitter-cli."""
    if not os.path.exists(AUTH_ENV_PATH):
        return False, "auth.env not found"

    try:
        result = subprocess.run(
            f'bash -c "source {AUTH_ENV_PATH} && twitter whoami --yaml 2>&1"',
            shell=True, capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and "ok: true" in result.stdout:
            for line in result.stdout.split('\n'):
                if 'username:' in line:
                    username = line.strip().split(':')[-1].strip()
                    return True, username
            return True, "authenticated"
        else:
            return False, result.stderr[:200] or result.stdout[:200]
    except Exception as e:
        return False, str(e)


def extract_cookies_cdp(config):
    """Extract cookies via Chrome CDP."""
    print("\nExtracting cookies from Chrome CDP...")
    print("Make sure Chrome is running with --remote-debugging-port=9222")
    print("And you are logged into x.com\n")

    cdp_host = config.get("cdp_host", "127.0.0.1")
    cdp_port = config.get("cdp_port", 9222)
    wsl_proxy = config.get("wsl_proxy", False)
    py_exe = config.get("wsl_windows_python", "/mnt/c/Windows/py.exe")

    # Check if we're in WSL2
    is_wsl = False
    try:
        with open("/proc/version", "r") as f:
            is_wsl = "microsoft" in f.read().lower()
    except Exception:
        pass

    # Build the cookie extraction script
    extract_script = f'''import json, asyncio, urllib.request, os, sys

CDP_HOST = "{cdp_host}"
CDP_PORT = "{cdp_port}"
OUT_PATH = r"{os.path.join(os.path.dirname(AUTH_ENV_PATH), "auth.env").replace("/", os.sep)}"

def main():
    try:
        resp = urllib.request.urlopen(f"http://{{CDP_HOST}}:{{CDP_PORT}}/json", timeout=5)
        targets = json.loads(resp.read())
        pages = [t for t in targets if t.get("type") == "page"]
        if not pages:
            print(json.dumps({{"error": "No page tabs open in Chrome"}}))
            return
        ws_url = pages[0]["webSocketDebuggerUrl"]
    except Exception as e:
        print(json.dumps({{"error": f"Chrome CDP not reachable: {{e}}"}}))
        return

    try:
        import websockets
    except ImportError:
        os.system(f"{{sys.executable}} -m pip install websockets -q")
        import websockets

    async def get_cookies():
        async with websockets.connect(ws_url, max_size=10*1024*1024) as ws:
            await ws.send(json.dumps({{"id": 1, "method": "Network.enable"}}))
            for _ in range(10):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if msg.get("id") == 1:
                    break

            await ws.send(json.dumps({{"id": 2, "method": "Network.getAllCookies"}}))
            for _ in range(20):
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
                if msg.get("id") == 2:
                    cookies = msg.get("result", {{}}).get("cookies", [])
                    x_cookies = [c for c in cookies if "x.com" in c.get("domain", "")]

                    auth_token = ""
                    ct0 = ""
                    for c in x_cookies:
                        if c["name"] == "auth_token":
                            auth_token = c["value"]
                        elif c["name"] == "ct0":
                            ct0 = c["value"]

                    if auth_token and ct0:
                        os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
                        with open(OUT_PATH, "w") as f:
                            f.write(f'export TWITTER_AUTH_TOKEN="{{auth_token}}"\\n')
                            f.write(f'export TWITTER_CT0="{{ct0}}"\\n')
                        print(json.dumps({{
                            "success": True,
                            "auth_token_preview": auth_token[:8] + "..." + auth_token[-4:],
                            "ct0_preview": ct0[:8] + "..." + ct0[-4:],
                            "total_cookies": len(x_cookies)
                        }}))
                    else:
                        found = [c["name"] for c in x_cookies]
                        logged_in = any(c["name"] == "twid" for c in x_cookies)
                        print(json.dumps({{
                            "error": "auth_token or ct0 not found",
                            "found_cookies": found,
                            "logged_in": logged_in
                        }}))
                    return
            print(json.dumps({{"error": "timeout waiting for response"}}))

    asyncio.run(get_cookies())

main()
'''

    if is_wsl or wsl_proxy:
        # WSL2 mode - run extraction on Windows side
        win_script_path = r"D:\Hermes\temp\extract_twitter_cookies.py"
        wsl_script_path = "/mnt/d/Hermes/temp/extract_twitter_cookies.py"

        # Write script to Windows-accessible location
        os.makedirs(os.path.dirname(wsl_script_path), exist_ok=True)
        with open(wsl_script_path, "w") as f:
            f.write(extract_script)

        print("Running extraction on Windows side (via py.exe)...")

        try:
            result = subprocess.run(
                [py_exe, "-3", win_script_path],
                capture_output=True, text=True, timeout=30
            )
        except FileNotFoundError:
            print(f"ERROR: Windows Python not found at {py_exe}")
            print("Install Python on Windows or set wsl_windows_python in config.json")
            return False
        except subprocess.TimeoutExpired:
            print("ERROR: Extraction timed out")
            return False

        output = result.stdout.strip()
    else:
        # Native mode - run directly
        print("Running extraction locally...")
        try:
            result = subprocess.run(
                [sys.executable, "-c", extract_script],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout.strip()
        except Exception as e:
            print(f"ERROR: {e}")
            return False

    # Parse result
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        print(f"ERROR: Could not parse output: {output}")
        return False

    if "error" in data:
        print(f"ERROR: {data['error']}")
        if not data.get("logged_in", True):
            print("You are not logged into x.com in Chrome.")
        if "found_cookies" in data:
            print(f"Found cookies: {', '.join(data['found_cookies'])}")
        return False

    if data.get("success"):
        print(f"auth_token: {data['auth_token_preview']}")
        print(f"ct0: {data['ct0_preview']}")
        print(f"Total x.com cookies: {data['total_cookies']}")
        return True

    return False


def manual_entry():
    """Manual cookie entry from browser DevTools."""
    print("\n=== Manual Cookie Entry ===")
    print("\nTo get your cookies:")
    print("1. Open x.com in Chrome and make sure you're logged in")
    print("2. Press F12 to open DevTools")
    print("3. Go to Application tab > Cookies > https://x.com")
    print("4. Find 'auth_token' and 'ct0' cookies")
    print("5. Copy their values below\n")

    auth_token = input("Enter auth_token value: ").strip()
    if not auth_token:
        print("ERROR: auth_token cannot be empty")
        return False

    ct0 = input("Enter ct0 value: ").strip()
    if not ct0:
        print("ERROR: ct0 cannot be empty")
        return False

    save_auth_env(auth_token, ct0)
    return True


def cmd_setup(args):
    """Interactive setup wizard."""
    config = load_config()

    print("=" * 60)
    print("  X/Twitter CLI - Setup Wizard")
    print("=" * 60)
    print()

    # Check if twitter-cli is installed
    try:
        subprocess.run(["twitter", "--version"], capture_output=True, timeout=5)
        print("[OK] twitter-cli is installed")
    except Exception:
        print("[!] twitter-cli not found. Install with:")
        print("    pip install twitter-cli")
        print()
        install = input("Install now? [Y/n]: ").strip().lower()
        if install != "n":
            subprocess.run([sys.executable, "-m", "pip", "install", "twitter-cli"])
        else:
            print("Please install twitter-cli manually and run setup again.")
            return 1

    print()

    # Auth method selection
    print("Authentication Setup")
    print("-" * 40)
    print("twitter-cli needs two cookies from x.com: auth_token and ct0")
    print()
    print("How would you like to provide these?")
    print()
    print("1) Extract automatically via Chrome CDP")
    print("   - Chrome must be running with debugging port")
    print("   - You must be logged into x.com in Chrome")
    print()
    print("2) Enter cookies manually from browser DevTools")
    print("   - Open x.com > F12 > Application > Cookies")
    print("   - Copy auth_token and ct0 values")
    print()

    if config.get("auth_method"):
        print(f"Current method: {config['auth_method']}")
    print()

    choice = input("Choose [1/2] (default: 2): ").strip() or "2"

    success = False
    if choice == "1":
        config["auth_method"] = "cdp"

        # Ask about WSL mode
        try:
            with open("/proc/version", "r") as f:
                is_wsl = "microsoft" in f.read().lower()
        except Exception:
            is_wsl = False

        if is_wsl:
            print("\nWSL2 detected. Chrome runs on Windows.")
            config["wsl_proxy"] = True

            py_exe = config.get("wsl_windows_python", "/mnt/c/Windows/py.exe")
            if not os.path.exists(py_exe):
                py_exe = input(f"Windows Python path (default: {py_exe}): ").strip() or py_exe
            config["wsl_windows_python"] = py_exe
        else:
            config["wsl_proxy"] = False

        save_config(config)
        success = extract_cookies_cdp(config)

    elif choice == "2":
        config["auth_method"] = "manual"
        save_config(config)
        success = manual_entry()

    if not success:
        print("\nSetup failed. You can run setup again anytime.")
        return 1

    # Verify
    print("\nVerifying authentication...")
    ok, info = verify_auth()
    if ok:
        print(f"[OK] Authenticated as: {info}")
    else:
        print(f"[!] Verification failed: {info}")
        print("    The cookies might be expired or invalid.")
        print("    You can re-run setup anytime.")

    # Rules configuration
    print()
    print("Content Rules (optional)")
    print("-" * 40)
    print("These are guidelines for tweet content. Customize or skip.")
    print()

    if not hasattr(args, 'non_interactive') or not args.non_interactive:
        threads = input("Allow thread posting? [y/N]: ").strip().lower()
        config["rules"]["single_tweets_only"] = (threads != "y")

        freshness = input(f"Content freshness in days (default: {config['rules']['freshness_days']}): ").strip()
        if freshness:
            config["rules"]["freshness_days"] = int(freshness)

        banned = input("Any banned topics? (comma-separated, or Enter to skip): ").strip()
        if banned:
            config["banned_topics"] = [t.strip() for t in banned.split(",")]

    save_config(config)

    print()
    print("=" * 60)
    print("  Setup complete!")
    print(f"  Auth method: {config['auth_method']}")
    print(f"  Config: {CONFIG_PATH}")
    print(f"  Auth: {AUTH_ENV_PATH}")
    print("=" * 60)
    return 0


def cmd_config(args):
    """Show current configuration."""
    config = load_config()
    print(json.dumps(config, indent=2))
    return 0


def cmd_auth(args):
    """Check authentication status."""
    ok, info = verify_auth()
    if ok:
        print(json.dumps({"authenticated": True, "username": info}))
        return 0
    else:
        print(json.dumps({"authenticated": False, "error": info}))
        return 1


def main():
    import argparse
    parser = argparse.ArgumentParser(description="X/Twitter CLI Setup")
    sub = parser.add_subparsers(dest="command")

    p_setup = sub.add_parser("setup", help="Run setup wizard")
    p_setup.add_argument("--non-interactive", action="store_true", help="Use defaults")

    sub.add_parser("config", help="Show config")
    sub.add_parser("auth", help="Check auth status")

    args = parser.parse_args()

    if args.command == "setup":
        return cmd_setup(args)
    elif args.command == "config":
        return cmd_config(args)
    elif args.command == "auth":
        return cmd_auth(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
