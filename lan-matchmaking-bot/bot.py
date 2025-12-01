import discord
from discord.ext import commands
import config
from utils.database import db
from utils.channel_manager import get_channel_manager
import asyncio
from utils.sheets_manager import get_sheets_manager

# Bot intents (permissions)
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.voice_states = True

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)


@bot.event
async def on_ready():
    """Called when bot is ready"""
    print(f'✅ Bot is ready! Logged in as {bot.user.name}')
    print(f'📊 Connected to {len(bot.guilds)} server(s)')

    # Connect to database
    await db.connect()

    # Initialize enabled games list if not exists
    enabled_games = await db.get_enabled_games()
    if enabled_games is None:
        await db.set_enabled_games([])
        print("📝 Initialized empty enabled games list")

    # Load cogs (command modules)
    try:
        await bot.load_extension('cogs.player')
        await bot.load_extension('cogs.matchmaking')
        await bot.load_extension('cogs.admin')
        print('✅ All cogs loaded')
    except Exception as e:
        print(f"❌ Error loading cogs: {e}")
        return

    # Sync commands ONCE after all cogs are loaded
    try:
        synced = await bot.tree.sync()
        print(f'✅ Synced {len(synced)} slash commands')
    except Exception as e:
        print(f'❌ Failed to sync commands: {e}')

    # Setup channels for enabled games only
    try:
        for guild in bot.guilds:
            cm = get_channel_manager(bot)
            enabled_games = await db.get_enabled_games()

            if enabled_games:
                print(f"🎮 Setting up channels for enabled games: {', '.join(enabled_games)}")
                for game_id in enabled_games:
                    await cm.setup_game_channels(guild, game_id)
            else:
                print("ℹ️ No games enabled yet. Use /enablegames to start!")
    except Exception as e:
        print(f"⚠️ Error setting up channels: {e}")

    # Start Google Sheets sync loop
    if config.GOOGLE_SHEETS_ENABLED:
        sheets_mgr = get_sheets_manager(bot)
        asyncio.create_task(sheets_mgr.start_sync_loop())


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

    # Stop sheets sync
    if config.GOOGLE_SHEETS_ENABLED:
        sheets_mgr = get_sheets_manager(bot)
        sheets_mgr.stop_sync_loop()


@bot.command(name='sync')
@commands.is_owner()
async def sync(ctx):
    """Manually sync slash commands (bot owner only)"""
    try:
        # Clear all commands first
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync()

        # Sync to specific guild for instant update
        guild = discord.Object(id=config.GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)

        await ctx.send(f"✅ Cleared and synced {len(synced)} command(s) to your server")
        print(f"Synced {len(synced)} commands to guild {config.GUILD_ID}")
    except Exception as e:
        await ctx.send(f"❌ Failed to sync: {e}")
        print(f"Sync error: {e}")


@bot.command(name='listcmds')
@commands.is_owner()
async def list_commands(ctx):
    """List all registered slash commands"""
    commands_list = bot.tree.get_commands()
    if not commands_list:
        await ctx.send("❌ No commands registered!")
        return

    # Group commands by category
    player_cmds = []
    admin_cmds = []

    for cmd in commands_list:
        if '[ADMIN]' in cmd.description:
            admin_cmds.append(f"/{cmd.name}")
        else:
            player_cmds.append(f"/{cmd.name}")

    embed = discord.Embed(
        title=f"📋 Registered Commands ({len(commands_list)})",
        color=discord.Color.blue()
    )

    if player_cmds:
        embed.add_field(
            name="👥 Player Commands",
            value=", ".join(player_cmds),
            inline=False
        )

    if admin_cmds:
        embed.add_field(
            name="🔧 Admin Commands",
            value=", ".join(admin_cmds),
            inline=False
        )

    await ctx.send(embed=embed)


@bot.command(name='status')
@commands.is_owner()
async def bot_status(ctx):
    """Check bot status and database connection"""
    embed = discord.Embed(
        title="🤖 Bot Status",
        color=discord.Color.green()
    )

    # Bot info
    embed.add_field(
        name="Bot Info",
        value=f"**Name:** {bot.user.name}\n**Servers:** {len(bot.guilds)}\n**Latency:** {round(bot.latency * 1000)}ms",
        inline=False
    )

    # Database info
    try:
        player_count = len(await db.get_all_players())
        enabled_games = await db.get_enabled_games()

        embed.add_field(
            name="Database",
            value=f"**Status:** ✅ Connected\n**Players:** {player_count}\n**Enabled Games:** {len(enabled_games)}",
            inline=False
        )
    except Exception as e:
        embed.add_field(
            name="Database",
            value=f"**Status:** ❌ Error\n**Error:** {str(e)}",
            inline=False
        )

    # Active games
    try:
        enabled_games = await db.get_enabled_games()
        if enabled_games:
            game_names = [config.GAMES[g]['short_name'] for g in enabled_games]
            embed.add_field(
                name="Active Games",
                value="\n".join([f"• {name}" for name in game_names]),
                inline=False
            )
        else:
            embed.add_field(
                name="Active Games",
                value="None - use /enablegames",
                inline=False
            )
    except:
        pass

    await ctx.send(embed=embed)


@bot.command(name='setupgame')
@commands.is_owner()
async def setup_game(ctx, game_id: str):
    """Manually setup channels for a specific game"""
    if game_id not in config.GAMES:
        await ctx.send(f"❌ Invalid game ID. Valid options: {', '.join(config.GAMES.keys())}")
        return

    try:
        cm = get_channel_manager(bot)
        await cm.setup_game_channels(ctx.guild, game_id)
        game_info = config.GAMES[game_id]
        await ctx.send(f"✅ Set up channels for {game_info['name']}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@bot.command(name='resetgame')
@commands.is_owner()
async def reset_game(ctx, game_id: str):
    """Reset all data for a specific game"""
    if game_id not in config.GAMES:
        await ctx.send(f"❌ Invalid game ID. Valid options: {', '.join(config.GAMES.keys())}")
        return

    # Confirm
    await ctx.send(f"⚠️ This will reset ALL data for {config.GAMES[game_id]['name']}. Type 'CONFIRM' to proceed.")

    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content == 'CONFIRM'

    try:
        await bot.wait_for('message', check=check, timeout=30.0)
    except asyncio.TimeoutError:
        await ctx.send("❌ Cancelled - timed out")
        return

    try:
        # Delete all matches for this game
        await db.db.matches.delete_many({'game_id': game_id})

        # Reset all player stats for this game
        await db.db.game_stats.delete_many({'game_id': game_id})

        # Remove from enabled games
        enabled_games = await db.get_enabled_games()
        if game_id in enabled_games:
            enabled_games.remove(game_id)
            await db.set_enabled_games(enabled_games)

        game_info = config.GAMES[game_id]
        await ctx.send(f"✅ Reset all data for {game_info['name']}")
    except Exception as e:
        await ctx.send(f"❌ Error: {e}")


@bot.command(name='help')
async def help_command(ctx):
    """Show help information"""
    embed = discord.Embed(
        title="🎮 LAN Matchmaking Bot - Help",
        description="Multi-game tournament management system",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="👥 Player Commands (use /)",
        value=(
            "`/register` - Register as a player\n"
            "`/setskill` - Set your skill level for games\n"
            "`/online` - Join matchmaking queue(s)\n"
            "`/offline` - Leave matchmaking queue(s)\n"
            "`/profile` - View your profile and stats\n"
            "`/mystats` - Quick status check\n"
            "`/submitpoints` - Submit match points"
        ),
        inline=False
    )

    embed.add_field(
        name="🔧 Admin Commands (use /)",
        value=(
            "`/enablegames` - Enable up to 2 games\n"
            "`/disablegames` - Disable games\n"
            "`/activegames` - View enabled games\n"
            "`/startmatch` - Start a pending match\n"
            "`/endmatch` - End an active match\n"
            "`/cancelmatch` - Cancel a pending match\n"
            "`/verifypoints` - Verify and finalize points\n"
            "`/matchstatus` - Detailed status overview\n"
            "`/setpoints` - Set player points\n"
            "`/resetplayer` - Reset player stats\n"
            "`/listplayers` - List all players\n"
            "`/forceoffline` - Force player offline"
        ),
        inline=False
    )

    embed.add_field(
        name="🎮 Available Games",
        value="\n".join([f"{info['emoji']} {info['name']}" for info in config.GAMES.values()]),
        inline=False
    )

    embed.set_footer(text="Made for LAN parties • Max 2 games active simultaneously")

    await ctx.send(embed=embed)


@bot.command(name='syncsheets')
@commands.is_owner()
async def sync_sheets(ctx):
    """Manually sync Google Sheets data"""
    if not config.GOOGLE_SHEETS_ENABLED:
        await ctx.send("❌ Google Sheets integration is disabled")
        return

    await ctx.send("🔄 Syncing all game stats from master sheet...")

    sheets_mgr = get_sheets_manager(bot)
    success = await sheets_mgr.sync_all_stats(ctx.guild)

    if success:
        await ctx.send("✅ All game stats synced successfully!")
    else:
        await ctx.send("⚠️ No changes detected or sync failed")

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(config.DISCORD_TOKEN)
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")