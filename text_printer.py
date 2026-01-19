#!/usr/bin/env python3
"""
📱➡️🖨️ Text-to-Print (Mac Only Edition)

Automatically prints incoming text messages to a GOOJPRT PT-210 thermal printer.
Uses Bluetooth Low Energy (BLE) for reliable communication.

Usage:
    python3 text_printer.py              Run the message monitor
    python3 text_printer.py --scan       Scan for BLE printers
    python3 text_printer.py --test       Test print via BLE
    python3 text_printer.py --explore    Explore printer's BLE services
"""

import asyncio
import sys
import sqlite3
import os
import json
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

# BLE library
try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    print("❌ bleak library not installed!")
    print("   Run: pip3 install bleak")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# PT-210 BLE CONSTANTS
# =============================================================================

# PT-210 BLE Service UUID (custom print service)
PT210_SERVICE_UUID = "e7810a71-73ae-499d-8c15-faa9aef0c3f2"

# Common write characteristic UUID for this printer family
PT210_WRITE_CHAR = "bef8d6c9-9c21-4c9e-b632-bd58c1009f9f"

# ESC/POS Commands
ESC_INIT = b'\x1b\x40'           # Initialize printer
ESC_ALIGN_LEFT = b'\x1b\x61\x00'
ESC_ALIGN_CENTER = b'\x1b\x61\x01'
LINE_FEED = b'\x0a'


# =============================================================================
# BLE PRINTER CLASS
# =============================================================================

class BLEPrinter:
    """Bluetooth Low Energy printer driver for PT-210."""
    
    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.device_address: Optional[str] = None
        self.write_characteristic: Optional[str] = None
    
    async def discover(self) -> Optional[str]:
        """Discover PT-210 printer via BLE scan."""
        logger.info("Scanning for PT-210 via BLE...")
        
        devices = await BleakScanner.discover(timeout=10.0)
        
        # Look for PT-210 by name
        for device in devices:
            name = device.name or ""
            if "PT-210" in name or "PT210" in name:
                logger.info(f"✓ Found PT-210: {device.name} ({device.address})")
                self.device_address = device.address
                return device.address
        
        # If not found by name, look for devices with the PT-210 service UUID
        logger.info("Scanning for devices with PT-210 service UUID...")
        devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
        
        for device, adv_data in devices.values():
            service_uuids = [s.lower() for s in adv_data.service_uuids]
            if PT210_SERVICE_UUID.lower() in service_uuids:
                logger.info(f"✓ Found device with PT-210 service: {device.name} ({device.address})")
                self.device_address = device.address
                return device.address
        
        logger.error("PT-210 not found. Make sure it's turned on and in range.")
        return None
    
    async def connect(self, address: Optional[str] = None) -> bool:
        """Connect to the printer via BLE."""
        if address:
            self.device_address = address
        
        if not self.device_address:
            if not await self.discover():
                return False
        
        try:
            logger.info(f"Connecting to {self.device_address}...")
            self.client = BleakClient(self.device_address)
            await self.client.connect()
            
            if not self.client.is_connected:
                logger.error("Failed to connect")
                return False
            
            logger.info("✓ Connected!")
            
            # Find the write characteristic
            await self._find_write_characteristic()
            return True
            
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False
    
    async def _find_write_characteristic(self):
        """Find the writable characteristic for sending print data."""
        for service in self.client.services:
            # Check if this is the PT-210 custom service
            if PT210_SERVICE_UUID.lower() in service.uuid.lower():
                logger.debug(f"Found PT-210 service: {service.uuid}")
                
                for char in service.characteristics:
                    if "write" in char.properties or "write-without-response" in char.properties:
                        self.write_characteristic = char.uuid
                        logger.debug(f"Using write characteristic: {char.uuid}")
                        return
        
        # Fallback: search all services for a writable characteristic
        for service in self.client.services:
            for char in service.characteristics:
                if "write" in char.properties or "write-without-response" in char.properties:
                    if not char.uuid.startswith("0000"):  # Skip standard BLE characteristics
                        self.write_characteristic = char.uuid
                        logger.debug(f"Using write characteristic: {char.uuid}")
                        return
        
        logger.warning("No suitable write characteristic found")
    
    async def disconnect(self):
        """Disconnect from printer."""
        if self.client and self.client.is_connected:
            await self.client.disconnect()
            logger.info("Disconnected from printer")
    
    async def print_text(self, text: str) -> bool:
        """Send text to the thermal printer using ESC/POS commands."""
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to printer")
            return False
        
        if not self.write_characteristic:
            logger.error("No write characteristic available")
            return False
        
        try:
            # Build ESC/POS data
            data = bytearray()
            data.extend(ESC_INIT)          # Initialize printer
            data.extend(ESC_ALIGN_LEFT)    # Left align
            
            # Add text (ASCII encoding)
            data.extend(text.encode('ascii', errors='replace'))
            
            # Paper feed
            data.extend(LINE_FEED * 4)
            
            # Send in chunks (BLE MTU is typically limited)
            chunk_size = 20
            for i in range(0, len(data), chunk_size):
                chunk = bytes(data[i:i + chunk_size])
                try:
                    await self.client.write_gatt_char(
                        self.write_characteristic,
                        chunk,
                        response=False
                    )
                except Exception:
                    await self.client.write_gatt_char(
                        self.write_characteristic,
                        chunk,
                        response=True
                    )
                await asyncio.sleep(0.05)
            
            return True
            
        except Exception as e:
            logger.error(f"Print error: {e}")
            return False


# =============================================================================
# CONTACT NAME LOOKUP
# =============================================================================

class ContactLookup:
    """Look up contact names from the macOS AddressBook database."""
    
    def __init__(self):
        self._cache = {}  # Cache lookups to avoid repeated DB queries
        self._db_path = self._find_addressbook_db()
    
    def _find_addressbook_db(self) -> Optional[str]:
        """Find the AddressBook database path."""
        base_path = os.path.expanduser("~/Library/Application Support/AddressBook/Sources")
        
        if not os.path.exists(base_path):
            return None
        
        # Look for the database in source folders
        for source_dir in os.listdir(base_path):
            db_path = os.path.join(base_path, source_dir, "AddressBook-v22.abcddb")
            if os.path.exists(db_path):
                return db_path
        
        return None
    
    def get_name(self, identifier: str) -> Optional[str]:
        """
        Look up a contact name by phone number or email.
        Returns the contact name if found, None otherwise.
        """
        if not identifier:
            return None
        
        # Check cache first
        if identifier in self._cache:
            return self._cache[identifier]
        
        name = None
        
        # Try AddressBook database
        if self._db_path:
            name = self._lookup_in_addressbook(identifier)
        
        # Cache the result (even if None, to avoid repeated lookups)
        self._cache[identifier] = name
        return name
    
    def _lookup_in_addressbook(self, identifier: str) -> Optional[str]:
        """Query the AddressBook database for a contact name."""
        try:
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # Normalize phone number (remove non-digits for comparison)
            normalized_phone = ''.join(c for c in identifier if c.isdigit())
            
            # Query for phone number match
            if normalized_phone:
                cursor.execute("""
                    SELECT ZABCDRECORD.ZFIRSTNAME, ZABCDRECORD.ZLASTNAME
                    FROM ZABCDRECORD
                    JOIN ZABCDPHONENUMBER ON ZABCDRECORD.Z_PK = ZABCDPHONENUMBER.ZOWNER
                    WHERE REPLACE(REPLACE(REPLACE(REPLACE(ZABCDPHONENUMBER.ZFULLNUMBER, ' ', ''), '-', ''), '(', ''), ')', '')
                    LIKE ?
                """, (f"%{normalized_phone[-10:]}",))  # Match last 10 digits
                
                row = cursor.fetchone()
                if row:
                    first, last = row[0] or '', row[1] or ''
                    name = f"{first} {last}".strip()
                    if name:
                        conn.close()
                        return name
            
            # Query for email match
            if '@' in identifier:
                cursor.execute("""
                    SELECT ZABCDRECORD.ZFIRSTNAME, ZABCDRECORD.ZLASTNAME
                    FROM ZABCDRECORD
                    JOIN ZABCDEMAILADDRESS ON ZABCDRECORD.Z_PK = ZABCDEMAILADDRESS.ZOWNER
                    WHERE LOWER(ZABCDEMAILADDRESS.ZADDRESS) = LOWER(?)
                """, (identifier,))
                
                row = cursor.fetchone()
                if row:
                    first, last = row[0] or '', row[1] or ''
                    name = f"{first} {last}".strip()
                    if name:
                        conn.close()
                        return name
            
            conn.close()
            
        except Exception as e:
            logger.debug(f"AddressBook lookup failed: {e}")
        
        return None


# =============================================================================
# MESSAGE MONITOR
# =============================================================================

class MessageMonitor:
    """Monitors the macOS Messages database for new messages."""
    
    APPLE_EPOCH_OFFSET = 978307200
    
    def __init__(self, config: dict):
        self.config = config
        self.db_path = os.path.expanduser("~/Library/Messages/chat.db")
        self.state_file = Path(__file__).parent / ".last_message_id"
        self.last_message_id = self._load_last_id()
        self.contacts = ContactLookup()  # For looking up contact names
    
    def _load_last_id(self) -> int:
        """Load last processed message ID from state file."""
        if self.state_file.exists():
            try:
                return int(self.state_file.read_text().strip())
            except:
                pass
        
        # Get current max ID (skip existing messages on first run)
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(ROWID) FROM message")
            result = cursor.fetchone()[0]
            conn.close()
            return result or 0
        except:
            return 0
    
    def _save_state(self):
        """Save current position."""
        self.state_file.write_text(str(self.last_message_id))
    
    def _convert_timestamp(self, timestamp: int) -> datetime:
        """Convert Apple timestamp to Python datetime."""
        if timestamp is None:
            return datetime.now()
        if timestamp > 1e12:
            timestamp = timestamp / 1e9
        return datetime.fromtimestamp(timestamp + self.APPLE_EPOCH_OFFSET)
    
    def fetch_new_messages(self) -> list:
        """Fetch messages newer than last processed ID."""
        messages = []
        
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = """
                SELECT 
                    m.ROWID, m.text, m.date, m.is_from_me, m.service,
                    h.id as handle_id
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                WHERE m.ROWID > ?
                ORDER BY m.ROWID ASC
            """
            cursor.execute(query, (self.last_message_id,))
            
            for row in cursor.fetchall():
                # Skip sent messages unless configured to include them
                if row['is_from_me'] and not self.config.get('include_sent_messages', False):
                    self.last_message_id = row['ROWID']
                    continue
                
                # Skip empty messages
                if not row['text']:
                    self.last_message_id = row['ROWID']
                    continue
                
                # Apply contact filter if specified
                filter_contacts = self.config.get('filter_contacts', [])
                if filter_contacts and row['handle_id'] not in filter_contacts:
                    self.last_message_id = row['ROWID']
                    continue
                
                # Get contact name if available, otherwise use phone/email
                handle_id = row['handle_id'] or 'Unknown'
                contact_name = self.contacts.get_name(handle_id)
                
                messages.append({
                    'id': row['ROWID'],
                    'text': row['text'],
                    'timestamp': self._convert_timestamp(row['date']),
                    'sender': contact_name or handle_id,  # Use name if found
                    'sender_id': handle_id,  # Keep the raw phone/email too
                    'is_from_me': bool(row['is_from_me']),
                })
                self.last_message_id = row['ROWID']
            
            conn.close()
            
        except Exception as e:
            logger.error(f"Database error: {e}")
        
        return messages


# =============================================================================
# RECEIPT FORMATTING
# =============================================================================

def format_receipt(message: dict, config: dict) -> str:
    """Format a message as a thermal printer receipt."""
    width = config.get('paper_width_chars', 32)
    
    lines = []
    
    # Top border
    if config.get('decorative_border', True):
        lines.append("=" * width)
    
    # Timestamp
    if config.get('show_timestamp', True):
        ts = message['timestamp'].strftime("%b %d, %I:%M %p")
        lines.append(ts.center(width))
    
    # Sender
    if config.get('show_sender', True):
        sender = message['sender']
        if len(sender) > width - 6:
            sender = sender[:width - 9] + "..."
        lines.append(f"From: {sender}"[:width])
    
    # Divider
    if config.get('decorative_border', True):
        lines.append("-" * width)
    
    # Message text (word-wrapped)
    wrapped = textwrap.wrap(message['text'], width=width)
    lines.extend(wrapped)
    
    # Bottom border
    if config.get('decorative_border', True):
        lines.append("=" * width)
    
    return "\n".join(lines)


# =============================================================================
# CONFIGURATION
# =============================================================================

def load_config() -> dict:
    """Load configuration from config.json."""
    config_file = Path(__file__).parent / "config.json"
    
    if config_file.exists():
        with open(config_file) as f:
            return json.load(f)
    
    # Default configuration
    return {
        "poll_interval_seconds": 2,
        "filter_contacts": [],
        "include_sent_messages": False,
        "paper_width_chars": 32,
        "show_timestamp": True,
        "show_sender": True,
        "decorative_border": True
    }


def check_database_access() -> bool:
    """Verify we can access the Messages database."""
    db_path = os.path.expanduser("~/Library/Messages/chat.db")
    
    if not os.path.exists(db_path):
        print("❌ Messages database not found")
        return False
    
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM message")
        count = cursor.fetchone()[0]
        conn.close()
        print(f"✓ Messages database accessible ({count:,} messages)")
        return True
    except sqlite3.OperationalError:
        print("❌ Permission denied!")
        print("\n  To fix this:")
        print("  1. Open System Settings → Privacy & Security → Full Disk Access")
        print("  2. Add Terminal (or your IDE) to the list")
        print("  3. Restart Terminal and try again")
        return False


# =============================================================================
# COMMANDS
# =============================================================================

async def cmd_scan():
    """Scan for BLE printers."""
    print("\n🔍 Scanning for BLE devices...")
    print("=" * 50)
    
    devices = await BleakScanner.discover(timeout=10.0)
    
    print(f"\nFound {len(devices)} devices:\n")
    
    for device in sorted(devices, key=lambda d: d.name or "zzz"):
        name = device.name or "(unnamed)"
        marker = " ⭐" if "PT" in name.upper() else ""
        print(f"  {name}{marker}")
        print(f"    Address: {device.address}")
        print()
    
    print("=" * 50)
    print("Look for 'PT-210' or similar in the list above.")
    print("If not found, make sure the printer is ON.")


async def cmd_test():
    """Test BLE connection and print."""
    print("\n🖨️  BLE Printer Test")
    print("=" * 50)
    
    printer = BLEPrinter()
    
    if not await printer.connect():
        print("\n❌ Could not connect to printer")
        print("   Run --scan to see available devices")
        return
    
    print("\nSending test message...")
    
    test_text = "================================\n"
    test_text += "        TEST PRINT\n"
    test_text += "================================\n"
    test_text += "If you can read this,\n"
    test_text += "your printer is working!\n"
    test_text += "================================\n"
    
    if await printer.print_text(test_text):
        print("✓ Test sent successfully!")
    else:
        print("✗ Print failed")
    
    await printer.disconnect()


async def cmd_explore():
    """Explore printer's BLE services."""
    print("\n🔎 Exploring PT-210 BLE Services")
    print("=" * 50)
    
    printer = BLEPrinter()
    
    if not await printer.discover():
        print("❌ Printer not found")
        return
    
    try:
        async with BleakClient(printer.device_address) as client:
            print(f"\nConnected to: {printer.device_address}\n")
            
            for service in client.services:
                is_print_service = PT210_SERVICE_UUID.lower() in service.uuid.lower()
                marker = " ⭐ PRINT SERVICE" if is_print_service else ""
                print(f"📦 Service: {service.uuid}{marker}")
                
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    print(f"   └─ {char.uuid}")
                    print(f"      Properties: {props}")
                print()
    
    except Exception as e:
        print(f"Error: {e}")


async def cmd_monitor():
    """Main monitoring loop."""
    print()
    print("=" * 50)
    print("  📱➡️🖨️  Text-to-Print")
    print("=" * 50)
    print()
    
    # Check database access
    if not check_database_access():
        return
    
    config = load_config()
    monitor = MessageMonitor(config)
    printer = BLEPrinter()
    
    # Connect to printer
    print("\nConnecting to printer via BLE...")
    if not await printer.connect():
        print("❌ Could not connect to printer")
        print("   Run with --scan to find available devices")
        return
    
    print()
    print("Configuration:")
    print(f"  Poll interval: {config.get('poll_interval_seconds', 2)}s")
    print(f"  Filter contacts: {config.get('filter_contacts') or 'All'}")
    print(f"  Include sent: {config.get('include_sent_messages', False)}")
    print()
    print("-" * 50)
    logger.info("Monitoring for new messages... (Ctrl+C to stop)")
    
    try:
        while True:
            messages = monitor.fetch_new_messages()
            
            for msg in messages:
                # Log the message
                direction = "→" if msg['is_from_me'] else "←"
                preview = msg['text'][:40] + "..." if len(msg['text']) > 40 else msg['text']
                
                # Show name and number if different
                sender_display = msg['sender']
                if msg.get('sender_id') and msg['sender'] != msg['sender_id']:
                    sender_display = f"{msg['sender']} ({msg['sender_id']})"
                
                logger.info(f"{direction} {sender_display}: {preview}")
                
                # Format and print
                receipt = format_receipt(msg, config)
                
                if await printer.print_text(receipt):
                    logger.info("  ✓ Printed!")
                else:
                    logger.error("  ✗ Print failed, reconnecting...")
                    await printer.connect()
            
            if messages:
                monitor._save_state()
            
            await asyncio.sleep(config.get('poll_interval_seconds', 2))
            
    except KeyboardInterrupt:
        print("\n\nStopping...")
        monitor._save_state()
        await printer.disconnect()
        print("Goodbye! 👋")


# =============================================================================
# MAIN
# =============================================================================

async def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == '--scan':
            await cmd_scan()
        elif cmd == '--test':
            await cmd_test()
        elif cmd == '--explore':
            await cmd_explore()
        elif cmd == '--help' or cmd == '-h':
            print(__doc__)
        else:
            print(f"Unknown command: {cmd}")
            print("Run with --help for usage")
    else:
        await cmd_monitor()


if __name__ == "__main__":
    asyncio.run(main())
