# 📱➡️🖨️ Text-to-Print (Mac Only Edition)

Automatically print incoming messages — iMessage, WhatsApp, Instagram and anything else
Beeper connects — to a Bluetooth thermal receipt printer.

## How It Works

```
┌─────────────┐          ┌─────────────┐          ┌─────────────┐
│  iMessage   │          │   Beeper    │   BLE    │   PT-210    │
│  WhatsApp   │ ───────► │   Desktop   │ ───────► │  (Printer)  │
│  Instagram  │  bridges │  local API  │          │             │
└─────────────┘          └─────────────┘          └─────────────┘
                                 ▲
                                 │ polls every 2s
                          ┌──────┴───────┐
                          │text_printer.py│
                          └──────────────┘
```

1. Beeper Desktop connects your chat networks and exposes them on a **local** API
   (`127.0.0.1:23373`) — nothing leaves your machine
2. This script polls that API for new messages
3. Each new message is formatted as a receipt and sent to the printer over
   Bluetooth Low Energy

Reading messages through Beeper means the script needs **no Full Disk Access** of its
own, which matters on Macs where that permission is locked down by an MDM policy.

## Quick Start

### 1. Install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

A virtualenv isn't optional on Homebrew Python — it refuses system-wide installs.

### 2. Set up Beeper

1. Install [Beeper Desktop](https://www.beeper.com) and connect the accounts you want
   to print (iMessage, WhatsApp, Instagram, …).
2. Create an API token: **Settings → Integrations → "+"** next to "Approved connections".
3. Save it locally:
   ```bash
   cp .env.example .env     # then paste your token into .env
   ```

Beeper Desktop must be **running** for the script to see any messages.

> Tokens expire. When one does, printing stops and the log tells you the token is
> expired or invalid — create a new one and update `.env`.

### 3. Find your printer

Turn the printer on, then:

```bash
python3 text_printer.py --scan
```

Put the address it reports into `.env` as `PRINTER_ADDRESS`. (If `--scan` crashes
immediately, see [Troubleshooting](#--scan-exits-immediately-with-no-output).)

### 4. Test print

```bash
python3 text_printer.py --test
```

### 5. Run the monitor

```bash
python3 text_printer.py
```

Send yourself a message — it should print within seconds. Only messages that arrive
*after* startup are printed, so you'll never get a backlog dumped on you.

## Commands

| Command | Description |
|---------|-------------|
| `python3 text_printer.py` | Run the message monitor |
| `python3 text_printer.py --test` | Print a test page |
| `python3 text_printer.py --scan` | Scan for BLE printers |
| `python3 text_printer.py --explore` | Explore the printer's BLE services |
| `python3 text_printer.py --help` | Show help |

## Configuration

### Secrets and machine-specific values → `.env`

`.env` is gitignored, so this repo is safe to publish. `.env.example` is the template.

| Value | Why it lives here |
|-------|-------------------|
| `BEEPER_ACCESS_TOKEN` | Secret. Read-only scope, local to your machine, expires. |
| `PRINTER_ADDRESS` | Not secret, but macOS gives each Mac a *different* BLE address for the same printer. Overrides `printer_address` in config.json. |

### Everything else → `config.json`

| Setting | Default | Description |
|---------|---------|-------------|
| `poll_interval_seconds` | `2` | How often to check for new messages |
| `beeper_networks` | `["imessage", "whatsapp", "instagram"]` | Which networks to print |
| `beeper_base_url` | `http://127.0.0.1:23373` | Beeper Desktop API address |
| `filter_contacts` | `[]` | Only print from these senders (empty = everyone) |
| `include_sent_messages` | `false` | Also print messages you send |
| `paper_width_chars` | `32` | Characters per line (58mm paper = 32) |
| `show_timestamp` | `true` | Show time on receipt |
| `show_sender` | `true` | Show sender on receipt |
| `decorative_border` | `true` | Add decorative borders |
| `print_images` | `true` | Print photo attachments |
| `print_video_frames` | `true` | Print a still frame for videos |
| `printer_address` | `""` | Empty = auto-discover by name |
| `printer_name` | `"BlueTooth Printer"` | Name shown in logs; auto-discovery also matches on it |

`beeper_networks` matches the network names Beeper reports (case-insensitive), so you
can add `"facebook"`, `"slack"`, `"signal"`, `"telegram"` and so on.

## Features

### 🖨️ Receipts
Each message prints with the time, sender, and — for anything that isn't iMessage — a
`[WhatsApp]` / `[Instagram]` tag. Group chats also get an `In: <chat name>` line.

### 😀 ASCII conversion
The printer speaks ASCII only, so emoji become emoticons (😀 → `:D`, 👍 → `(thumbs up)`,
200+ mapped), smart punctuation is normalized (`can't` → `can't`, `—` → `--`), and
accents are stripped (`José` → `Jose`). Without this they'd all print as `?`.

### 🖼️ Photos and video frames
Photos print directly. Videos — including shared Instagram reels — print a still frame
extracted with macOS Quick Look, so no ffmpeg install is needed.

**iMessage media is the exception.** Those files live in
`~/Library/Messages/Attachments/`, which requires Full Disk Access. Without it the
receipt still prints with a `[Video: IMG_1234.mov]` line, just no picture. Grant Full
Disk Access to your terminal and iMessage photos start printing automatically.

## Run at Startup (Optional)

Create `~/Library/LaunchAgents/com.texttoprint.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.texttoprint</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/text-to-print/venv/bin/python3</string>
        <string>/path/to/text-to-print/text_printer.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/text-to-print</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/text-to-print.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/text-to-print.err</string>
</dict>
</plist>
```

Load it:

```bash
launchctl load ~/Library/LaunchAgents/com.texttoprint.plist
```

Use the venv's Python and set `WorkingDirectory` so `.env` and `config.json` are found.

## Troubleshooting

### Nothing prints / "Could not reach Beeper Desktop"

- Is Beeper Desktop **running**? The API only exists while the app is open.
- Is your token current? Check it directly:
  ```bash
  source .env
  curl -s -X POST http://127.0.0.1:23373/oauth/introspect \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "token=$BEEPER_ACCESS_TOKEN&token_type_hint=access_token"
  ```
  `{"active": false}` means it expired — create a new one.

### A network's messages aren't printing

Check the name in `beeper_networks` matches what Beeper reports:

```bash
source .env
curl -s -H "Authorization: Bearer $BEEPER_ACCESS_TOKEN" \
  "http://127.0.0.1:23373/v1/chats" | python3 -m json.tool | grep '"network"' | sort -u
```

### `--scan` exits immediately with no output

macOS requires the running binary to declare `NSBluetoothAlwaysUsageDescription` in its
`Info.plist` before it may scan for Bluetooth devices. Homebrew's `python3` doesn't, so
the OS kills the process the moment a scan starts (SIGABRT, no error message). Confirm:

```bash
ls -t ~/Library/Logs/DiagnosticReports/Python-*.ips | head -1
```

The crash report names TCC and `NSBluetoothAlwaysUsageDescription`.

Connecting to an already-known address does **not** hit this, so the workaround is to
pin the address instead of scanning: set `PRINTER_ADDRESS` in `.env`. To find it, run
`--scan` from a Python that declares the key (python.org's framework build), or reuse
the address from a machine where scanning works.

### Printer not found

- Make sure the printer is **turned ON** and nearby
- Try turning it off and on again
- `PRINTER_ADDRESS` from another Mac won't work — the address is per-machine

### Print quality issues

- Check paper is loaded correctly
- Try adjusting `paper_width_chars`

## Technical Details

- **Bluetooth Low Energy** via [`bleak`](https://github.com/hbldh/bleak)
- **ESC/POS** commands for printer control
- PT-210 GATT service: `e7810a71-73ae-499d-8c15-faa9aef0c3f2`
- [Beeper Desktop API](https://developers.beeper.com/desktop-api) for messages

### Why the chat/message list endpoints, not search?

Beeper's macOS iMessage support is a built-in automation library rather than a Matrix
bridge, so it has no entry in `/v1/accounts` or `/v1/bridges` and is missing from the
`/v1/messages/search` index entirely. Reading from `/v1/chats` and
`/v1/chats/{chatID}/messages` covers every network uniformly.

New messages are tracked with a cursor **per chat** rather than one global timestamp.
iMessage is local and instant while bridged networks sync with a delay, so a single
shared watermark would let fast iMessages bury slower messages that arrived later
carrying earlier timestamps.

## License

MIT — do whatever you want with this!
