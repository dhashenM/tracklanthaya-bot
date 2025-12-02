import discord
from discord.ext import commands
from discord import app_commands
from utils.database import db
from utils.channel_manager import get_channel_manager
import config


class GameSelect(discord.ui.Select):
    """Dropdown for selecting a game"""

    def __init__(self, action: str, enabled_games: list):
        # Create options for each enabled game
        options = []
        for game_id in enabled_games:
            game_info = config.GAMES[game_id]
            options.append(
                discord.SelectOption(
                    label=game_info['name'],
                    value=game_id,
                    emoji=game_info['emoji'],
                    description=f"Team Size: {game_info['team_size']}v{game_info['team_size']}"
                )
            )

        super().__init__(
            placeholder=f"Select a game to {action}...",
            options=options,
            min_values=1,
            max_values=len(options)  # Allow multiple selections
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        # Handle in parent view
        await self.view.handle_selection(interaction, self.values)


class GameSelectView(discord.ui.View):
    """View with game selection dropdown"""

    def __init__(self, action: str, enabled_games: list, callback_func):
        super().__init__(timeout=60)
        self.action = action
        self.callback_func = callback_func
        self.add_item(GameSelect(action, enabled_games))

    async def handle_selection(self, interaction: discord.Interaction, selected_games: list):
        await self.callback_func(interaction, selected_games)
        self.stop()


class PlayerCommands(commands.Cog):
    """Commands for regular players/members"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="register", description="Register as a player")
    async def register(self, interaction: discord.Interaction):
        """Register a new player"""
        player = await db.get_player(interaction.user.id)

        if player:
            await interaction.response.send_message(
                "✅ You're already registered!",
                ephemeral=True
            )
            return

        await db.create_player(interaction.user.id, interaction.user.name)
        await interaction.response.send_message(
            "✅ Registration successful! Use `/setskill` to set your skill levels for each game.",
            ephemeral=True
        )

    @app_commands.command(name="setskill", description="Set your skill level for games (1-10)")
    async def setskill(self, interaction: discord.Interaction):
        """Set player skill level - shows dropdown to select games"""
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        enabled_games = await db.get_enabled_games()

        if not enabled_games:
            await interaction.response.send_message(
                "❌ No games are currently enabled!",
                ephemeral=True
            )
            return

        # Show game selection
        view = GameSelectView("set skill for", enabled_games, self.handle_setskill_selection)
        await interaction.response.send_message(
            "🎮 Select which game(s) you want to set your skill level for:",
            view=view,
            ephemeral=True
        )

    async def handle_setskill_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle skill level setting after game selection"""
        # Create modal for skill input
        modal = SkillModal(selected_games)
        await interaction.response.send_modal(modal)

    @app_commands.command(name="online", description="Join matchmaking queue")
    async def go_online(self, interaction: discord.Interaction):
        """Set player status to online for selected games"""
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        enabled_games = await db.get_enabled_games()

        if not enabled_games:
            await interaction.response.send_message(
                "❌ No games are currently enabled!",
                ephemeral=True
            )
            return

        # Check if player is in an active match
        if player.get('current_match_game'):
            game_info = config.GAMES[player['current_match_game']]
            await interaction.response.send_message(
                f"❌ You're currently in an active {game_info['name']} match!",
                ephemeral=True
            )
            return

        # Filter out games they're already online for
        available_games = [g for g in enabled_games if player.get('queue_status', {}).get(g) != 'online']

        if not available_games:
            await interaction.response.send_message(
                "⚠️ You're already online for all enabled games!",
                ephemeral=True
            )
            return

        # Show game selection
        view = GameSelectView("join queue for", available_games, self.handle_online_selection)
        await interaction.response.send_message(
            "🎮 Select which game(s) you want to queue for:",
            view=view,
            ephemeral=True
        )

    async def handle_online_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle going online after game selection"""
        await interaction.response.defer(ephemeral=True)

        player = await db.get_player(interaction.user.id)
        skill_levels = player.get('skill_levels', {})

        # Check if user needs to set skill for any selected games
        games_need_skill = []
        for game_id in selected_games:
            # If skill is still default (5) or not set, require them to set it
            if game_id not in skill_levels or skill_levels.get(game_id) == 5:
                games_need_skill.append(game_id)

        if games_need_skill:
            # User needs to set skill first
            game_names = [config.GAMES[g]['name'] for g in games_need_skill]
            await interaction.followup.send(
                f"⚠️ Please set your skill level first for:\n" +
                "\n".join([f"• {name}" for name in game_names]) +
                "\n\nUse `/setskill` to set your skill levels (1-10).",
                ephemeral=True
            )
            return

        queue_status = player.get('queue_status', {})

        # Update queue status for selected games
        for game_id in selected_games:
            queue_status[game_id] = 'online'

        await db.update_player(interaction.user.id, {'queue_status': queue_status})

        # Build response message
        game_names = [config.GAMES[g]['name'] for g in selected_games]
        await interaction.followup.send(
            f"✅ You are now online for:\n" + "\n".join([f"• {name}" for name in game_names]),
            ephemeral=True
        )

        # Update queue channels and check matchmaking for each game
        cm = get_channel_manager(self.bot)
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')

        for game_id in selected_games:
            await cm.update_queue(interaction.guild, game_id)
            if matchmaking_cog:
                await matchmaking_cog.check_and_create_match(interaction.guild, game_id)

    @app_commands.command(name="offline", description="Leave matchmaking queue")
    async def go_offline(self, interaction: discord.Interaction):
        """Set player status to offline for selected games"""
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        # Get games they're currently online for
        queue_status = player.get('queue_status', {})
        online_games = [g for g, status in queue_status.items() if status == 'online']

        if not online_games:
            await interaction.response.send_message(
                "⚠️ You're not online for any games!",
                ephemeral=True
            )
            return

        # Show game selection
        view = GameSelectView("leave queue for", online_games, self.handle_offline_selection)
        await interaction.response.send_message(
            "🎮 Select which game(s) you want to leave the queue for:",
            view=view,
            ephemeral=True
        )

    async def handle_offline_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle going offline after game selection"""
        player = await db.get_player(interaction.user.id)
        queue_status = player.get('queue_status', {})

        # Update queue status for selected games
        for game_id in selected_games:
            queue_status[game_id] = 'offline'

        await db.update_player(interaction.user.id, {'queue_status': queue_status})

        # Build response message
        game_names = [config.GAMES[g]['name'] for g in selected_games]
        await interaction.response.send_message(
            f"✅ You are now offline for:\n" + "\n".join([f"• {name}" for name in game_names]),
            ephemeral=True
        )

        # Update queue channels
        cm = get_channel_manager(self.bot)
        for game_id in selected_games:
            await cm.update_queue(interaction.guild, game_id)

    @app_commands.command(name="profile", description="View player profile and stats")
    async def profile(self, interaction: discord.Interaction, member: discord.Member = None):
        """View player profile"""
        target_user = member if member else interaction.user
        player = await db.get_player(target_user.id)

        if not player:
            await interaction.response.send_message(
                f"❌ {'That user is' if member else 'You are'} not registered!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"👤 {player['username']}'s Profile",
            color=discord.Color.blue()
        )

        # Calculate total points and matches
        total_points = 0
        total_matches = 0

        for game_id in config.GAMES.keys():
            stats = await db.get_game_stats(target_user.id, game_id)
            total_points += stats.get('points', 0)
            total_matches += stats.get('matches_played', 0)

        # Show totals at top
        embed.add_field(
            name="📊 Overall Stats",
            value=f"**Total Points:** {total_points:.2f}\n**Total Matches:** {total_matches}",
            inline=False
        )

        # Show current match status
        if player.get('current_match_game'):
            game_info = config.GAMES[player['current_match_game']]
            embed.add_field(
                name="🎮 Current Match",
                value=f"{game_info['emoji']} {game_info['name']}",
                inline=False
            )

        # Show queue status for enabled games only
        enabled_games = await db.get_enabled_games()
        queue_status = player.get('queue_status', {})
        online_games = [config.GAMES[g]['name'] for g in enabled_games if queue_status.get(g) == 'online']
        if online_games:
            embed.add_field(
                name="📋 Currently Queued For",
                value="\n".join([f"• {name}" for name in online_games]),
                inline=False
            )

        # Show stats for ALL games
        embed.add_field(name="🎮 Game Statistics", value="", inline=False)

        for game_id, game_info in config.GAMES.items():
            stats = await db.get_game_stats(target_user.id, game_id)
            skill_levels = player.get('skill_levels', {})
            skill = skill_levels.get(game_id, "Not Set")

            points = stats.get('points', 0)
            matches = stats.get('matches_played', 0)

            # Only show if player has played or set skill
            if points > 0 or matches > 0 or skill != "Not Set":
                skill_text = f"{skill}/10" if skill != "Not Set" else "❌ Not Set"

                stats_text = (
                    f"Skill: {skill_text}\n"
                    f"Points: {points:.2f} | Matches: {matches}"
                )

                embed.add_field(
                    name=f"{game_info['emoji']} {game_info['short_name']}",
                    value=stats_text,
                    inline=True
                )

        # Show as ephemeral if viewing own profile, public if viewing others
        is_self = (member is None or member.id == interaction.user.id)
        await interaction.response.send_message(embed=embed, ephemeral=is_self)

    @app_commands.command(name="mystats", description="Quick view of your current queue status")
    async def mystats(self, interaction: discord.Interaction):
        """Show quick status of queues and current match"""
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📊 Your Quick Stats",
            color=discord.Color.blue()
        )

        # Current match
        if player.get('current_match_game'):
            game_info = config.GAMES[player['current_match_game']]
            embed.add_field(
                name="🎮 Currently Playing",
                value=f"{game_info['emoji']} {game_info['name']}",
                inline=False
            )
        else:
            embed.add_field(name="🎮 Currently Playing", value="Not in a match", inline=False)

        # Queue status
        queue_status = player.get('queue_status', {})
        online_games = []
        offline_games = []

        enabled_games = await db.get_enabled_games()
        for game_id in enabled_games:
            game_info = config.GAMES[game_id]
            if queue_status.get(game_id) == 'online':
                online_games.append(f"{game_info['emoji']} {game_info['short_name']}")
            else:
                offline_games.append(f"{game_info['emoji']} {game_info['short_name']}")

        if online_games:
            embed.add_field(
                name="🟢 Online For",
                value="\n".join(online_games),
                inline=True
            )

        if offline_games:
            embed.add_field(
                name="⚪ Offline For",
                value="\n".join(offline_games),
                inline=True
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


class SkillModal(discord.ui.Modal):
    """Modal for entering skill levels"""

    def __init__(self, game_ids: list):
        super().__init__(title="Set Your Skill Levels")
        self.game_ids = game_ids

        # Add input for each game (max 5 per modal)
        for game_id in game_ids[:5]:  # Discord modal limit
            game_info = config.GAMES[game_id]
            self.add_item(
                discord.ui.TextInput(
                    label=f"{game_info['short_name']} Skill (1-10)",
                    placeholder="Enter your skill level from 1-10",
                    min_length=1,
                    max_length=2,
                    custom_id=game_id
                )
            )

    async def on_submit(self, interaction: discord.Interaction):
        player = await db.get_player(interaction.user.id)
        skill_levels = player.get('skill_levels', {})

        updates = []
        for item in self.children:
            try:
                skill = int(item.value)
                if 1 <= skill <= 10:
                    skill_levels[item.custom_id] = skill
                    game_info = config.GAMES[item.custom_id]
                    updates.append(f"{game_info['emoji']} {game_info['short_name']}: {skill}/10")
                else:
                    await interaction.response.send_message(
                        f"❌ Skill level must be between 1 and 10!",
                        ephemeral=True
                    )
                    return
            except ValueError:
                await interaction.response.send_message(
                    f"❌ Please enter valid numbers!",
                    ephemeral=True
                )
                return

        await db.update_player(interaction.user.id, {'skill_levels': skill_levels})

        await interaction.response.send_message(
            "✅ Skill levels updated:\n" + "\n".join(updates),
            ephemeral=True
        )


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(PlayerCommands(bot))
    print("✅ Player commands loaded")
