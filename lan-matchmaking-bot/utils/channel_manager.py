import discord
from utils.database import db
import config
from datetime import datetime


class ChannelManager:
    """Manages auto-updating information channels"""

    def __init__(self, bot):
        self.bot = bot
        self.channel_ids = {}  # Store channel IDs

    async def setup_channels(self, guild):
        """Create or find all info channels"""
        # Find or create category
        category = discord.utils.get(guild.categories, name=config.INFO_CATEGORY_NAME)
        if not category:
            category = await guild.create_category(config.INFO_CATEGORY_NAME)

        # Create/find each channel
        self.channel_ids['queue'] = await self._get_or_create_channel(
            guild, category, config.QUEUE_CHANNEL_NAME
        )
        self.channel_ids['leaderboard'] = await self._get_or_create_channel(
            guild, category, config.LEADERBOARD_CHANNEL_NAME
        )
        self.channel_ids['history'] = await self._get_or_create_channel(
            guild, category, config.MATCH_HISTORY_CHANNEL_NAME
        )
        self.channel_ids['upcoming'] = await self._get_or_create_channel(
            guild, category, config.UPCOMING_MATCHES_CHANNEL_NAME
        )

        # Set channel permissions (read-only for @everyone, bot can send)
        for channel_id in self.channel_ids.values():
            channel = guild.get_channel(channel_id)
            if channel:
                # Allow bot to send messages
                await channel.set_permissions(
                    guild.me,  # The bot itself
                    send_messages=True,
                    embed_links=True,
                    read_messages=True,
                    read_message_history=True,
                    manage_messages=True  # For purging old messages
                )
                # Prevent everyone else from sending
                await channel.set_permissions(
                    guild.default_role,
                    send_messages=False,
                    add_reactions=False
                )

        # Initial updates
        await self.update_queue(guild)
        await self.update_leaderboard(guild)
        await self.update_match_history(guild)
        await self.update_upcoming_matches(guild)

        print("✅ Info channels set up")

    async def _get_or_create_channel(self, guild, category, name):
        """Get existing channel or create new one"""
        channel = discord.utils.get(guild.text_channels, name=name)
        if not channel:
            channel = await guild.create_text_channel(name, category=category)
        return channel.id

    async def update_queue(self, guild):
        """Update queue channel"""
        channel = guild.get_channel(self.channel_ids.get('queue'))
        if not channel:
            return

        online_players = await db.get_online_players()

        embed = discord.Embed(
            title="🎮 Matchmaking Queue",
            description=f"Players waiting for match: **{len(online_players)}**",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        if online_players:
            queue_text = ""
            for i, player in enumerate(online_players, 1):
                priority_star = "⭐" if player.get('queue_priority', 0) > 0 else ""
                queue_text += f"{i}. {priority_star}**{player['username']}** (Skill: {player['skill_level']}/10)\n"
            embed.add_field(name="Players in Queue", value=queue_text, inline=False)
            embed.set_footer(text="⭐ = Priority (skipped in previous match) • Updated")
        else:
            embed.add_field(name="Queue Status", value="*Queue is empty*", inline=False)

        # Clear channel and send new message
        await channel.purge(limit=100)
        await channel.send(embed=embed)

    async def update_leaderboard(self, guild):
        """Update leaderboard channel"""
        channel = guild.get_channel(self.channel_ids.get('leaderboard'))
        if not channel:
            return

        players = await db.get_leaderboard(15)

        embed = discord.Embed(
            title="🏆 Player Leaderboard",
            description="Top players by points",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        if players:
            leaderboard_text = ""
            for i, player in enumerate(players, 1):
                if i == 1:
                    medal = "🥇"
                elif i == 2:
                    medal = "🥈"
                elif i == 3:
                    medal = "🥉"
                else:
                    medal = f"`{i:2d}.`"

                win_rate = (player['wins'] / player['matches_played'] * 100) if player['matches_played'] > 0 else 0
                leaderboard_text += (
                    f"{medal} **{player['username']}**\n"
                    f"     └ Points: {player['points']} | "
                    f"Matches: {player['matches_played']} | "
                    f"Wins: {player['wins']} ({win_rate:.0f}%)\n\n"
                )

            embed.description = leaderboard_text
        else:
            embed.add_field(name="No Data", value="*No matches played yet*", inline=False)

        embed.set_footer(text="Updated")

        # Clear channel and send new message
        await channel.purge(limit=100)
        await channel.send(embed=embed)

    async def update_match_history(self, guild):
        """Update match history channel"""
        channel = guild.get_channel(self.channel_ids.get('history'))
        if not channel:
            return

        matches = await db.get_match_history(10)

        embed = discord.Embed(
            title="📜 Match History",
            description="Recent completed matches",
            color=discord.Color.blue(),
            timestamp=datetime.utcnow()
        )

        if matches:
            for i, match in enumerate(matches, 1):
                team1_names = ", ".join([p['username'] for p in match['team1']])
                team2_names = ", ".join([p['username'] for p in match['team2']])
                team1_score = match.get('team1_score', 0)
                team2_score = match.get('team2_score', 0)
                winning_team = match.get('winning_team', 0)

                if winning_team == 0:
                    result = "🤝 Tie"
                elif winning_team == 1:
                    result = "🔴 Team 1 Won"
                else:
                    result = "🔵 Team 2 Won"

                match_time = match.get('verified_at', match.get('created_at'))
                time_str = f"<t:{int(match_time.timestamp())}:R>" if match_time else "Unknown"

                match_text = (
                    f"**Score:** {team1_score} - {team2_score} | {result}\n"
                    f"🔴 {team1_names}\n"
                    f"🔵 {team2_names}\n"
                    f"⏰ {time_str}"
                )

                embed.add_field(
                    name=f"Match #{len(matches) - i + 1}",
                    value=match_text,
                    inline=False
                )
        else:
            embed.add_field(name="No History", value="*No matches completed yet*", inline=False)

        embed.set_footer(text="Updated")

        # Clear channel and send new message
        await channel.purge(limit=100)
        await channel.send(embed=embed)

    async def update_upcoming_matches(self, guild):
        """Update upcoming matches channel"""
        channel = guild.get_channel(self.channel_ids.get('upcoming'))
        if not channel:
            return

        active_match = await db.get_active_match()
        pending_match = await db.get_pending_match()

        embed = discord.Embed(
            title="⏳ Upcoming Matches",
            color=discord.Color.orange(),
            timestamp=datetime.utcnow()
        )

        # Active match
        if active_match:
            team1_names = ", ".join([p['username'] for p in active_match['team1']])
            team2_names = ", ".join([p['username'] for p in active_match['team2']])
            active_text = (
                f"🔴 **Team 1:** {team1_names}\n"
                f"🔵 **Team 2:** {team2_names}\n"
                f"⏰ Started <t:{int(active_match['started_at'].timestamp())}:R>"
            )
            embed.add_field(name="⚡ Currently Playing", value=active_text, inline=False)
        else:
            embed.add_field(name="⚡ Currently Playing", value="*No active match*", inline=False)

        # Pending match
        if pending_match:
            team1_names = ", ".join([p['username'] for p in pending_match['team1']])
            team2_names = ", ".join([p['username'] for p in pending_match['team2']])
            pending_text = (
                f"🔴 **Team 1:** {team1_names}\n"
                f"🔵 **Team 2:** {team2_names}\n"
                f"⏰ Waiting for admin to start..."
            )
            embed.add_field(name="🔜 Next Match", value=pending_text, inline=False)
        else:
            embed.add_field(name="🔜 Next Match", value="*No match scheduled*", inline=False)

        embed.set_footer(text="Updated")

        # Clear channel and send new message
        await channel.purge(limit=100)
        await channel.send(embed=embed)


# Global instance
channel_manager = None


def get_channel_manager(bot):
    """Get or create channel manager instance"""
    global channel_manager
    if channel_manager is None:
        channel_manager = ChannelManager(bot)
    return channel_manager