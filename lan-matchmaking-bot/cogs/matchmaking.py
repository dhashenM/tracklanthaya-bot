import discord
from discord.ext import commands
from discord import app_commands
from utils.database import db
from utils.matchmaking_logic import create_match_from_queue
from utils.channel_manager import get_channel_manager
import config
from datetime import datetime, timedelta
import asyncio


class MatchmakingCommands(commands.Cog):
    """Matchmaking logic and match management for multiple games"""

    def __init__(self, bot):
        self.bot = bot
        # Track used combinations per game: {game_id: set()}
        self.used_combinations = {}
        # Track created channels per game: {game_id: {match_id: [channels]}}
        self.match_channels = {}
        # Track points entry timers: {match_id: task}
        self.points_entry_timers = {}

    async def check_and_create_match(self, guild, game_id: str):
        """Check queue and create match if possible for specific game"""
        # Check if this game is enabled
        enabled_games = await db.get_enabled_games()
        if game_id not in enabled_games:
            return

        # Check if there's already an active or pending match for this game
        active_match = await db.get_active_match(game_id)
        pending_match = await db.get_pending_match(game_id)

        if active_match or pending_match:
            return  # Wait until current matches are handled

        # Get online players for this game who aren't in ANY match
        online_players = await db.get_online_players(game_id)

        game_info = config.GAMES[game_id]
        match_size = game_info['team_size'] * 2

        if len(online_players) < match_size:
            return  # Not enough players

        # Get or initialize used combinations for this game
        if game_id not in self.used_combinations:
            self.used_combinations[game_id] = set()

        # Create match from queue
        match_result = create_match_from_queue(
            online_players,
            game_id,
            self.used_combinations[game_id]
        )

        if not match_result:
            return  # Couldn't create balanced match

        # Store the combination to avoid repetition
        self.used_combinations[game_id].add(match_result['combo_id'])

        # Keep only last 5 combinations per game
        if len(self.used_combinations[game_id]) > 5:
            combos_list = list(self.used_combinations[game_id])
            self.used_combinations[game_id] = set(combos_list[-5:])

        # Create match in database
        match_data = {
            'team1': match_result['team1'],
            'team2': match_result['team2'],
            'imbalance': match_result['imbalance'],
            'status': 'pending',
            'points_submitted': {},
            'points_verified': False
        }

        match = await db.create_match(game_id, match_data)

        # Update priority for leftover players
        for player in match_result['leftover_players']:
            stats = await db.get_game_stats(player['user_id'], game_id)
            current_priority = stats.get('queue_priority', 0)
            await db.update_game_stats(
                player['user_id'],
                game_id,
                {'queue_priority': current_priority + 1}
            )

        # Reset priority for matched players
        for player in match_result['team1'] + match_result['team2']:
            await db.update_game_stats(player['user_id'], game_id, {'queue_priority': 0})

        # Notify admin
        await self.notify_admin_new_match(guild, game_id, match)

        # Notify matched players
        await self.notify_matched_players(guild, game_id, match)

        # Update channels
        cm = get_channel_manager(self.bot)
        await cm.update_upcoming_matches(guild, game_id)

    async def notify_admin_new_match(self, guild, game_id: str, match: dict):
        """Notify admin about new match"""
        game_info = config.GAMES[game_id]
        match_type = game_info.get('match_type', 'team')

        # Update upcoming matches channel
        cm = get_channel_manager(self.bot)
        await cm.update_upcoming_matches(guild, game_id)

        # Find admin role
        admin_role = discord.utils.get(guild.roles, name=config.ADMIN_ROLE_NAME)

        if not admin_role:
            print("⚠️ Admin role not found!")
            return

        # Send to general channel for this game
        channel = cm.get_channel(guild, game_id, 'general')

        if not channel:
            channel = guild.text_channels[0] if guild.text_channels else None

        if not channel:
            return

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['name']} - New Match Ready!",
            description=f"{admin_role.mention} A new match has been created and is awaiting your approval.",
            color=discord.Color.orange()
        )

        # Different display for different match types
        if match_type == 'ffa':
            # Free-for-all
            all_players = match['team1']
            player_names = ", ".join([p['username'] for p in all_players])
            avg_skill = sum(p['skill_level'] for p in all_players) / len(all_players)

            embed.add_field(
                name=f"🏁 {len(all_players)} Players",
                value=player_names,
                inline=False
            )
            embed.add_field(
                name="⚖️ Average Skill",
                value=f"{avg_skill:.1f}/10",
                inline=False
            )

        elif match_type == '1v1':
            # 1v1
            player1 = match['team1'][0]
            player2 = match['team2'][0]

            embed.add_field(
                name="🥊 Player 1",
                value=f"{player1['username']} (Skill: {player1['skill_level']}/10)",
                inline=True
            )
            embed.add_field(
                name="🥊 Player 2",
                value=f"{player2['username']} (Skill: {player2['skill_level']}/10)",
                inline=True
            )
            embed.add_field(
                name="⚖️ Skill Difference",
                value=f"{match['imbalance']:.1f}",
                inline=False
            )

        else:
            # Team-based
            team1_names = ", ".join([p['username'] for p in match['team1']])
            team2_names = ", ".join([p['username'] for p in match['team2']])

            team1_skill = sum(p['skill_level'] for p in match['team1'])
            team2_skill = sum(p['skill_level'] for p in match['team2'])

            embed.add_field(
                name="🔴 Team 1 (Skill: {})".format(team1_skill),
                value=team1_names,
                inline=False
            )

            embed.add_field(
                name="🔵 Team 2 (Skill: {})".format(team2_skill),
                value=team2_names,
                inline=False
            )

            embed.add_field(
                name="⚖️ Balance",
                value=f"Skill Imbalance: {match['imbalance']}",
                inline=False
            )

        embed.set_footer(text=f"Match ID: {match['_id']}\nUse /startmatch")

        await channel.send(embed=embed)

    async def notify_matched_players(self, guild, game_id: str, match: dict):
        """Notify players they've been matched"""
        game_info = config.GAMES[game_id]
        all_players = match['team1'] + match['team2']

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['name']} - Match Found!",
            description="You've been matched! Waiting for admin to start the match.",
            color=discord.Color.green()
        )

        team1_names = ", ".join([p['username'] for p in match['team1']])
        team2_names = ", ".join([p['username'] for p in match['team2']])

        embed.add_field(name="🔴 Team 1", value=team1_names, inline=False)
        embed.add_field(name="🔵 Team 2", value=team2_names, inline=False)

        for player in all_players:
            member = guild.get_member(player['user_id'])
            if member:
                try:
                    await member.send(embed=embed)
                except:
                    pass  # User might have DMs disabled

    async def create_match_channels(self, guild, game_id: str, match: dict):
        """Create voice and text channels for the match"""
        game_info = config.GAMES[game_id]
        match_type = game_info.get('match_type', 'team')

        # Find game category
        category = discord.utils.get(guild.categories, name=game_info['category_name'])

        if not category:
            print(f"⚠️ Category not found for {game_info['name']}")
            return

        # For FFA games, create only one set of channels
        if match_type == 'ffa':
            # Create single voice and text channel for all players
            match_voice = await guild.create_voice_channel(
                f"{game_info['emoji']} Match Lobby",
                category=category
            )
            match_text = await guild.create_text_channel(
                f"{game_info['emoji'].lower()}│match-chat",
                category=category
            )

            # Store channel references
            if game_id not in self.match_channels:
                self.match_channels[game_id] = {}

            match_id = str(match['_id'])
            self.match_channels[game_id][match_id] = [match_voice, match_text]

            # Set permissions for all players
            all_players = match['team1']  # In FFA, all players are in team1
            for player in all_players:
                member = guild.get_member(player['user_id'])
                if member:
                    await match_voice.set_permissions(member, connect=True, speak=True, view_channel=True)
                    await match_text.set_permissions(member, read_messages=True, send_messages=True)

            # Send welcome message
            player_mentions = " ".join([f"<@{p['user_id']}>" for p in all_players])

            await match_text.send(
                f"{game_info['emoji']} **Free-For-All Match - GO!**\n{player_mentions}\n\n"
                f"Join the voice channel and may the best racer win!"
            )

            return match_voice, match_text

        # For 1v1, create simple channels
        elif match_type == '1v1':
            match_voice = await guild.create_voice_channel(
                f"{game_info['emoji']} Match Arena",
                category=category
            )
            match_text = await guild.create_text_channel(
                f"{game_info['emoji'].lower()}│match-chat",
                category=category
            )

            if game_id not in self.match_channels:
                self.match_channels[game_id] = {}

            match_id = str(match['_id'])
            self.match_channels[game_id][match_id] = [match_voice, match_text]

            # Set permissions for both players
            all_players = match['team1'] + match['team2']
            for player in all_players:
                member = guild.get_member(player['user_id'])
                if member:
                    await match_voice.set_permissions(member, connect=True, speak=True, view_channel=True)
                    await match_text.set_permissions(member, read_messages=True, send_messages=True)

            # Send welcome message
            player1_mention = f"<@{match['team1'][0]['user_id']}>"
            player2_mention = f"<@{match['team2'][0]['user_id']}>"

            await match_text.send(
                f"{game_info['emoji']} **1v1 Match!**\n"
                f"{player1_mention} vs {player2_mention}\n\n"
                f"Good luck!"
            )

            return match_voice, match_text

        # Standard team-based game (existing code)
        else:
            # Create Team 1 channels
            team1_voice = await guild.create_voice_channel(
                config.TEAM1_CHANNEL_NAME,
                category=category
            )
            team1_text = await guild.create_text_channel(
                "🔴│team-1-chat",
                category=category
            )

            # Create Team 2 channels
            team2_voice = await guild.create_voice_channel(
                config.TEAM2_CHANNEL_NAME,
                category=category
            )
            team2_text = await guild.create_text_channel(
                "🔵│team-2-chat",
                category=category
            )

            # Store channel references
            if game_id not in self.match_channels:
                self.match_channels[game_id] = {}

            match_id = str(match['_id'])
            self.match_channels[game_id][match_id] = [team1_voice, team1_text, team2_voice, team2_text]

            # Set permissions for Team 1
            for player in match['team1']:
                member = guild.get_member(player['user_id'])
                if member:
                    await team1_voice.set_permissions(member, connect=True, speak=True, view_channel=True)
                    await team1_text.set_permissions(member, read_messages=True, send_messages=True)
                    await team2_voice.set_permissions(member, connect=False, view_channel=False)
                    await team2_text.set_permissions(member, read_messages=False)

            # Set permissions for Team 2
            for player in match['team2']:
                member = guild.get_member(player['user_id'])
                if member:
                    await team2_voice.set_permissions(member, connect=True, speak=True, view_channel=True)
                    await team2_text.set_permissions(member, read_messages=True, send_messages=True)
                    await team1_voice.set_permissions(member, connect=False, view_channel=False)
                    await team1_text.set_permissions(member, read_messages=False)

            # Send welcome messages
            team1_mentions = " ".join([f"<@{p['user_id']}>" for p in match['team1']])
            team2_mentions = " ".join([f"<@{p['user_id']}>" for p in match['team2']])

            await team1_text.send(
                f"🔴 **Team 1 - Let's go!**\n{team1_mentions}\n\n"
                f"Join your voice channel and coordinate your strategy!"
            )

            await team2_text.send(
                f"🔵 **Team 2 - Let's go!**\n{team2_mentions}\n\n"
                f"Join your voice channel and coordinate your strategy!"
            )

            return team1_voice, team1_text, team2_voice, team2_text

    async def delete_match_channels(self, game_id: str, match_id: str):
        """Delete channels for a match"""
        if game_id in self.match_channels and match_id in self.match_channels[game_id]:
            channels = self.match_channels[game_id][match_id]
            for channel in channels:
                try:
                    await channel.delete()
                except Exception as e:
                    print(f"Error deleting channel: {e}")
            del self.match_channels[game_id][match_id]

    async def start_points_entry_timer(self, guild, game_id: str, match_id: str):
        """Start timer for points entry"""
        # Cancel existing timer if any
        if match_id in self.points_entry_timers:
            self.points_entry_timers[match_id].cancel()

        # Create new timer
        async def timer_callback():
            await asyncio.sleep(config.POINTS_ENTRY_TIMEOUT)

            # Check if points are still not verified
            match = await db.get_match(match_id)
            if match and not match.get('points_verified', False):
                # Find admin channel
                cm = get_channel_manager(self.bot)
                channel = cm.get_channel(guild, game_id, 'general')

                if not channel:
                    channel = guild.text_channels[0] if guild.text_channels else None

                if channel:
                    game_info = config.GAMES[game_id]
                    admin_role = discord.utils.get(guild.roles, name=config.ADMIN_ROLE_NAME)
                    mention = admin_role.mention if admin_role else "Admins"

                    await channel.send(
                        f"⚠️ {mention} Points entry timeout for **{game_info['name']}** match `{match_id}`. "
                        f"Please verify points using `/verifypoints`"
                    )

        # Start timer
        task = asyncio.create_task(timer_callback())
        self.points_entry_timers[match_id] = task


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(MatchmakingCommands(bot))
    print("✅ Matchmaking commands loaded")
