import discord
from discord.ext import commands
import config
from utils.database import db
import asyncio

# Bot intents (permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)


@bot.event
async def on_ready():
    """Called when bot is ready"""
    print(f'✅ Bot is ready! Logged in as {bot.user.name}')
    print(f'📊 Connected to {len(bot.guilds)} server(s)')

    # Connect to database
    await db.connect()

    # Set default system settings
    matchmaking_enabled = await db.get_system_setting('matchmaking_enabled')
    if matchmaking_enabled is None:
        await db.set_system_setting('matchmaking_enabled', False)

    # Load cogs (command modules)
    await bot.load_extension('cogs.player')
    await bot.load_extension('cogs.matchmaking')
    await bot.load_extension('cogs.admin')

    print('✅ All cogs loaded')


@bot.event
async def on_command_error(ctx, error):
    """Handle command errors"""
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("❌ Command not found. Use `!help` to see available commands.")
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission to use this command.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing required argument: {error.param.name}")
    else:
        print(f"Error: {error}")
        await ctx.send(f"❌ An error occurred: {str(error)}")


@bot.event
async def on_close():
    """Called when bot shuts down"""
    await db.close()


# Run the bot
if __name__ == "__main__":
    try:
        bot.run(config.DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")