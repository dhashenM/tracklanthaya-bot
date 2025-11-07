import discord
from discord.ext import commands
from discord import app_commands
from utils.database import db
from utils.matchmaking_logic import create_match_from_queue
import config
from datetime import datetime, timedelta
import asyncio
from utils.channel_manager import get_channel_manager


class MatchmakingCommands(commands.Cog):
    """Matchmaking logic and match management"""

    def __init__(self, bot):
        self.bot = bot
        self.used_combinations = set()  # Track recent team combinations
        self.match_channels = {}  # Track created channels {match_id: [channels]}
        self.points_entry_timers = {}  # Track points entry timeouts

    async def check_and_create_match(self, guild):
        """Check queue and create match if possible"""
        # Check if matchmaking is enabled
        matchmaking_enabled = await db.get_system_setting('matchmaking_enabled')
        if not matchmaking_enabled:
            return

        # Check if there's already an active or pending match
        active_match = await db.get_active_match()
        pending_match = await db.get_pending_match()

        if active_match or pending_match:
            return  # Wait until current matches are handled

        # Get online players
        online_players = await db.get_online_players()

        if len(online_players) < config.MATCH_SIZE:
            return  # Not enough players

        # Create match from queue
        match_result = create_match_from_queue(online_players, self.used_combinations)

        if not match_result:
            return  # Couldn't create balanced match

        # Store the combination to avoid repetition
        self.used_combinations.add(match_result['combo_id'])

        # Keep only last 5 combinations
        if len(self.used_combinations) > 5:
            self.used_combinations = set(list(self.used_combinations)[-5:])

        # Create match in database
        match_data = {
            'team1': match_result['team1'],
            'team2': match_result['team2'],
            'imbalance': match_result['imbalance'],
            'status': 'pending',
            'points_submitted': {},  # {user_id: points}
            'points_verified': False
        }

        match = await db.create_match(match_data)

        # Update priority for leftover players
        for player in match_result['leftover_players']:
            current_priority = player.get('queue_priority', 0)
            await db.update_player(player['user_id'], {'queue_priority': current_priority + 1})

        # Reset priority for matched players
        for player in match_result['team1'] + match_result['team2']:
            await db.update_player(player['user_id'], {'queue_priority': 0})

        # Notify admin
        await self.notify_admin_new_match(guild, match)

        # Notify matched players
        await self.notify_matched_players(guild, match)

    async def notify_admin_new_match(self, guild, match):
        """Notify admin about new match"""
        # Update upcoming matches channel
        cm = get_channel_manager(self.bot)
        await cm.update_upcoming_matches(guild)

        # Find admin role
        admin_role = discord.utils.get(guild.roles, name=config.ADMIN_ROLE_NAME)

        if not admin_role:
            print("⚠️ Admin role not found!")
            return

        # Find a text channel to send notification (use first available)
        channel = guild.text_channels[0] if guild.text_channels else None

        if not channel:
            return

        team1_names = ", ".join([p['username'] for p in match['team1']])
        team2_names = ", ".join([p['username'] for p in match['team2']])

        team1_skill = sum(p['skill_level'] for p in match['team1'])
        team2_skill = sum(p['skill_level'] for p in match['team2'])

        embed = discord.Embed(
            title="🎮 New Match Ready!",
            description=f"{admin_role.mention} A new match has been created and is awaiting your approval.",
            color=discord.Color.orange()
        )

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

        embed.set_footer(text=f"Match ID: {match['_id']}\nUse /startmatch or /cancelmatch")

        await channel.send(embed=embed)

    async def notify_matched_players(self, guild, match):
        """Notify players they've been matched"""
        all_players = match['team1'] + match['team2']

        embed = discord.Embed(
            title="🎮 Match Found!",
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

    async def create_match_channels(self, guild, match):
        """Create voice and text channels for the match"""
        # Find or create category
        category = discord.utils.get(guild.categories, name=config.MATCH_CATEGORY_NAME)

        if not category:
            category = await guild.create_category(config.MATCH_CATEGORY_NAME)

        # Create Team 1 channels
        team1_voice = await guild.create_voice_channel(
            config.TEAM1_CHANNEL_NAME,
            category=category
        )
        team1_text = await guild.create_text_channel(
            "team-1-chat",
            category=category
        )

        # Create Team 2 channels
        team2_voice = await guild.create_voice_channel(
            config.TEAM2_CHANNEL_NAME,
            category=category
        )
        team2_text = await guild.create_text_channel(
            "team-2-chat",
            category=category
        )

        # Store channel references
        match_id = str(match['_id'])
        self.match_channels[match_id] = [team1_voice, team1_text, team2_voice, team2_text]

        # Set permissions for Team 1
        for player in match['team1']:
            member = guild.get_member(player['user_id'])
            if member:
                await team1_voice.set_permissions(member, connect=True, speak=True)
                await team1_text.set_permissions(member, read_messages=True, send_messages=True)
                await team2_voice.set_permissions(member, connect=False)
                await team2_text.set_permissions(member, read_messages=False)

        # Set permissions for Team 2
        for player in match['team2']:
            member = guild.get_member(player['user_id'])
            if member:
                await team2_voice.set_permissions(member, connect=True, speak=True)
                await team2_text.set_permissions(member, read_messages=True, send_messages=True)
                await team1_voice.set_permissions(member, connect=False)
                await team1_text.set_permissions(member, read_messages=False)

        return team1_voice, team1_text, team2_voice, team2_text

    async def delete_match_channels(self, match_id):
        """Delete channels for a match"""
        if match_id in self.match_channels:
            channels = self.match_channels[match_id]
            for channel in channels:
                try:
                    await channel.delete()
                except:
                    pass  # Channel might already be deleted
            del self.match_channels[match_id]

    async def start_points_entry_timer(self, guild, match_id):
        """Start timer for points entry"""
        await asyncio.sleep(config.POINTS_ENTRY_TIMEOUT)

        # Check if points are still not verified
        match = await db.get_match(match_id)
        if match and not match.get('points_verified', False):
            # Find admin channel
            channel = guild.text_channels[0] if guild.text_channels else None
            if channel:
                await channel.send(
                    f"⚠️ Points entry timeout for match {match_id}. "
                    f"Please verify points using `/verifypoints {match_id}`"
                )


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(MatchmakingCommands(bot))
    print("✅ Matchmaking commands loaded")