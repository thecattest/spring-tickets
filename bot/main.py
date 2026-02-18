"""
VK Bot entry point.

Initializes VKBottle, configures handlers, and starts polling.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path if running as script
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

from vkbottle.bot import Bot
from vkbottle import BaseStateGroup

from bot import config
from bot.fsm.storage import RedisStorage
from bot.handlers import commands, reservation, menu, deletion, payment, reserve


# Setup logging
config.setup_logging()
logger = logging.getLogger(__name__)


async def setup():
    """
    Async initialization tasks.
    Returns configured bot instance.
    """
    # Validate configuration
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return None

    logger.info("Starting VK Bot...")
    logger.info(f"Group ID: {config.VK_GROUP_ID}")
    logger.info(f"Redis: {config.REDIS_HOST}:{config.REDIS_PORT}/{config.REDIS_DB}")
    logger.info(f"Database: {config.DATABASE_URL}")

    # Initialize Redis storage (FSM states + context via StatePeer)
    try:
        redis_storage = RedisStorage(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD if config.REDIS_PASSWORD else None,
        )
        await redis_storage.connect()
        logger.info("Redis FSM storage established")
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")
        return None

    # Initialize VKBottle bot with Redis state dispenser
    bot = Bot(token=config.VK_BOT_TOKEN, state_dispenser=redis_storage)

    # Register handlers
    logger.info("Registering handlers...")
    commands.register_handlers(bot)
    reservation.register_handlers(bot)
    menu.register_handlers(bot)
    deletion.register_handlers(bot)
    payment.register_handlers(bot)
    reserve.register_handlers(bot)

    # Initialize database
    from database import init_db
    try:
        init_db()
        logger.info("Database initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        return None

    # Load hall layout
    from bot.utils.layout import load_layout
    try:
        load_layout()
        logger.info("Hall layout loaded")
    except Exception as e:
        logger.error(f"Failed to load hall layout: {e}")
        return None

    logger.info("Bot is ready! Starting polling...")
    return bot


if __name__ == "__main__":
    # Run async setup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        bot = loop.run_until_complete(setup())
        if bot:
            # Now run VKBottle's synchronous run_forever()
            bot.run_forever()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        loop.close()
