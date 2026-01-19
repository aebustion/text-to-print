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

# Emoji to ASCII/Emoticon mapping
EMOJI_MAP = {
    # Smileys
    '😀': ':D', '😃': ':D', '😄': ':D', '😁': ':D', '😆': 'XD',
    '😅': "':D", '🤣': 'XD', '😂': ":'D", '🙂': ':)', '🙃': '(:', 
    '😉': ';)', '😊': ':)', '😇': '0:)', '🥰': ':)', '😍': '<3_<3',
    '🤩': '*_*', '😘': ':*', '😗': ':*', '😚': ':*', '😙': ':*',
    '🥲': ":')", '😋': ':P', '😛': ':P', '😜': ';P', '🤪': ';P',
    '😝': 'XP', '🤑': '$_$', '🤗': '(hug)', '🤭': ':x', '🤫': 'shh',
    '🤔': ':/', '🤐': ':X', '🤨': 'o_O', '😐': ':|', '😑': '-_-',
    '😶': ':', '😏': ';)', '😒': '-_-', '🙄': '9_9', '😬': ':E',
    '🤥': ':^)', '😌': ':)', '😔': ':(', '😪': ':_(', '🤤': ':)~',
    '😴': 'zzZ', '😷': ':mask:', '🤒': ':sick:', '🤕': ':hurt:',
    '🤢': ':X', '🤮': ':P~~', '🤧': ':achoo:', '🥵': ':hot:',
    '🥶': ':cold:', '🥴': ':~)', '😵': 'X_X', '🤯': ':boom:',
    '🤠': ':cowboy:', '🥳': ':party:', '🥸': ':disguise:',
    '😎': 'B)', '🤓': '8)', '🧐': '-O-', 
    '😕': ':/', '😟': ':(', '🙁': ':(', '😮': ':O', '😯': ':O',
    '😲': ':O', '😳': ':$', '🥺': ';_;', '😦': 'D:', '😧': 'D:',
    '😨': 'D:', '😰': "D':", '😥': ":'(", '😢': ":'(", '😭': ":'((",
    '😱': ':scream:', '😖': '>_<', '😣': '>_<', '😞': ':(', 
    '😓': "':(",  '😩': 'D:', '😫': 'D:', '🥱': ':yawn:',
    '😤': '>:(', '😡': '>:(', '😠': '>:(', '🤬': ':@#$!',
    '😈': '>:)', '👿': '>:)', '💀': ':skull:', '☠️': ':skull:',
    '💩': ':poop:', '🤡': ':clown:', '👹': ':ogre:', '👺': ':goblin:',
    '👻': ':ghost:', '👽': ':alien:', '👾': ':alien:', '🤖': ':robot:',
    
    # Gestures
    '👋': '(wave)', '🤚': '(hand)', '🖐️': '(hand)', '✋': '(hand)',
    '🖖': '(vulcan)', '👌': '(ok)', '🤌': '(pinch)', '🤏': '(tiny)',
    '✌️': '(peace)', '🤞': '(crossed)', '🤟': '(ILY)', '🤘': '(rock)',
    '🤙': '(call me)', '👈': '<--', '👉': '-->', '👆': '(up)',
    '👇': '(down)', '☝️': '(1)', '👍': '(thumbs up)', '👎': '(thumbs down)',
    '✊': '(fist)', '👊': '(punch)', '🤛': '(fist)', '🤜': '(fist)',
    '👏': '(clap)', '🙌': '(hooray)', '👐': '(open hands)', '🤲': '(palms)',
    '🤝': '(handshake)', '🙏': '(pray)', '✍️': '(writing)',
    '💪': '(flex)', '🦾': '(robot arm)', '🦿': '(leg)',
    
    # Hearts & Love
    '❤️': '<3', '🧡': '<3', '💛': '<3', '💚': '<3', '💙': '<3',
    '💜': '<3', '🖤': '<3', '🤍': '<3', '🤎': '<3', '💔': '</3',
    '❣️': '<3', '💕': '<3<3', '💞': '<3', '💓': '<3', '💗': '<3',
    '💖': '<3*', '💘': '<3--', '💝': '<3', '💟': '<3',
    '😻': '<3_<3', '💑': '(couple)', '💏': '(kiss)',
    
    # Misc symbols
    '✨': '*', '🌟': '*', '⭐': '*', '💫': '*', '✴️': '*',
    '🔥': '(fire)', '💥': '(boom)', '💢': '(angry)', '💦': '(sweat)',
    '💨': '(wind)', '🕳️': '(hole)', '💣': '(bomb)', '💬': '(chat)',
    '🗨️': '(chat)', '🗯️': '(angry chat)', '💭': '(thought)',
    '💤': 'zzZ', '🎵': '(music)', '🎶': '(music)', '🎼': '(music)',
    '❗': '!', '❕': '!', '❓': '?', '❔': '?', '‼️': '!!',
    '⁉️': '?!', '💯': '(100)', '🔴': '(o)', '🟢': '(o)', '🔵': '(o)',
    '✅': '[v]', '❌': '[x]', '⭕': '(o)', '🚫': '(no)',
    '➡️': '-->', '⬅️': '<--', '⬆️': '(up)', '⬇️': '(down)',
    '↩️': '<-', '↪️': '->', '🔄': '(refresh)',
    
    # Weather
    '☀️': '(sun)', '🌤️': '(sun)', '⛅': '(cloud)', '🌥️': '(cloud)',
    '☁️': '(cloud)', '🌦️': '(rain)', '🌧️': '(rain)', '⛈️': '(storm)',
    '🌩️': '(lightning)', '🌨️': '(snow)', '❄️': '(snow)', '☃️': '(snowman)',
    '⛄': '(snowman)', '🌪️': '(tornado)', '🌈': '(rainbow)',
    
    # Animals
    '🐶': '(dog)', '🐱': '(cat)', '🐭': '(mouse)', '🐹': '(hamster)',
    '🐰': '(bunny)', '🦊': '(fox)', '🐻': '(bear)', '🐼': '(panda)',
    '🐨': '(koala)', '🐯': '(tiger)', '🦁': '(lion)', '🐮': '(cow)',
    '🐷': '(pig)', '🐸': '(frog)', '🐵': '(monkey)', '🙈': '(see no evil)',
    '🙉': '(hear no evil)', '🙊': '(speak no evil)', '🐔': '(chicken)',
    '🐧': '(penguin)', '🐦': '(bird)', '🦆': '(duck)', '🦅': '(eagle)',
    '🦉': '(owl)', '🦇': '(bat)', '🐺': '(wolf)', '🐗': '(boar)',
    '🐴': '(horse)', '🦄': '(unicorn)', '🐝': '(bee)', '🐛': '(bug)',
    '🦋': '(butterfly)', '🐌': '(snail)', '🐞': '(ladybug)',
    '🐜': '(ant)', '🦟': '(mosquito)', '🐢': '(turtle)', '🐍': '(snake)',
    '🦎': '(lizard)', '🦖': '(dino)', '🦕': '(dino)', '🐙': '(octopus)',
    '🦑': '(squid)', '🦐': '(shrimp)', '🦞': '(lobster)', '🦀': '(crab)',
    '🐡': '(fish)', '🐠': '(fish)', '🐟': '(fish)', '🐬': '(dolphin)',
    '🐳': '(whale)', '🐋': '(whale)', '🦈': '(shark)',
    
    # Food & Drink
    '🍎': '(apple)', '🍐': '(pear)', '🍊': '(orange)', '🍋': '(lemon)',
    '🍌': '(banana)', '🍉': '(watermelon)', '🍇': '(grapes)', '🍓': '(strawberry)',
    '🍈': '(melon)', '🍒': '(cherry)', '🍑': '(peach)', '🥭': '(mango)',
    '🍍': '(pineapple)', '🥝': '(kiwi)', '🍅': '(tomato)', '🥑': '(avocado)',
    '🥦': '(broccoli)', '🥬': '(lettuce)', '🥒': '(cucumber)', '🌶️': '(pepper)',
    '🌽': '(corn)', '🥕': '(carrot)', '🧄': '(garlic)', '🧅': '(onion)',
    '🥔': '(potato)', '🍠': '(sweet potato)', '🥐': '(croissant)',
    '🥯': '(bagel)', '🍞': '(bread)', '🥖': '(baguette)', '🥨': '(pretzel)',
    '🧀': '(cheese)', '🥚': '(egg)', '🍳': '(cooking)', '🧈': '(butter)',
    '🥞': '(pancakes)', '🧇': '(waffle)', '🥓': '(bacon)', '🥩': '(steak)',
    '🍗': '(chicken)', '🍖': '(meat)', '🌭': '(hotdog)', '🍔': '(burger)',
    '🍟': '(fries)', '🍕': '(pizza)', '🥪': '(sandwich)', '🥙': '(pita)',
    '🧆': '(falafel)', '🌮': '(taco)', '🌯': '(burrito)', '🥗': '(salad)',
    '🍝': '(pasta)', '🍜': '(ramen)', '🍲': '(stew)', '🍛': '(curry)',
    '🍣': '(sushi)', '🍱': '(bento)', '🥟': '(dumpling)', '🍤': '(shrimp)',
    '🍙': '(rice ball)', '🍚': '(rice)', '🍘': '(rice cracker)',
    '🍥': '(fish cake)', '🥠': '(fortune cookie)', '🥡': '(takeout)',
    '🍦': '(ice cream)', '🍧': '(shaved ice)', '🍨': '(sundae)',
    '🍩': '(donut)', '🍪': '(cookie)', '🎂': '(cake)', '🍰': '(cake slice)',
    '🧁': '(cupcake)', '🥧': '(pie)', '🍫': '(chocolate)', '🍬': '(candy)',
    '🍭': '(lollipop)', '🍮': '(pudding)', '🍯': '(honey)',
    '🍼': '(bottle)', '🥛': '(milk)', '☕': '(coffee)', '🍵': '(tea)',
    '🧃': '(juice box)', '🥤': '(drink)', '🍶': '(sake)', '🍺': '(beer)',
    '🍻': '(cheers)', '🥂': '(champagne)', '🍷': '(wine)', '🥃': '(whiskey)',
    '🍸': '(cocktail)', '🍹': '(tropical)', '🧊': '(ice)',
    
    # Activities
    '⚽': '(soccer)', '🏀': '(basketball)', '🏈': '(football)', '⚾': '(baseball)',
    '🥎': '(softball)', '🎾': '(tennis)', '🏐': '(volleyball)', '🏉': '(rugby)',
    '🥏': '(frisbee)', '🎱': '(pool)', '🏓': '(ping pong)', '🏸': '(badminton)',
    '🎮': '(gaming)', '🎲': '(dice)', '🧩': '(puzzle)', '🎯': '(bullseye)',
    '🎳': '(bowling)', '🎪': '(circus)', '🎭': '(theater)', '🎨': '(art)',
    '🎬': '(movie)', '🎤': '(mic)', '🎧': '(headphones)', '🎸': '(guitar)',
    '🎹': '(piano)', '🥁': '(drums)', '🎷': '(sax)', '🎺': '(trumpet)',
    '🎻': '(violin)', '🪕': '(banjo)', '📷': '(camera)', '📸': '(camera)',
    '📹': '(video)', '📺': '(tv)', '📻': '(radio)', '📱': '(phone)',
    '💻': '(laptop)', '⌨️': '(keyboard)', '🖥️': '(computer)', '🖨️': '(printer)',
    
    # Celebrations
    '🎉': '(party)', '🎊': '(confetti)', '🎈': '(balloon)', '🎁': '(gift)',
    '🎀': '(ribbon)', '🏆': '(trophy)', '🏅': '(medal)', '🥇': '(gold)',
    '🥈': '(silver)', '🥉': '(bronze)', '🎖️': '(medal)',
}


def prepare_image_for_print(image_path: str, max_width: int = 384) -> Optional[bytes]:
    """
    Convert an image to ESC/POS bitmap format for thermal printing.
    
    Args:
        image_path: Path to the image file
        max_width: Maximum width in pixels (384 for 58mm paper, 576 for 80mm)
    
    Returns:
        ESC/POS bitmap data, or None if conversion fails
    """
    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow not installed. Run: pip3 install Pillow")
        return None
    
    try:
        # Open and convert image
        img = Image.open(image_path)
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Resize to fit paper width while maintaining aspect ratio
        width, height = img.size
        if width > max_width:
            ratio = max_width / width
            new_height = int(height * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        # Ensure width is divisible by 8 (required for bitmap)
        width, height = img.size
        if width % 8 != 0:
            new_width = (width // 8 + 1) * 8
            new_img = Image.new('L', (new_width, height), 255)
            new_img.paste(img, (0, 0))
            img = new_img
        
        width, height = img.size
        
        # Convert to 1-bit using dithering for better quality
        img = img.convert('1')
        
        # Convert to ESC/POS bitmap format
        # Using ESC * command (bit image mode)
        data = bytearray()
        
        # Process image row by row
        for y in range(height):
            # ESC * m nL nH - Select bit image mode
            # m = 0 (8-dot single density), 1 (8-dot double density), 32 (24-dot single), 33 (24-dot double)
            # We use mode 0 for simplicity
            n = width
            nL = n % 256
            nH = n // 256
            
            data.extend(b'\x1b\x2a\x00')  # ESC * 0
            data.append(nL)
            data.append(nH)
            
            # Each byte represents 8 horizontal pixels
            for x in range(0, width, 8):
                byte = 0
                for bit in range(8):
                    if x + bit < width:
                        pixel = img.getpixel((x + bit, y))
                        if pixel == 0:  # Black pixel
                            byte |= (1 << (7 - bit))
                data.append(byte)
            
            # Line feed after each row
            data.extend(b'\x0a')
        
        return bytes(data)
        
    except Exception as e:
        logger.error(f"Image conversion error: {e}")
        return None


def convert_emojis(text: str) -> str:
    """Convert emojis in text to ASCII emoticons."""
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)
    
    # Replace any remaining emojis with [?]
    # This catches emojis not in our dictionary
    import re
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"  # dingbats
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols
        "\U00002600-\U000026FF"  # misc symbols
        "]+", 
        flags=re.UNICODE
    )
    text = emoji_pattern.sub('[?]', text)
    
    return text


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
    
    async def print_image(self, image_path: str) -> bool:
        """Print an image to the thermal printer."""
        if not self.client or not self.client.is_connected:
            logger.error("Not connected to printer")
            return False
        
        if not self.write_characteristic:
            logger.error("No write characteristic available")
            return False
        
        # Convert image to ESC/POS format
        image_data = prepare_image_for_print(image_path)
        if not image_data:
            logger.error("Failed to prepare image")
            return False
        
        try:
            # Initialize printer
            await self.client.write_gatt_char(
                self.write_characteristic,
                ESC_INIT,
                response=False
            )
            await asyncio.sleep(0.1)
            
            # Send image data in chunks
            chunk_size = 20
            for i in range(0, len(image_data), chunk_size):
                chunk = image_data[i:i + chunk_size]
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
            
            # Paper feed
            await self.client.write_gatt_char(
                self.write_characteristic,
                LINE_FEED * 2,
                response=False
            )
            
            logger.info("✓ Image sent to printer")
            return True
            
        except Exception as e:
            logger.error(f"Image print error: {e}")
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
    
    def _get_attachments(self, message_id: int, cursor) -> list:
        """Get attachment information for a message."""
        attachments = []
        
        try:
            cursor.execute("""
                SELECT 
                    a.filename,
                    a.mime_type,
                    a.transfer_name
                FROM attachment a
                JOIN message_attachment_join maj ON a.ROWID = maj.attachment_id
                WHERE maj.message_id = ?
            """, (message_id,))
            
            for row in cursor.fetchall():
                filename = row[0] or row[2] or 'attachment'
                mime_type = row[1] or ''
                
                # Determine attachment type
                if mime_type.startswith('image/'):
                    att_type = 'image'
                elif mime_type.startswith('video/'):
                    att_type = 'video'
                elif mime_type.startswith('audio/'):
                    att_type = 'audio'
                else:
                    att_type = 'file'
                
                # Get the full path (attachments are stored in ~/Library/Messages/Attachments)
                if filename and filename.startswith('~'):
                    filepath = os.path.expanduser(filename)
                else:
                    filepath = filename
                
                attachments.append({
                    'type': att_type,
                    'mime_type': mime_type,
                    'filename': os.path.basename(filename) if filename else 'attachment',
                    'filepath': filepath,
                })
        
        except Exception as e:
            logger.debug(f"Error getting attachments: {e}")
        
        return attachments
    
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
                    m.cache_has_attachments,
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
                
                # Check for attachments (images, etc.)
                has_attachment = bool(row['cache_has_attachments'])
                attachments = []
                
                if has_attachment:
                    attachments = self._get_attachments(row['ROWID'], cursor)
                
                messages.append({
                    'id': row['ROWID'],
                    'text': row['text'] or '',
                    'timestamp': self._convert_timestamp(row['date']),
                    'sender': contact_name or handle_id,  # Use name if found
                    'sender_id': handle_id,  # Keep the raw phone/email too
                    'is_from_me': bool(row['is_from_me']),
                    'has_attachment': has_attachment,
                    'attachments': attachments,
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
    
    # Message text (word-wrapped) with emoji conversion
    text = message.get('text', '')
    if text:
        text = convert_emojis(text)  # Convert emojis to ASCII
        wrapped = textwrap.wrap(text, width=width)
        lines.extend(wrapped)
    
    # Show attachments
    attachments = message.get('attachments', [])
    if attachments:
        for att in attachments:
            att_type = att['type']
            if att_type == 'image':
                lines.append(f"[Image: {att['filename']}]"[:width])
            elif att_type == 'video':
                lines.append(f"[Video: {att['filename']}]"[:width])
            elif att_type == 'audio':
                lines.append(f"[Audio: {att['filename']}]"[:width])
            else:
                lines.append(f"[File: {att['filename']}]"[:width])
    
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
                
                # Print images if enabled
                if config.get('print_images', False):
                    for att in msg.get('attachments', []):
                        if att['type'] == 'image' and att.get('filepath'):
                            filepath = att['filepath']
                            if os.path.exists(filepath):
                                logger.info(f"  Printing image: {att['filename']}")
                                if await printer.print_image(filepath):
                                    logger.info("  ✓ Image printed!")
                                else:
                                    logger.warning("  ⚠ Image print failed")
            
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
