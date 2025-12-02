import discord
from discord.ext import commands
from discord import app_commands
from utils.database import db
from utils.channel_manager import get_channel_manager
import config
from bson import ObjectId
from datetime import datetime, timedelta


def is_admin():
    """Check if user has admin role"""

    async def predicate(interaction: discord.Interaction):
        admin_role = discord.utils.get(interaction.user.roles, name=config.ADMIN_ROLE_NAME)
        return admin_role is not None

    return app_commands.check(predicate)


class GameSelectAdmin(discord.ui.Select):
    """Dropdown for admin to select games"""

    def __init__(self, action: str, available_games: list, max_selections: int = None):
        # Create options for games
        options = []
        for game_id in available_games:
            game_info = config.GAMES[game_id]
            options.append(
                discord.SelectOption(
                    label=game_info['name'],
                    value=game_id,
                    emoji=game_info['emoji'],
                    description=f"Team Size: {game_info['team_size']}v{game_info['team_size']}"
                )
            )

        max_vals = max_selections if max_selections else len(options)

        super().__init__(
            placeholder=f"Select game(s) to {action}...",
            options=options,
            min_values=1,
            max_values=min(max_vals, len(options))
        )
        self.action = action

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_selection(interaction, self.values)


class GameSelectViewAdmin(discord.ui.View):
    """View with game selection dropdown for admins"""

    def __init__(self, action: str, available_games: list, callback_func, max_selections: int = None):
        super().__init__(timeout=60)
        self.action = action
        self.callback_func = callback_func
        self.add_item(GameSelectAdmin(action, available_games, max_selections))

    async def handle_selection(self, interaction: discord.Interaction, selected_games: list):
        await self.callback_func(interaction, selected_games)
        self.stop()


class AdminCommands(commands.Cog):
    """Commands for administrators"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="enablegames", description="[ADMIN] Enable matchmaking for specific games")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def enable_games(self, interaction: discord.Interaction):
        """Enable matchmaking for games"""
        enabled_games = await db.get_enabled_games()

        # Get games that aren't already enabled
        available_games = [g for g in config.GAMES.keys() if g not in enabled_games]

        if not available_games:
            await interaction.response.send_message(
                "⚠️ All games are already enabled!",
                ephemeral=True
            )
            return

        # Show game selection (max 2 at a time as per requirements)
        view = GameSelectViewAdmin(
            "enable",
            available_games,
            self.handle_enable_games,
            max_selections=2
        )
        await interaction.response.send_message(
            "🎮 Select up to 2 games to enable:\n"
            "*Note: Only 2 games can run simultaneously*",
            view=view,
            ephemeral=True
        )

    async def handle_enable_games(self, interaction: discord.Interaction, selected_games: list):
        """Handle enabling games after selection"""
        # Defer immediately since channel setup takes time
        await interaction.response.defer()

        enabled_games = await db.get_enabled_games()

        # Check limit
        if len(enabled_games) + len(selected_games) > 2:
            await interaction.followup.send(
                "❌ Cannot enable more than 2 games at once!\n"
                f"Currently enabled: {len(enabled_games)}\n"
                f"You're trying to add: {len(selected_games)}",
                ephemeral=True
            )
            return

        # Enable the games
        enabled_games.extend(selected_games)
        await db.set_enabled_games(enabled_games)

        # Setup channels for newly enabled games
        cm = get_channel_manager(self.bot)
        for game_id in selected_games:
            await cm.setup_game_channels(interaction.guild, game_id)

        game_names = [config.GAMES[g]['name'] for g in selected_games]
        await interaction.followup.send(
            "✅ **Matchmaking enabled for:**\n" + "\n".join([f"• {name}" for name in game_names])
        )

    @app_commands.command(name="disablegames", description="[ADMIN] Disable matchmaking for specific games")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def disable_games(self, interaction: discord.Interaction):
        """Disable matchmaking for games"""
        enabled_games = await db.get_enabled_games()

        if not enabled_games:
            await interaction.response.send_message(
                "⚠️ No games are currently enabled!",
                ephemeral=True
            )
            return

        # Show game selection
        view = GameSelectViewAdmin("disable", enabled_games, self.handle_disable_games)
        await interaction.response.send_message(
            "🎮 Select game(s) to disable:",
            view=view,
            ephemeral=True
        )

    async def handle_disable_games(self, interaction: discord.Interaction, selected_games: list):
        """Handle disabling games after selection"""
        enabled_games = await db.get_enabled_games()

        # Check if any games have active matches
        for game_id in selected_games:
            active_match = await db.get_active_match(game_id)
            if active_match:
                game_info = config.GAMES[game_id]
                await interaction.response.send_message(
                    f"❌ Cannot disable **{game_info['name']}** - there's an active match!",
                    ephemeral=True
                )
                return

        # Disable the games
        enabled_games = [g for g in enabled_games if g not in selected_games]
        await db.set_enabled_games(enabled_games)

        # Set all players offline for these games
        players = await db.get_all_players()
        for player in players:
            queue_status = player.get('queue_status', {})
            for game_id in selected_games:
                if game_id in queue_status:
                    queue_status[game_id] = 'offline'
            await db.update_player(player['user_id'], {'queue_status': queue_status})

        game_names = [config.GAMES[g]['name'] for g in selected_games]
        await interaction.response.send_message(
            "✅ **Matchmaking disabled for:**\n" + "\n".join([f"• {name}" for name in game_names])
        )

    @app_commands.command(name="activegames", description="[ADMIN] View currently enabled games")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def active_games(self, interaction: discord.Interaction):
        """View active games"""
        enabled_games = await db.get_enabled_games()

        if not enabled_games:
            await interaction.response.send_message(
                "⚠️ No games are currently enabled!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🎮 Active Games",
            description=f"Currently running: {len(enabled_games)}/2 games",
            color=discord.Color.green()
        )

        for game_id in enabled_games:
            game_info = config.GAMES[game_id]

            # Get queue info
            online_players = await db.get_online_players(game_id)
            active_match = await db.get_active_match(game_id)
            pending_match = await db.get_pending_match(game_id)

            status_parts = [
                f"Queue: {len(online_players)} players",
                f"Active: {'Yes' if active_match else 'No'}",
                f"Pending: {'Yes' if pending_match else 'No'}"
            ]

            embed.add_field(
                name=f"{game_info['emoji']} {game_info['name']}",
                value=" | ".join(status_parts),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="startmatch", description="[ADMIN] Start a pending match")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def start_match(self, interaction: discord.Interaction):
        """Start pending match - shows game selection if multiple pending"""
        await interaction.response.defer()

        enabled_games = await db.get_enabled_games()

        # Find all pending matches
        pending_matches = []
        for game_id in enabled_games:
            match = await db.get_pending_match(game_id)
            if match:
                pending_matches.append((game_id, match))

        if not pending_matches:
            await interaction.followup.send(
                "❌ No pending matches to start!",
                ephemeral=True
            )
            return

        if len(pending_matches) == 1:
            # Only one pending match, start it directly
            game_id, match = pending_matches[0]
            await self.start_specific_match(interaction, game_id, match)
        else:
            # Multiple pending matches, let admin choose
            games_with_pending = [g for g, m in pending_matches]
            view = GameSelectViewAdmin(
                "start match for",
                games_with_pending,
                self.handle_start_match_selection,
                max_selections=1
            )
            await interaction.followup.send(
                "🎮 Multiple games have pending matches. Select which one to start:",
                view=view,
                ephemeral=True
            )

    async def handle_start_match_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle starting match after game selection"""
        game_id = selected_games[0]
        match = await db.get_pending_match(game_id)

        if not match:
            await interaction.response.send_message(
                "❌ No pending match found!",
                ephemeral=True
            )
            return

        await self.start_specific_match(interaction, game_id, match)

    async def start_specific_match(self, interaction: discord.Interaction, game_id: str, match: dict):
        """Start a specific match"""
        game_info = config.GAMES[game_id]

        # Update match status
        await db.update_match(
            match['_id'],
            {
                'status': 'active',
                'started_at': discord.utils.utcnow()
            }
        )

        # Set all players' current_match_game
        all_players = match['team1'] + match['team2']
        for player in all_players:
            await db.update_player(player['user_id'], {'current_match_game': game_id})

        # Create channels
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.create_match_channels(interaction.guild, game_id, match)

        # Notify players
        team1_names = ", ".join([p['username'] for p in match['team1']])
        team2_names = ", ".join([p['username'] for p in match['team2']])

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['name']} - Match Started!",
            description="The match has begun! Good luck!",
            color=discord.Color.green()
        )
        embed.add_field(name="🔴 Team 1", value=team1_names, inline=False)
        embed.add_field(name="🔵 Team 2", value=team2_names, inline=False)

        # Send response (either followup or response depending on context)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

        # Notify players via DM
        for player in all_players:
            member = interaction.guild.get_member(player['user_id'])
            if member:
                try:
                    await member.send(embed=embed)
                except:
                    pass

        # Update channels
        cm = get_channel_manager(self.bot)
        await cm.update_upcoming_matches(interaction.guild, game_id)

        # Check queues for all enabled games (not just this one)
        if matchmaking_cog:
            enabled_games = await db.get_enabled_games()
            for enabled_game_id in enabled_games:
                await cm.update_queue(interaction.guild, enabled_game_id)
                await matchmaking_cog.check_and_create_match(interaction.guild, enabled_game_id)

    @app_commands.command(name="endmatch", description="[ADMIN] End an active match")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def end_match(self, interaction: discord.Interaction):
        """End active match - shows game selection if multiple active"""
        await interaction.response.defer()

        enabled_games = await db.get_enabled_games()

        # Find all active matches
        active_matches = []
        for game_id in enabled_games:
            match = await db.get_active_match(game_id)
            if match:
                active_matches.append((game_id, match))

        if not active_matches:
            await interaction.followup.send(
                "❌ No active matches to end!",
                ephemeral=True
            )
            return

        if len(active_matches) == 1:
            # Only one active match, end it directly
            game_id, match = active_matches[0]
            await self.end_specific_match(interaction, game_id, match)
        else:
            # Multiple active matches, let admin choose
            games_with_active = [g for g, m in active_matches]
            view = GameSelectViewAdmin(
                "end match for",
                games_with_active,
                self.handle_end_match_selection,
                max_selections=1
            )
            await interaction.followup.send(
                "🎮 Multiple games have active matches. Select which one to end:",
                view=view,
                ephemeral=True
            )

    async def handle_end_match_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle ending match after game selection"""
        await interaction.response.defer()

        game_id = selected_games[0]
        match = await db.get_active_match(game_id)

        if not match:
            await interaction.followup.send(
                "❌ No active match found!",
                ephemeral=True
            )
            return

        await self.end_specific_match(interaction, game_id, match)

    async def end_specific_match(self, interaction: discord.Interaction, game_id: str, match: dict):
        """End a specific match directly (no points verification needed)"""
        game_info = config.GAMES[game_id]

        # Update match status to completed immediately
        await db.update_match(
            match['_id'],
            {
                'status': 'completed',
                'ended_at': discord.utils.utcnow()
            }
        )

        # Free up all players from this match
        all_players = match['team1'] + match['team2']
        for player in all_players:
            # Set player as offline (not in queue)
            player_data = await db.get_player(player['user_id'])
            queue_status = player_data.get('queue_status', {})

            # Set this game to offline
            queue_status[game_id] = 'offline'

            await db.update_player(player['user_id'], {
                'current_match_game': None,
                'queue_status': queue_status
            })

            # Update match count in stats
            stats = await db.get_game_stats(player['user_id'], game_id)
            await db.update_game_stats(player['user_id'], game_id, {
                'matches_played': stats.get('matches_played', 0) + 1
            })

        # Delete match channels
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.delete_match_channels(game_id, str(match['_id']))

        # Announce match ended
        team1_names = ", ".join([p['username'] for p in match['team1']])
        team2_names = ", ".join([p['username'] for p in match['team2']])

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['name']} - Match Ended",
            description="Match has been completed. Players are now offline.",
            color=discord.Color.blue()
        )
        embed.add_field(name="🔴 Team 1", value=team1_names, inline=False)
        embed.add_field(name="🔵 Team 2", value=team2_names, inline=False)
        embed.set_footer(text="Points will be updated via Google Sheets")

        # Send response
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed)
        else:
            await interaction.response.send_message(embed=embed)

        # Notify players
        for player in all_players:
            member = interaction.guild.get_member(player['user_id'])
            if member:
                try:
                    notify_embed = discord.Embed(
                        title=f"{game_info['emoji']} Match Ended",
                        description=f"Your {game_info['name']} match has ended.\n\nYou are now **offline**. Use the button or `/online` command to queue for another match.",
                        color=discord.Color.blue()
                    )
                    await member.send(embed=notify_embed)
                except:
                    pass

        # Update channels
        cm = get_channel_manager(self.bot)
        await cm.update_upcoming_matches(interaction.guild, game_id)
        await cm.update_queue(interaction.guild, game_id)
        await cm.update_match_history(interaction.guild, game_id)

        # Check queue for next match
        if matchmaking_cog:
            enabled_games = await db.get_enabled_games()
            for enabled_game_id in enabled_games:
                await cm.update_queue(interaction.guild, enabled_game_id)
                await matchmaking_cog.check_and_create_match(interaction.guild, enabled_game_id)


    @app_commands.command(name="cancelmatch", description="[ADMIN] Cancel a pending match")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def cancel_match(self, interaction: discord.Interaction):
        """Cancel pending match"""
        await interaction.response.defer()

        enabled_games = await db.get_enabled_games()

        # Find all pending matches
        pending_matches = []
        for game_id in enabled_games:
            match = await db.get_pending_match(game_id)
            if match:
                pending_matches.append((game_id, match))

        if not pending_matches:
            await interaction.followup.send(
                "❌ No pending matches to cancel!",
                ephemeral=True
            )
            return

        if len(pending_matches) == 1:
            # Only one pending match
            game_id, match = pending_matches[0]
            await self.cancel_specific_match(interaction, game_id, match)
        else:
            # Multiple pending matches
            games_with_pending = [g for g, m in pending_matches]
            view = GameSelectViewAdmin(
                "cancel match for",
                games_with_pending,
                self.handle_cancel_match_selection,
                max_selections=1
            )
            await interaction.followup.send(
                "🎮 Multiple games have pending matches. Select which one to cancel:",
                view=view,
                ephemeral=True
            )

    async def handle_cancel_match_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle canceling match after game selection"""
        game_id = selected_games[0]
        match = await db.get_pending_match(game_id)

        if not match:
            await interaction.response.send_message(
                "❌ No pending match found!",
                ephemeral=True
            )
            return

        await self.cancel_specific_match(interaction, game_id, match)

    async def cancel_specific_match(self, interaction: discord.Interaction, game_id: str, match: dict):
        """Cancel a specific match"""
        game_info = config.GAMES[game_id]

        # Update match status
        await db.update_match(match['_id'], {'status': 'cancelled'})

        # Send response
        if interaction.response.is_done():
            await interaction.followup.send(f"✅ {game_info['name']} match has been cancelled.")
        else:
            await interaction.response.send_message(f"✅ {game_info['name']} match has been cancelled.")

        # Update channels
        cm = get_channel_manager(self.bot)
        await cm.update_upcoming_matches(interaction.guild, game_id)

        # Check queue again
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.check_and_create_match(interaction.guild, game_id)

    @app_commands.command(name="setpoints", description="[ADMIN] Set a player's points for a game")
    @app_commands.describe(member="The player", points="New point value")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def set_points(self, interaction: discord.Interaction, member: discord.Member, points: int):
        """Set player points - shows game selection"""
        player = await db.get_player(member.id)

        if not player:
            await interaction.response.send_message(
                f"❌ {member.name} is not registered!",
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

        # Store points value for callback
        self.temp_points_value = points
        self.temp_target_member = member

        view = GameSelectViewAdmin(
            f"set {member.name}'s points for",
            enabled_games,
            self.handle_setpoints_selection,
            max_selections=1
        )
        await interaction.response.send_message(
            f"🎮 Select which game to set {member.name}'s points to {points}:",
            view=view,
            ephemeral=True
        )

    async def handle_setpoints_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle setting points after game selection"""
        game_id = selected_games[0]
        game_info = config.GAMES[game_id]

        await db.update_game_stats(
            self.temp_target_member.id,
            game_id,
            {'points': self.temp_points_value}
        )

        await interaction.response.send_message(
            f"✅ Set {self.temp_target_member.name}'s {game_info['name']} points to {self.temp_points_value}"
        )

        # Update leaderboard
        cm = get_channel_manager(self.bot)
        await cm.update_leaderboard(interaction.guild, game_id)

    @app_commands.command(name="resetplayer", description="[ADMIN] Reset a player's stats for a game")
    @app_commands.describe(member="The player to reset")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def reset_player(self, interaction: discord.Interaction, member: discord.Member):
        """Reset player stats - shows game selection"""
        player = await db.get_player(member.id)

        if not player:
            await interaction.response.send_message(
                f"❌ {member.name} is not registered!",
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

        self.temp_target_member = member

        view = GameSelectViewAdmin(
            f"reset {member.name}'s stats for",
            enabled_games,
            self.handle_resetplayer_selection,
            max_selections=len(enabled_games)
        )
        await interaction.response.send_message(
            f"🎮 Select which game(s) to reset {member.name}'s stats for:",
            view=view,
            ephemeral=True
        )

    async def handle_resetplayer_selection(self, interaction: discord.Interaction, selected_games: list):
        """Handle resetting player after game selection"""
        for game_id in selected_games:
            await db.update_game_stats(self.temp_target_member.id, game_id, {
                'points': 0,
                'matches_played': 0,
                'wins': 0,
                'losses': 0,
                'queue_priority': 0
            })

        game_names = [config.GAMES[g]['name'] for g in selected_games]
        await interaction.response.send_message(
            f"✅ Reset {self.temp_target_member.name}'s stats for:\n" +
            "\n".join([f"• {name}" for name in game_names])
        )

        # Update leaderboards
        cm = get_channel_manager(self.bot)
        for game_id in selected_games:
            await cm.update_leaderboard(interaction.guild, game_id)

    @app_commands.command(name="listplayers", description="[ADMIN] List all registered players")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def list_players(self, interaction: discord.Interaction):
        """List all players"""
        players = await db.get_all_players()

        if not players:
            await interaction.response.send_message("❌ No players registered yet!")
            return

        embed = discord.Embed(
            title=f"👥 All Players ({len(players)})",
            color=discord.Color.blue()
        )

        description = ""
        for player in players[:25]:  # Discord embed field limit
            # Check queue status
            queue_status = player.get('queue_status', {})
            online_games = [config.GAMES[g]['emoji'] for g, s in queue_status.items() if s == 'online']
            status_text = "".join(online_games) if online_games else "⚪"

            # Check if in match
            if player.get('current_match_game'):
                game_emoji = config.GAMES[player['current_match_game']]['emoji']
                status_text = f"🎮{game_emoji}"

            description += f"{status_text} **{player['username']}**\n"

        if len(players) > 25:
            description += f"\n_...and {len(players) - 25} more_"

        embed.description = description
        embed.set_footer(text="⚪ = Offline | 🎮 = In Match | Game emojis = Queued")

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="forceoffline", description="[ADMIN] Force a player offline from all queues")
    @app_commands.describe(member="The player to force offline")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def force_offline(self, interaction: discord.Interaction, member: discord.Member):
        """Force a player offline from all queues"""
        player = await db.get_player(member.id)

        if not player:
            await interaction.response.send_message(
                f"❌ {member.name} is not registered!",
                ephemeral=True
            )
            return

        # Check if in active match
        if player.get('current_match_game'):
            game_info = config.GAMES[player['current_match_game']]
            await interaction.response.send_message(
                f"❌ Cannot force offline - {member.name} is in an active {game_info['name']} match!",
                ephemeral=True
            )
            return

        # Set all queues to offline
        queue_status = player.get('queue_status', {})
        for game_id in queue_status.keys():
            queue_status[game_id] = 'offline'

        await db.update_player(member.id, {'queue_status': queue_status})

        await interaction.response.send_message(
            f"✅ Forced {member.name} offline from all queues"
        )

        # Update all queue channels
        cm = get_channel_manager(self.bot)
        enabled_games = await db.get_enabled_games()
        for game_id in enabled_games:
            await cm.update_queue(interaction.guild, game_id)

    @app_commands.command(name="matchstatus", description="[ADMIN] View detailed status of all games")
    @app_commands.default_permissions(administrator=True)
    @is_admin()
    async def match_status(self, interaction: discord.Interaction):
        """View detailed match status across all games"""
        enabled_games = await db.get_enabled_games()

        if not enabled_games:
            await interaction.response.send_message(
                "❌ No games are currently enabled!",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📊 Detailed Match Status",
            description=f"Status across {len(enabled_games)} active game(s)",
            color=discord.Color.purple()
        )

        for game_id in enabled_games:
            game_info = config.GAMES[game_id]

            # Get comprehensive info
            online_players = await db.get_online_players(game_id)
            active_match = await db.get_active_match(game_id)
            pending_match = await db.get_pending_match(game_id)
            awaiting_match = await db.db.matches.find_one({
                'game_id': game_id,
                'status': 'awaiting_points'
            })

            status_lines = [
                f"**Queue:** {len(online_players)} players",
            ]

            if active_match:
                team1 = ", ".join([p['username'] for p in active_match['team1'][:2]])
                team2 = ", ".join([p['username'] for p in active_match['team2'][:2]])
                status_lines.append(f"**Active:** {team1}... vs {team2}...")
            else:
                status_lines.append("**Active:** None")

            if pending_match:
                status_lines.append("**Pending:** Match ready to start")
            else:
                status_lines.append("**Pending:** None")

            if awaiting_match:
                submitted = len(awaiting_match.get('points_submitted', {}))
                total = len(awaiting_match['team1'] + awaiting_match['team2'])
                status_lines.append(f"**Awaiting Points:** {submitted}/{total} submitted")
            else:
                status_lines.append("**Awaiting Points:** None")

            embed.add_field(
                name=f"{game_info['emoji']} {game_info['short_name']}",
                value="\n".join(status_lines),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(AdminCommands(bot))
    print("✅ Admin commands loaded")
