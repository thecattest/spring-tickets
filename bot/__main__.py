"""
Allow running bot as a module: python3 -m bot
"""

import asyncio
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bot.main import setup

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        bot = loop.run_until_complete(setup())
        if bot:
            bot.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
