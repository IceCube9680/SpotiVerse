import os
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import logging
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Import config
try:
    from config import Config
except ImportError:
    logger.error("❌ Could not import config.py. Make sure it exists.")
    sys.exit(1)

# Import handlers
try:
    from handlers.commands import CommandHandler
    from handlers.search import SearchHandler
    from handlers.downloads import DownloadHandler
    from utils.logger import BotLogger
except ImportError as e:
    logger.error(f"❌ Could not import required modules: {e}")
    logger.error("Make sure all handler files exist in the handlers directory")
    sys.exit(1)
class SpotiVerseBot:
    def __init__(self):
        # Validate required credentials
        self.validate_credentials()
            
        self.bot = Client(
            "spotiverse_bot",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            bot_token=Config.BOT_TOKEN
        )
        
        # Initialize utilities
        # Initialize utilities
        self.logger = BotLogger(self.bot)
        self.search_handler = SearchHandler()
        self.download_handler = DownloadHandler(self.bot, self.logger, self.search_handler)
        self.command_handler = CommandHandler(self.bot, self.logger, self.search_handler, self.download_handler)  # Add download_handler
        
        # Set up handlers
        self.setup_handlers()
    
    def validate_credentials(self):
        """Validate that all required credentials are set"""
        errors = []
        
        if not Config.API_ID or Config.API_ID == 0:
            errors.append("API_ID is required. Get it from https://my.telegram.org")
        
        if not Config.API_HASH:
            errors.append("API_HASH is required. Get it from https://my.telegram.org")
        
        if not Config.BOT_TOKEN:
            errors.append("BOT_TOKEN is required. Get it from @BotFather")
        
        if errors:
            error_msg = "❌ Configuration errors:\n" + "\n".join(f"• {error}" for error in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("bot.log", encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

    def setup_handlers(self):
        """Set up message and callback handlers"""
        
        # Command handlers
        @self.bot.on_message(filters.command("start"))
        async def start_handler(client, message: Message):
            await self.command_handler.start_command(client, message)
        
        @self.bot.on_message(filters.command("help"))
        async def help_handler(client, message: Message):
            await self.command_handler.help_command(client, message)
        
        @self.bot.on_message(filters.command("search"))
        async def search_handler(client, message: Message):
            await self.command_handler.search_command(client, message)
        
        @self.bot.on_message(filters.command("download"))
        async def download_handler(client, message: Message):
            await self.command_handler.download_command(client, message)
        
        @self.bot.on_message(filters.command("userinfo"))
        async def userinfo_handler(client, message: Message):
            await self.command_handler.userinfo_command(client, message)
        
        @self.bot.on_message(filters.command("premium"))
        async def premium_handler(client, message: Message):
            await self.command_handler.premium_command(client, message)
        
        @self.bot.on_message(filters.command("settings"))
        async def settings_handler(client, message: Message):
            await self.command_handler.settings_command(client, message)
        
        # Admin commands
        @self.bot.on_message(filters.command("addpremium"))
        async def add_premium_handler(client, message: Message):
            await self.command_handler.add_premium_command(client, message)
        
        @self.bot.on_message(filters.command("removepremium"))
        async def remove_premium_handler(client, message: Message):
            await self.command_handler.remove_premium_command(client, message)
        
        @self.bot.on_message(filters.command("stats"))
        async def stats_handler(client, message: Message):
            await self.command_handler.stats_command(client, message)
        
        @self.bot.on_message(filters.command("broadcast"))
        async def broadcast_handler(client, message: Message):
            await self.command_handler.broadcast_command(client, message)
        
        # Callback query handlers with error handling
        @self.bot.on_callback_query()
        async def callback_query_handler(client, callback_query: CallbackQuery):
            try:
                data = callback_query.data
                
                if data.startswith("download_"):
                    await self.download_handler.handle_download_callback(client, callback_query)
                
                elif data.startswith("setting_"):
                    await self.command_handler.handle_settings_callback(client, callback_query)
                
                elif data.startswith("broadcast_"):
                    await self.command_handler.handle_broadcast_confirmation(client, callback_query)
                
                elif data == "premium_info":
                    await callback_query.message.edit_text(
                        "💎 **Premium Features**\n\n"
                        "• Unlimited downloads\n"
                        "• High quality FLAC format\n"
                        "• Advanced search options\n"
                        "• Album downloads\n"
                        "• No ads\n\n"
                        "Contact @icecube9680 for premium access!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
                        ])
                    )
                    # Answer the callback query
                    try:
                        await callback_query.answer()
                    except Exception as e:
                        logger.warning(f"Could not answer callback query: {e}")
                
                elif data == "main_menu":
                    await callback_query.message.delete()
                    await self.command_handler.start_command(client, callback_query.message)
                    # Answer the callback query
                    try:
                        await callback_query.answer()
                    except Exception as e:
                        logger.warning(f"Could not answer callback query: {e}")
            
            except Exception as e:
                logger.error(f"Error in callback query handler: {e}")
                # Try to answer the callback query to prevent future errors
                try:
                    await callback_query.answer("An error occurred")
                except Exception as inner_e:
                    logger.warning(f"Could not answer callback query after error: {inner_e}")
    
    async def start(self):
        """Start the bot with proper error handling"""
        try:
            # Create necessary directories
            os.makedirs("temp/", exist_ok=True)
            os.makedirs("data/thumbnails/", exist_ok=True)
            
            # Start the bot
            logger.info("Starting SpotiVerse Bot...")
            await self.bot.start()
            
            # Get bot info to confirm it's working
            me = await self.bot.get_me()
            logger.info(f"Bot started successfully! Username: @{me.username}")
            
            # Send startup message to owner if configured
            # Send startup message to log channel instead of owner
            if Config.LOG_CHANNEL and Config.LOG_CHANNEL != 0:
                try:
                    await self.bot.send_message(
                        Config.LOG_CHANNEL,
                        "✅ Bot started successfully!\n\n"
                        f"Username: @{me.username}\n"
                        f"ID: {me.id}"
                    )
                except Exception as e:
                    logger.warning(f"Could not send startup message to log channel: {e}")

            
            # Keep the bot running
            logger.info("Bot is now running. Press Ctrl+C to stop.")
            await asyncio.Event().wait()
            
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            raise
        finally:
            # Ensure proper cleanup
            if self.bot.is_connected:
                await self.bot.stop()
                logger.info("Bot stopped.")

async def main():
    """Main function with error handling"""
    try:
        bot = SpotiVerseBot()
        await bot.start()
    except ValueError as e:
        print(f"❌ Configuration error: {e}")
        print("💡 Please check your .env file and make sure all required credentials are set.")
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        print("💡 Check your internet connection and try again.")

if __name__ == "__main__":
    # Check if .env file exists
    if not os.path.exists(".env"):
        print("❌ .env file not found!")
        print("💡 Please create a .env file with your credentials.")
        print("📋 Use .env.example as a template.")
        sys.exit(1)
    
    # Run the bot
    asyncio.run(main())