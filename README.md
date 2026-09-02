# 📱➡️🖨️ Text-to-Print (Mac Only Edition)

Automatically print incoming messages — iMessage, WhatsApp, Instagram — to a thermal receipt printer.

Uses **Bluetooth Low Energy (BLE)** for reliable communication with GOOJPRT PT-210 printers. WhatsApp/Instagram (and any other network Beeper bridges) come in via the local [Beeper Desktop API](https://developers.beeper.com/desktop-api).

## How It Works

```
┌─────────────┐  iCloud   ┌─────────────┐   BLE    ┌─────────────┐
│   iPhone    │ ────────► │     Mac     │ ──────►  │   PT-210    │
│  (Messages) │   sync    │  (Monitor)  │          │  (Printer)  │
└─────────────┘           └─────────────┘          └─────────────┘
```

1. Messages sync from iPhone to Mac via iCloud
2. Python script monitors the Messages database
3. New messages are sent to the PT-210 via Bluetooth Low Energy
4. Printer outputs a receipt with the message

## Quick Start

### 1. Install Dependencies

```bash
cd text-to-print-mac-only
pip3 install -r requirements.txt
```

### 2. Grant Full Disk Access

The script needs permission to read the Messages database:

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click the lock 🔒 to make changes
3. Add **Terminal** (or your Python IDE)
4. Restart Terminal

### 3. Turn On Your Printer

Make sure the PT-210 is powered on and in range of your Mac.

### 4. Scan for Printer

```bash
python3 text_printer.py --scan
```

Look for "PT-210" in the device list.

### 5. Test Print

```bash
python3 text_printer.py --test
```

You should see a test receipt print!

### 6. Run the Monitor

```bash
python3 text_printer.py
```

Send yourself a text message — it should print within seconds!

## WhatsApp / Instagram / iMessage Setup (via Beeper)

Non-iMessage networks print through [Beeper Desktop](https://www.beeper.com)'s local API. Beeper can *also* supply iMessage, which is useful if Full Disk Access to `chat.db` isn't available (for example on a Mac managed by an MDM policy that locks it).

1. **Install Beeper Desktop** and connect the accounts you want to print.
2. **Create an API token**: in Beeper Desktop, go to **Settings → Integrations**, click the **"+"** next to "Approved connections", and follow the prompt.
3. **Save the token locally** (never commit it):
   ```bash
   cp .env.example .env    # then paste your token into .env
   ```
4. Leave Beeper Desktop running, then start the monitor as usual.

Tokens expire. When one does, printing stops and the log says the token is
expired or invalid — create a new one and update `.env`.

### Secrets and machine-specific settings

Everything secret or machine-specific lives in `.env`, which is gitignored, so
this repo is safe to make public. `.env.example` is the committed template.

| Value | Where it goes | Why |
|-------|---------------|-----|
| `BEEPER_ACCESS_TOKEN` | `.env` | Secret. Read-only scope, local to your machine, and expires. |
| `PRINTER_ADDRESS` | `.env` | Not secret, but macOS gives each Mac a different BLE address for the same printer. |
| Everything else | `config.json` | Portable across machines, safe to commit. |

`PRINTER_ADDRESS` overrides `printer_address` in config.json when set.

### Where iMessage comes from

- List `"imessage"` in `beeper_networks` → iMessage arrives via Beeper, and **no Full Disk Access is needed**.
- Leave it out → the script reads `~/Library/Messages/chat.db` directly, which *does* require Full Disk Access.

The monitor prints which source it chose at startup. If Beeper Desktop isn't running or installed, it logs a warning, disables Beeper for the session, and falls back to `chat.db`.

Receipts from non-iMessage networks get a `[WhatsApp]` / `[Instagram]` tag, and group chats get an `In: <chat name>` line.

> **Implementation note:** Beeper's macOS iMessage support is a built-in automation library rather than a Matrix bridge, so it does not appear in `/v1/accounts` or `/v1/bridges` and is missing from the `/v1/messages/search` index. This project therefore reads from `/v1/chats` + `/v1/chats/{chatID}/messages`, which covers every network uniformly.

## Commands

| Command | Description |
|---------|-------------|
| `python3 text_printer.py` | Run the message monitor |
| `python3 text_printer.py --test` | Print a test page |
| `python3 text_printer.py --scan` | Scan for BLE printers |
| `python3 text_printer.py --explore` | Explore printer's BLE services |
| `python3 text_printer.py --help` | Show help |

## Configuration

Edit `config.json` to customize behavior:

| Setting | Default | Description |
|---------|---------|-------------|
| `poll_interval_seconds` | `2` | How often to check for new messages |
| `filter_contacts` | `[]` | Only print from these contacts (empty = all) |
| `include_sent_messages` | `false` | Also print messages you send |
| `paper_width_chars` | `32` | Characters per line (58mm paper = 32) |
| `show_timestamp` | `true` | Show time on receipt |
| `show_sender` | `true` | Show sender on receipt |
| `decorative_border` | `true` | Add decorative borders |
| `print_images` | `false` | Print image attachments (requires Pillow) |
| `beeper_enabled` | `false` | Print messages via the Beeper Desktop API |
| `beeper_networks` | `["whatsapp", "instagram"]` | Which Beeper networks to print. Include `"imessage"` to source iMessage from Beeper instead of `chat.db` |
| `beeper_base_url` | `http://127.0.0.1:23373` | Beeper Desktop API address (rarely needs changing) |

### Filter by Contact

Only print messages from specific people:

```json
"filter_contacts": ["+15551234567", "mom@icloud.com"]
```

## Features

### 📇 Contact Names
The script looks up contact names from your Mac's Contacts app. Instead of seeing "+15551234567", you'll see "Mom" (if they're in your contacts).

### 😀 Emoji Support
Emojis are automatically converted to ASCII emoticons:
- 😀 → :D
- ❤️ → <3
- 👍 → (thumbs up)
- And 200+ more!

### 📎 Attachment Detection
When someone sends an image, video, or file, the receipt shows:
```
[Image: photo.jpg]
```

### 🖼️ Image Printing (Optional)
To print actual images, enable it in config.json:
```json
"print_images": true
```
And install Pillow: `pip3 install Pillow`

Images are automatically converted to black & white and sized for the receipt paper.

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
        <string>/usr/bin/python3</string>
        <string>/path/to/text-to-print-mac-only/text_printer.py</string>
    </array>
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

## Troubleshooting

### "Permission denied" when reading Messages

Grant Full Disk Access to Terminal (see step 2 above).

### Printer not found in scan

- Make sure the PT-210 is **turned ON**
- Move the printer closer to your Mac
- Try turning the printer off and on again

### `--scan` exits immediately with no output (crash)

macOS requires the running binary to declare `NSBluetoothAlwaysUsageDescription`
in its `Info.plist` before it may scan for Bluetooth devices. Homebrew's `python3`
doesn't, so the OS kills the process the moment a scan starts (SIGABRT, no error
message). Confirm it with:

```bash
ls -t ~/Library/Logs/DiagnosticReports/Python-*.ips | head -1
```

The crash report names TCC and `NSBluetoothAlwaysUsageDescription`.

Connecting to an already-known address does **not** hit this, so the workaround is
to pin the address instead of scanning: set `PRINTER_ADDRESS` in `.env` (see
`.env.example`). To find the address, run `--scan` from a Python that does declare
the key — python.org's framework build, or any terminal already granted Bluetooth
access — or reuse the address from a machine where scanning works.

### Messages not appearing

Make sure iCloud Messages sync is enabled:
- **Messages app → Settings → iMessage → "Enable Messages in iCloud"**

### Print quality issues

- Check paper is loaded correctly
- Try adjusting `paper_width_chars` in config.json

## Technical Details

This project uses:

- **Bluetooth Low Energy (BLE)** via the `bleak` library
- **ESC/POS commands** for printer control
- PT-210 custom GATT service: `e7810a71-73ae-499d-8c15-faa9aef0c3f2`

## License

MIT — do whatever you want with this!
