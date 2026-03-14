---
name: x-twitter-cli
description: Post, search, like, retweet, and read X/Twitter using twitter-cli. Cookie auth via Chrome CDP extraction or manual entry. Config-based content rules.
tags: [twitter, x, social-media, cli]
---

# X/Twitter via twitter-cli

Post, search, like, retweet, and interact with X/Twitter — no official API needed.

## First-Time Setup

Run the setup wizard:

```bash
python3 scripts/twitter_setup.py setup
```

This will:
1. Check if `twitter-cli` is installed (offers to install if missing)
2. Let you choose authentication method:
   - **Option 1**: Extract cookies automatically via Chrome CDP (must be logged into x.com)
   - **Option 2**: Enter auth_token and ct0 manually from browser DevTools
3. Configure content rules (optional)
4. Save everything to `config.json` and `auth.env`

### Config File

Settings are stored in `scripts/config.json`:

```json
{
  "auth_method": "cdp",
  "cdp_host": "127.0.0.1",
  "cdp_port": 9222,
  "wsl_proxy": false,
  "wsl_windows_python": "/mnt/c/Windows/py.exe",
  "rules": {
    "single_tweets_only": true,
    "freshness_days": 7,
    "min_delay_seconds": 1.5,
    "max_delay_seconds": 4.0
  },
  "banned_topics": []
}
```

View config: `python3 scripts/twitter_setup.py config`
Check auth: `python3 scripts/twitter_setup.py auth`

### Auth File

Credentials are saved to `auth.env` in the skill root (chmod 600):
```
export TWITTER_AUTH_TOKEN="..."
export TWITTER_CT0="..."
```

### WSL2 Support

If running in WSL2, the setup wizard detects this and offers to extract cookies via Windows py.exe (same approach as chrome-cdp skill). Chrome must be running on Windows with `--remote-debugging-port=9222`.

## Quick Start (after setup)

```bash
# Load credentials
source auth.env

# Verify
twitter whoami

# Home timeline
twitter feed --max 20
```

## Commands

### Read
```bash
twitter feed --max 20                           # Home timeline
twitter feed -t following --max 20              # Following feed
twitter search "AI agents" -t Latest --max 20   # Search
twitter user elonmusk                            # User profile
twitter user-posts elonmusk --max 20            # User's tweets
twitter tweet 1234567890                         # Tweet detail + replies
twitter bookmarks --max 20                       # Bookmarks
```

### Write
```bash
twitter post "tweet text"                       # Post tweet
twitter post "text" --image img.jpg             # Post with image (max 4)
twitter reply 1234567890 "reply text"           # Reply to tweet
twitter quote 1234567890 "comment"              # Quote tweet
twitter delete 1234567890                       # Delete tweet
twitter like 1234567890                         # Like
twitter unlike 1234567890                       # Unlike
twitter retweet 1234567890                      # Retweet
twitter unretweet 1234567890                    # Undo retweet
twitter follow elonmusk                         # Follow
twitter unfollow elonmusk                       # Unfollow
```

### Output Formats
```bash
twitter feed --json                             # JSON for scripts
twitter feed --yaml                             # YAML (default when piped)
twitter -c feed --max 10                        # Compact (80% fewer tokens)
twitter feed --full-text                        # Full tweet text in tables
```

### Advanced Search
```bash
twitter search "topic" --from username --lang en --since 2026-03-01
twitter search "topic" --exclude retweets --has links
```

## Typical Workflow

```bash
# Load auth
source auth.env

# Check what's happening
twitter search "your topic" -t Latest --max 10

# Post something
twitter post "Just published a new guide on AI agents! Check it out."

# Engage with replies
twitter reply 1234567890 "Great point! I think..."
```

## Dependencies
### Requirements

- **Python >= 3.10** (twitter-cli will not work on Python 3.9 or older)
- **Linux, macOS, or Windows** (twitter-cli uses curl_cffi which needs platform-specific wheels)
- **glibc-based Linux** recommended (Alpine/musl may need manual curl_cffi compilation)

The setup wizard checks these requirements before attempting installation.


- Python 3.8+
- `twitter-cli` (pip install twitter-cli)
- `websockets` (pip install websockets) — only for CDP cookie extraction
- Chrome/Chromium with debugging port — only for CDP cookie extraction

## Pitfalls

- **Cookies expire**: auth_token/ct0 expire on logout or password change. Re-run setup if authentication fails.
- **Rate limits**: 
  - Tweets: no hard limit, but random delay built in
  - Search: 50 per 15 min
  - Likes: unlimited
  - Follow: 15 per 15 min
- **CDP extraction requires login**: You must be logged into x.com in Chrome for auto-extraction to work.
- **WSL2 networking**: Cookie extraction in WSL2 mode runs via Windows py.exe since WSL can't reach Windows localhost.
- **Single tweets only**: twitter-cli posts single tweets. Thread posting requires reply chains (manual or scripted).
- **Anti-detection**: Built-in random delays (1.5-4s) between write operations. Don't bypass these or risk account flags.

## Verification

1. `python3 scripts/twitter_setup.py auth` should return `{"authenticated": true}`
2. `twitter whoami` should show your username
3. `twitter feed --max 1` should return one tweet from your timeline
