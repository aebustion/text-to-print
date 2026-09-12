#!/usr/bin/env python3
"""
📱➡️🖨️ Text-to-Print (Mac Only Edition)

Automatically prints incoming messages to a Bluetooth thermal printer.

Messages come from the local Beeper Desktop API, so any network Beeper
connects -- iMessage, WhatsApp, Instagram and the rest -- can print.
Printing uses Bluetooth Low Energy, and works with GOOJPRT PT-210 and
other generic BLE thermal printers.

Requires Beeper Desktop to be running, with BEEPER_ACCESS_TOKEN set in a
local .env file (see .env.example).

Usage:
    python3 text_printer.py              Run the message monitor
    python3 text_printer.py --scan       Scan for BLE printers
    python3 text_printer.py --test       Test print via BLE
    python3 text_printer.py --explore    Explore printer's BLE services
"""

import asyncio
import sys
import os
import json
import re
import html
import shutil
import mimetypes
import subprocess
import tempfile
import textwrap
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
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

# Beeper Desktop API client
try:
    import requests
except ImportError:
    print("❌ requests library not installed!")
    print("   Run: pip3 install requests")
    sys.exit(1)

# Load BEEPER_ACCESS_TOKEN from a local .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# =============================================================================
# BLE PRINTER CONSTANTS
# =============================================================================

# Known printer service UUIDs (will try these in order, then fall back to discovery)
KNOWN_PRINT_SERVICE_UUIDS = [
    "e7810a71-73ae-499d-8c15-faa9aef0c3f2",  # PT-210 / GOOJPRT
    "49535343-fe7d-4ae5-8fa9-9fafd205e455",  # Common thermal printer service
    "000018f0-0000-1000-8000-00805f9b34fb",  # Another common printer service
]

# Known write characteristic UUIDs
KNOWN_WRITE_CHAR_UUIDS = [
    "bef8d6c9-9c21-4c9e-b632-bd58c1009f9f",  # PT-210 / GOOJPRT
    "49535343-8841-43f4-a8d4-ecbe34729bb3",  # Common thermal printer write char
    "49535343-1e4d-4bd9-ba61-23c647249616",  # Another common write char
]

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


def _convert_heic_to_pil(image_path: str):
    """
    Convert HEIC image to PIL Image.
    Uses pillow-heif if available, otherwise falls back to macOS sips command.
    """
    from PIL import Image
    import subprocess
    import tempfile
    
    # Method 1: Try pillow-heif (if installed)
    try:
        import pillow_heif
        heif_file = pillow_heif.read_heif(image_path)
        img = Image.frombytes(
            heif_file.mode,
            heif_file.size,
            heif_file.data,
            "raw",
        )
        return img
    except ImportError:
        pass
    except Exception as e:
        logger.debug(f"pillow-heif failed: {e}")
    
    # Method 2: Use macOS sips to convert (built-in on all Macs)
    try:
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            tmp_path = tmp.name
        
        # Use sips to convert HEIC to JPEG
        result = subprocess.run(
            ['sips', '-s', 'format', 'jpeg', image_path, '--out', tmp_path],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0 and os.path.exists(tmp_path):
            img = Image.open(tmp_path)
            img.load()  # Load image data before we delete the file
            os.unlink(tmp_path)  # Clean up temp file
            return img
        else:
            logger.error(f"sips conversion failed: {result.stderr}")
    except Exception as e:
        logger.error(f"HEIC conversion error: {e}")

    return None


@contextmanager
def video_poster_frame(video_path: str, mime_type: str = '', filename: str = ''):
    """
    Yield a path to a still frame extracted from a video, or None on failure.

    Uses macOS Quick Look (`qlmanage`), which is built in, so shared Instagram
    reels and other video attachments can be printed without requiring ffmpeg.

    Quick Look picks its generator from the file extension, and Beeper stores
    media under extensionless content-hash filenames, so the video is staged to
    a correctly-suffixed temp copy first. The temp directory (and the extracted
    frame in it) is removed when the caller is done.
    """
    tmpdir = tempfile.mkdtemp(prefix='text-to-print-')
    frame = None

    try:
        # Prefer the original filename's extension: iMessage attachments carry a
        # real name (ScreenRecording....mov) but no mimeType, while Instagram is
        # the reverse -- a mimeType with an extensionless content-hash path.
        ext = (
            os.path.splitext(filename or '')[1]
            or mimetypes.guess_extension(mime_type or '')
            or os.path.splitext(video_path)[1]
            or '.mp4'
        )
        staged = os.path.join(tmpdir, f'video{ext}')
        shutil.copyfile(video_path, staged)

        subprocess.run(
            ['qlmanage', '-t', '-s', '512', '-o', tmpdir, staged],
            capture_output=True,
            timeout=60,
        )

        thumbnails = [f for f in os.listdir(tmpdir) if f.lower().endswith('.png')]
        if thumbnails:
            frame = os.path.join(tmpdir, thumbnails[0])
        else:
            logger.debug(f"Quick Look produced no frame for {video_path}")

    except Exception as e:
        logger.debug(f"Video frame extraction failed: {e}")

    try:
        yield frame
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def prepare_image_for_print(image_path: str, max_width: int = 384) -> Optional[bytes]:
    """
    Convert an image to ESC/POS raster bitmap format for thermal printing.
    
    Args:
        image_path: Path to the image file
        max_width: Maximum width in pixels (384 for 58mm paper, 576 for 80mm)
    
    Returns:
        ESC/POS bitmap data, or None if conversion fails
    """
    try:
        from PIL import Image, ImageOps, ImageEnhance
    except ImportError:
        logger.warning("Pillow not installed. Run: pip3 install Pillow")
        return None
    
    # Try to register HEIC support
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
    except ImportError:
        pass  # HEIC support not available, will try conversion fallback
    
    try:
        # Check if it's a HEIC file that needs conversion
        if image_path.lower().endswith(('.heic', '.heif')):
            img = _convert_heic_to_pil(image_path)
            if img is None:
                logger.error("Could not convert HEIC image")
                return None
        else:
            # Open image normally
            img = Image.open(image_path)
        
        # Handle rotation from EXIF data
        try:
            img = ImageOps.exif_transpose(img)
        except:
            pass
        
        # Convert to grayscale
        img = img.convert('L')
        
        # Increase contrast for better thermal printing
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.5)
        
        # Resize to fit paper width while maintaining aspect ratio
        width, height = img.size
        if width > max_width:
            ratio = max_width / width
            new_height = int(height * ratio)
            try:
                resample = Image.Resampling.LANCZOS
            except AttributeError:
                resample = Image.LANCZOS
            img = img.resize((max_width, new_height), resample)
        
        # Ensure width is divisible by 8
        width, height = img.size
        if width % 8 != 0:
            new_width = (width // 8) * 8
            img = img.crop((0, 0, new_width, height))
        
        width, height = img.size
        bytes_per_row = width // 8
        
        # Convert to 1-bit black and white with dithering
        img = img.convert('1')
        
        # Build ESC/POS raster image command
        # GS v 0 - Print raster bit image
        data = bytearray()
        
        # GS v 0 m xL xH yL yH d1...dk
        # m = 0 (normal), 1 (double width), 2 (double height), 3 (double both)
        data.extend(b'\x1d\x76\x30\x00')  # GS v 0, mode 0
        
        # xL xH = width in bytes
        data.append(bytes_per_row % 256)
        data.append(bytes_per_row // 256)
        
        # yL yH = height in dots
        data.append(height % 256)
        data.append(height // 256)
        
        # Image data - row by row
        for y in range(height):
            for x in range(0, width, 8):
                byte = 0
                for bit in range(8):
                    if x + bit < width:
                        pixel = img.getpixel((x + bit, y))
                        if pixel == 0:  # Black pixel
                            byte |= (1 << (7 - bit))
                data.append(byte)
        
        return bytes(data)
        
    except Exception as e:
        logger.error(f"Image conversion error: {e}")
        import traceback
        traceback.print_exc()
        return None


# Typographic characters that phones insert automatically. The printer only
# speaks ASCII, so without these "don't" would print as "don?t".
SMART_PUNCT_MAP = {
    '‘': "'", '’': "'", '‚': ",", '‛': "'",   # single quotes
    '“': '"', '”': '"', '„': '"', '‟': '"',   # double quotes
    '–': '-', '—': '--', '―': '--', '−': '-',  # dashes
    '…': '...',                                               # ellipsis
    ' ': ' ', ' ': ' ', ' ': ' ', '​': '',     # spaces
    '•': '*', '·': '*',                                  # bullets
    '«': '<<', '»': '>>',                                # guillemets
    '™': '(TM)', '®': '(R)', '©': '(C)',
    '½': '1/2', '¼': '1/4', '¾': '3/4',
    '°': ' deg',
}


def convert_emojis(text: str) -> str:
    """Convert emojis and smart punctuation in text to printable ASCII."""
    for emoji, replacement in EMOJI_MAP.items():
        text = text.replace(emoji, replacement)

    for char, replacement in SMART_PUNCT_MAP.items():
        text = text.replace(char, replacement)

    # Replace any remaining emojis with [?]
    # This catches emojis not in our dictionary
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
        "\U0001F7E0-\U0001F7FF"  # geometric shapes extended (colored squares)
        "\U00002190-\U000021FF"  # arrows
        "\U00002B00-\U00002BFF"  # misc symbols & arrows
        "\U0000FE00-\U0000FE0F"  # variation selectors
        "\U0001F000-\U0001F02F"  # mahjong tiles
        "]+",
        flags=re.UNICODE
    )
    text = emoji_pattern.sub('[?]', text)

    # Strip accents so names like "José" print as "Jose" rather than "Jos?".
    # Non-Latin scripts decompose to themselves and are left for the printer's
    # encode step to handle, same as before.
    decomposed = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in decomposed if not unicodedata.combining(c))

    return text


def strip_beeper_html(text: str) -> str:
    """Convert Beeper's rich-text HTML message bodies (WhatsApp/Instagram/etc.) to plain text."""
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p>\s*<p[^>]*>', '\n\n', text, flags=re.IGNORECASE)
    text = re.sub(r'<a\b[^>]*>(.*?)</a>', r'\1', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'<[^>]+>', '', text)
    return html.unescape(text).strip()


# =============================================================================
# BLE PRINTER CLASS
# =============================================================================

class BLEPrinter:
    """Bluetooth Low Energy printer driver for thermal printers."""
    
    def __init__(self, config: dict = None):
        self.client: Optional[BleakClient] = None
        self.device_address: Optional[str] = None
        self.write_characteristic: Optional[str] = None
        self.config = config or {}
    
    async def discover(self) -> Optional[str]:
        """Discover printer via BLE scan or use configured address."""
        # PRINTER_ADDRESS in .env wins over config.json. macOS gives each Mac its
        # own BLE address for the same printer, so keeping it in the untracked
        # .env lets config.json stay machine-independent and safe to commit.
        configured_address = os.environ.get('PRINTER_ADDRESS') or self.config.get('printer_address')
        configured_name = self.config.get('printer_name', '')

        if configured_address:
            logger.info(f"Using configured printer: {configured_name or configured_address}")
            self.device_address = configured_address
            return configured_address

        logger.info("Scanning for BLE printers...")
        
        devices = await BleakScanner.discover(timeout=10.0)
        
        # Look for known printer names
        printer_keywords = ["PT-210", "PT210", "Bluetooth Printer", "BlueTooth Printer", "Printer", "PRINT", "GOOJPRT", "Thermal"]
        for device in devices:
            name = device.name or ""
            for keyword in printer_keywords:
                if keyword.upper() in name.upper():
                    logger.info(f"✓ Found printer: {device.name} ({device.address})")
                    self.device_address = device.address
                    return device.address
        
        # If not found by name, look for devices with known printer service UUIDs
        logger.info("Scanning for devices with known printer service UUIDs...")
        devices = await BleakScanner.discover(timeout=10.0, return_adv=True)
        
        for device, adv_data in devices.values():
            service_uuids = [s.lower() for s in adv_data.service_uuids]
            for known_uuid in KNOWN_PRINT_SERVICE_UUIDS:
                if known_uuid.lower() in service_uuids:
                    logger.info(f"✓ Found device with printer service: {device.name} ({device.address})")
                    self.device_address = device.address
                    return device.address
        
        logger.error("Printer not found. Make sure it's turned on and in range.")
        logger.error("You can configure the printer address in config.json")
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
        # First, check for known printer service UUIDs
        for service in self.client.services:
            service_uuid_lower = service.uuid.lower()
            for known_service in KNOWN_PRINT_SERVICE_UUIDS:
                if known_service.lower() in service_uuid_lower:
                    logger.debug(f"Found known printer service: {service.uuid}")
                    
                    for char in service.characteristics:
                        if "write" in char.properties or "write-without-response" in char.properties:
                            self.write_characteristic = char.uuid
                            logger.info(f"Using write characteristic: {char.uuid}")
                            return
        
        # Second, check for known write characteristic UUIDs directly
        for service in self.client.services:
            for char in service.characteristics:
                char_uuid_lower = char.uuid.lower()
                for known_char in KNOWN_WRITE_CHAR_UUIDS:
                    if known_char.lower() in char_uuid_lower:
                        if "write" in char.properties or "write-without-response" in char.properties:
                            self.write_characteristic = char.uuid
                            logger.info(f"Using known write characteristic: {char.uuid}")
                            return
        
        # Fallback: search all services for any writable characteristic
        # Prefer non-standard (vendor-specific) characteristics
        candidates = []
        for service in self.client.services:
            for char in service.characteristics:
                if "write" in char.properties or "write-without-response" in char.properties:
                    is_standard = char.uuid.lower().startswith("0000") and len(char.uuid) == 36
                    candidates.append((char.uuid, is_standard, service.uuid))
        
        # Sort to prefer non-standard characteristics
        candidates.sort(key=lambda x: x[1])
        
        if candidates:
            self.write_characteristic = candidates[0][0]
            logger.info(f"Using write characteristic: {self.write_characteristic}")
            logger.debug(f"  From service: {candidates[0][2]}")
            return
        
        logger.warning("No suitable write characteristic found")
        logger.warning("Run with --explore to see available services and characteristics")
    
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
        # Use smaller width for BLE to avoid overwhelming the printer
        image_data = prepare_image_for_print(image_path, max_width=256)
        if not image_data:
            logger.error("Failed to prepare image")
            return False
        
        logger.info(f"  Image data size: {len(image_data)} bytes")
        
        try:
            # Initialize printer
            await self.client.write_gatt_char(
                self.write_characteristic,
                ESC_INIT,
                response=False
            )
            await asyncio.sleep(0.2)
            
            # Send image data in larger chunks with delays
            # The GS v 0 command needs the header sent together
            chunk_size = 100  # Larger chunks for image data
            total_chunks = (len(image_data) + chunk_size - 1) // chunk_size
            
            for i in range(0, len(image_data), chunk_size):
                chunk = image_data[i:i + chunk_size]
                chunk_num = i // chunk_size + 1
                
                try:
                    await self.client.write_gatt_char(
                        self.write_characteristic,
                        chunk,
                        response=True  # Use response for reliability
                    )
                except Exception as e:
                    logger.debug(f"Chunk {chunk_num} write error: {e}")
                    # Try without response
                    await self.client.write_gatt_char(
                        self.write_characteristic,
                        chunk,
                        response=False
                    )
                
                # Longer delay to let printer process
                await asyncio.sleep(0.1)
                
                # Progress indicator for large images
                if chunk_num % 10 == 0:
                    logger.debug(f"  Sent {chunk_num}/{total_chunks} chunks")
            
            # Wait for printing to complete
            await asyncio.sleep(1.0)
            
            # Paper feed
            await self.client.write_gatt_char(
                self.write_characteristic,
                LINE_FEED * 3,
                response=False
            )
            
            logger.info("✓ Image sent to printer")
            return True
            
        except Exception as e:
            logger.error(f"Image print error: {e}")
            import traceback
            traceback.print_exc()
            return False


# =============================================================================
# BEEPER MONITOR (iMessage, WhatsApp, Instagram, ... via the Beeper Desktop API)
# =============================================================================

class BeeperMonitor:
    """
    Monitors messages via the local Beeper Desktop API.

    Works off the chat/message list endpoints rather than /v1/messages/search,
    because Beeper's macOS iMessage support is a built-in automation library
    rather than a Matrix bridge: it has no entry in /v1/accounts or /v1/bridges
    and is absent from the search index, but it does show up in /v1/chats and
    /v1/chats/{chatID}/messages alongside every bridged network.
    """

    def __init__(self, config: dict):
        self.config = config
        self.base_url = config.get('beeper_base_url', 'http://127.0.0.1:23373').rstrip('/')
        self.token = os.environ.get('BEEPER_ACCESS_TOKEN', '')
        self.networks = {n.lower() for n in config.get('beeper_networks', ['imessage', 'whatsapp', 'instagram'])}
        self.state_file = Path(__file__).parent / ".last_beeper_timestamp"

        if not self.token:
            logger.error("BEEPER_ACCESS_TOKEN is not set. Copy .env.example to .env and add your token.")
            self.enabled = False
        else:
            self.enabled = self._check_connection()

        # Only print messages that arrive after startup.
        self.floor = self._load_last_seen()

        # Newest timestamp already printed, tracked per chat rather than globally.
        # A single shared watermark loses messages: iMessage is local and instant
        # while bridged networks (WhatsApp/Instagram) sync with a delay, so a fast
        # iMessage would push a global watermark past a slower message that hadn't
        # arrived yet, skipping it permanently.
        self.chat_cursors = {}

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _report_expired_token(self):
        """Explain how to fix an expired or rejected access token."""
        logger.error("Beeper access token is expired or invalid. Beeper monitoring is off.")
        logger.error("  To fix: in Beeper Desktop go to Settings -> Integrations, click the")
        logger.error("  '+' next to 'Approved connections' to create a new token, then update")
        logger.error(f"  BEEPER_ACCESS_TOKEN in {Path(__file__).parent / '.env'} and restart.")

    def _check_connection(self) -> bool:
        """
        Verify the Beeper Desktop API is running and the token is currently valid.

        Deliberately calls an authenticated endpoint: /v1/info is served without
        auth, so it returns 200 even for an expired token and would report a
        healthy connection that then fails on every poll.
        """
        try:
            resp = requests.get(
                f"{self.base_url}/v1/chats",
                headers=self._headers(),
                timeout=5,
            )
            if resp.status_code == 401:
                self._report_expired_token()
                return False
            resp.raise_for_status()
            logger.info(f"Beeper: watching {', '.join(sorted(self.networks))}")
            return True
        except Exception as e:
            logger.warning(f"Beeper Desktop API not reachable ({e}). Disabling Beeper monitoring for this session.")
            return False

    def _fetch_active_chats(self) -> list:
        """Return watched chats that have new activity, newest first."""
        chats = []
        cursor = None

        # /v1/chats is ordered by lastActivity descending. The floor never moves,
        # so we can always stop once we reach chats last active before startup.
        for _ in range(10):  # safety cap
            params = {}
            if cursor:
                params["cursor"] = cursor
                params["direction"] = "before"

            resp = requests.get(
                f"{self.base_url}/v1/chats",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get('items', [])
            reached_old_chats = False

            for chat in items:
                last_activity = chat.get('lastActivity') or ''
                if last_activity <= self.floor:
                    reached_old_chats = True
                    break
                if (chat.get('network') or '').lower() not in self.networks:
                    continue
                # Skip chats whose activity we've already caught up on.
                if last_activity > self.chat_cursors.get(chat['id'], self.floor):
                    chats.append(chat)

            if reached_old_chats or not data.get('hasMore') or not data.get('oldestCursor'):
                break
            cursor = data['oldestCursor']

        return chats

    def _fetch_chat_messages(self, chat_id: str, since: str) -> list:
        """Return raw messages in a chat newer than `since` (newest first per page)."""
        from urllib.parse import quote

        found = []
        cursor = None
        encoded_id = quote(chat_id, safe='')

        for _ in range(10):  # safety cap: 10 * 20 = 200 messages per chat per poll
            params = {}
            if cursor:
                params["cursor"] = cursor
                params["direction"] = "before"

            resp = requests.get(
                f"{self.base_url}/v1/chats/{encoded_id}/messages",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get('items', [])
            reached_old_messages = False

            for msg in items:
                if (msg.get('timestamp') or '') <= since:
                    reached_old_messages = True
                    continue
                found.append(msg)

            if reached_old_messages or not data.get('hasMore') or not data.get('oldestCursor'):
                break
            cursor = data['oldestCursor']

        return found

    def _load_last_seen(self) -> str:
        """
        Start fresh each run: only messages arriving after startup get printed.

        Formatted to match Beeper's own timestamps (millisecond precision, 'Z'
        suffix) so the ISO strings can be compared directly.
        """
        now = datetime.now(timezone.utc)
        return f"{now.strftime('%Y-%m-%dT%H:%M:%S')}.{now.microsecond // 1000:03d}Z"

    def _save_state(self):
        self.state_file.write_text(json.dumps({
            'floor': self.floor,
            'chat_cursors': self.chat_cursors,
        }, indent=2))

    @staticmethod
    def _file_url_to_path(url: str) -> Optional[str]:
        """Convert a file:// URL to a local filesystem path."""
        if url and url.startswith('file://'):
            from urllib.parse import unquote, urlparse
            return unquote(urlparse(url).path)
        return None

    def _resolve_attachment_path(self, att: dict) -> Optional[str]:
        """
        Get a local filesystem path for an attachment.

        Beeper hands these over in two shapes: iMessage attachments come with a
        direct file:// srcURL, while bridged networks give an mxc:// id that has
        to be fetched through the download endpoint first.
        """
        path = self._file_url_to_path(att.get('srcURL') or '')
        if path:
            return path

        identifier = att.get('id') or ''
        if not identifier.startswith(('mxc://', 'localmxc://')):
            return None

        try:
            resp = requests.post(
                f"{self.base_url}/v1/assets/download",
                headers=self._headers(),
                json={"url": identifier},
                timeout=30,
            )
            resp.raise_for_status()
            src_url = resp.json().get('srcURL') or ''
            return self._file_url_to_path(src_url) or src_url or None
        except Exception as e:
            logger.debug(f"Beeper attachment download failed: {e}")
            return None

    def fetch_new_messages(self) -> list:
        """Fetch messages newer than the last processed timestamp."""
        if not self.enabled:
            return []

        messages = []

        try:
            for chat in self._fetch_active_chats():
                network = chat.get('network') or 'Beeper'
                is_group = chat.get('type') == 'group'
                chat_id = chat['id']
                since = self.chat_cursors.get(chat_id, self.floor)

                raw_messages = self._fetch_chat_messages(chat_id, since)

                # Advance this chat's cursor past everything examined, including
                # messages filtered out below, so they aren't re-fetched forever.
                for msg in raw_messages:
                    ts = msg.get('timestamp') or ''
                    if ts > self.chat_cursors.get(chat_id, since):
                        self.chat_cursors[chat_id] = ts

                for msg in raw_messages:
                    if msg.get('isDeleted') or msg.get('isHidden'):
                        continue

                    # Skip sent messages unless configured to include them
                    if msg.get('isSender') and not self.config.get('include_sent_messages', False):
                        continue

                    text = strip_beeper_html(msg.get('text') or '')
                    raw_attachments = msg.get('attachments') or []

                    # Photos and videos usually arrive with no caption at all, so
                    # only skip a message when it has neither text nor media --
                    # that leaves reactions and similar events filtered out.
                    if not text and not raw_attachments:
                        continue

                    sender = msg.get('senderName') or msg.get('senderID') or 'Unknown'

                    # Apply contact filter if specified
                    filter_contacts = self.config.get('filter_contacts', [])
                    if filter_contacts and sender not in filter_contacts and msg.get('senderID') not in filter_contacts:
                        continue

                    ts = msg.get('timestamp')
                    # Naive local datetime, so receipts show local wall-clock time
                    timestamp = datetime.fromisoformat(ts.replace('Z', '+00:00')).astimezone().replace(tzinfo=None)

                    attachments = []
                    for att in raw_attachments:
                        att_type_map = {'img': 'image', 'video': 'video', 'audio': 'audio'}
                        att_type = att_type_map.get(att.get('type'), 'file')
                        attachments.append({
                            'type': att_type,
                            'mime_type': att.get('mimeType') or '',
                            'filename': att.get('fileName') or att_type,
                            'filepath': self._resolve_attachment_path(att),
                        })

                    messages.append({
                        'id': msg.get('id'),
                        'text': text,
                        'timestamp': timestamp,
                        'sender': sender,
                        'sender_id': msg.get('senderID'),
                        'is_from_me': bool(msg.get('isSender')),
                        'has_attachment': bool(attachments),
                        'attachments': attachments,
                        'source': network,
                        'chat_title': chat.get('title') if is_group else None,
                    })

        except requests.HTTPError as e:
            # A token that expires mid-run would otherwise log this on every
            # poll; stop asking and tell the user how to fix it, once.
            if e.response is not None and e.response.status_code == 401:
                self.enabled = False
                self._report_expired_token()
            else:
                logger.error(f"Beeper API error: {e}")
        except Exception as e:
            logger.error(f"Beeper API error: {e}")

        messages.sort(key=lambda m: m['timestamp'])
        return messages


# =============================================================================
# RECEIPT FORMATTING
# =============================================================================

def format_attachment_label(att: dict) -> str:
    """
    Build the '[Image: photo.jpg]' line for an attachment.

    The filename is only worth printing when it's human-readable. iMessage gives
    real names like IMG_3820.HEIC, but Instagram/WhatsApp use long opaque CDN ids
    that would just fill a line of paper with noise.
    """
    label = {'image': 'Image', 'video': 'Video', 'audio': 'Audio'}.get(att.get('type'), 'File')
    name = att.get('filename') or ''
    _, ext = os.path.splitext(name)

    if name and ext and len(name) <= 24:
        return f"[{label}: {name}]"
    return f"[{label}]"


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
    
    # Source app (only shown for non-iMessage sources, e.g. WhatsApp/Instagram)
    source = message.get('source')
    if source and source.lower() != 'imessage':
        lines.append(f"[{source}]"[:width])

    # Group chat title
    chat_title = message.get('chat_title')
    if chat_title:
        lines.append(f"In: {convert_emojis(chat_title)}"[:width])

    # Sender
    if config.get('show_sender', True):
        sender = convert_emojis(message['sender'])
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
    for att in message.get('attachments', []):
        lines.append(format_attachment_label(att)[:width])
    
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
        "decorative_border": True,
        "print_images": True,
        "print_video_frames": True,
        "beeper_networks": ["imessage", "whatsapp", "instagram"],
        "beeper_base_url": "http://127.0.0.1:23373",
    }


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
    
    config = load_config()
    printer = BLEPrinter(config)
    
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
    print("\n🔎 Exploring Printer BLE Services")
    print("=" * 50)
    
    config = load_config()
    printer = BLEPrinter(config)
    
    if not await printer.discover():
        print("❌ Printer not found")
        return
    
    try:
        async with BleakClient(printer.device_address) as client:
            print(f"\nConnected to: {printer.device_address}\n")
            
            for service in client.services:
                # Check if this is a known print service
                is_print_service = any(
                    known.lower() in service.uuid.lower() 
                    for known in KNOWN_PRINT_SERVICE_UUIDS
                )
                marker = " ⭐ PRINT SERVICE" if is_print_service else ""
                print(f"📦 Service: {service.uuid}{marker}")
                
                for char in service.characteristics:
                    props = ", ".join(char.properties)
                    is_write = "write" in char.properties or "write-without-response" in char.properties
                    write_marker = " ✏️  WRITABLE" if is_write else ""
                    print(f"   └─ {char.uuid}{write_marker}")
                    print(f"      Properties: {props}")
                print()
    
    except Exception as e:
        print(f"Error: {e}")


def is_readable(path: str) -> bool:
    """
    Check a file can actually be opened.

    os.path.exists() is not enough: macOS reports protected paths such as
    ~/Library/Messages/Attachments as existing, then denies the read. iMessage
    media lives there, so without Full Disk Access it looks present but isn't.
    """
    try:
        with open(path, 'rb') as f:
            f.read(1)
        return True
    except (PermissionError, OSError):
        return False


async def print_attachment(printer: 'BLEPrinter', att: dict, config: dict):
    """Print an image attachment, or a still frame for a video attachment."""
    filepath = att.get('filepath')
    att_type = att.get('type')
    label = att.get('filename') or att_type

    if not filepath:
        return

    if not is_readable(filepath):
        # The receipt still prints with an [Image]/[Video] line, so the message
        # itself is never lost -- only the picture is missing.
        logger.warning(f"  ⚠ No permission to read {att_type} ({label}); printed the text receipt only")
        logger.warning("     Grant Full Disk Access to print iMessage photos and videos.")
        return

    if att_type == 'image':
        logger.info(f"  Printing image: {label}")
        if await printer.print_image(filepath):
            logger.info("  ✓ Image printed!")
        else:
            logger.warning("  ⚠ Image print failed")

    elif att_type == 'video' and config.get('print_video_frames', True):
        logger.info(f"  Extracting frame from video: {label}")
        with video_poster_frame(filepath, att.get('mime_type', ''), att.get('filename', '')) as frame:
            if not frame:
                logger.warning("  ⚠ Could not extract a video frame")
                return
            if await printer.print_image(frame):
                logger.info("  ✓ Video frame printed!")
            else:
                logger.warning("  ⚠ Video frame print failed")


async def cmd_monitor():
    """Main monitoring loop."""
    print()
    print("=" * 50)
    print("  📱➡️🖨️  Text-to-Print")
    print("=" * 50)
    print()

    config = load_config()

    beeper = BeeperMonitor(config)
    if not beeper.enabled:
        print("❌ Could not reach Beeper Desktop -- nothing to monitor.")
        print("   Make sure Beeper Desktop is running and BEEPER_ACCESS_TOKEN in")
        print("   .env is current (see .env.example).")
        return

    printer = BLEPrinter(config)

    # Connect to printer
    print("\nConnecting to printer via BLE...")
    if not await printer.connect():
        print("❌ Could not connect to printer")
        print("   Run with --scan to find available devices")
        return

    print()
    print("Configuration:")
    print(f"  Poll interval: {config.get('poll_interval_seconds', 2)}s")
    print(f"  Networks: {', '.join(sorted(beeper.networks))}")
    print(f"  Filter contacts: {config.get('filter_contacts') or 'All'}")
    print(f"  Include sent: {config.get('include_sent_messages', False)}")
    print()
    print("-" * 50)
    logger.info("Monitoring for new messages... (Ctrl+C to stop)")

    try:
        while True:
            messages = beeper.fetch_new_messages()

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
                        await print_attachment(printer, att, config)
            
            if messages:
                beeper._save_state()

            await asyncio.sleep(config.get('poll_interval_seconds', 2))

    except KeyboardInterrupt:
        print("\n\nStopping...")
        beeper._save_state()
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
