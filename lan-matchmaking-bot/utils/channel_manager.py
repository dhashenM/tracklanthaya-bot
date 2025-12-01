import discord
from utils.database import db
import config
from datetime import datetime


class MultiGameChannelManager:
    """Manages auto-updating information channels for multiple games"""

    def __init__(self, bot):
        self.bot = bot
        self.game_channels = {}  # {game_id: {channel_type: channel_id}}

    async def setup_all_game_channels(self, guild):
        """Set up channels for all games"""
        for game_id, game_info in config.GAMES.items():
            await self.setup_game_channels(guild, game_id)

        # Setup total leaderboard
        await self.setup_total_leaderboard(guild)

        print("✅ All game channels set up")

    async def setup_game_channels(self, guild, game_id: str):
        """Set up channels for a specific game"""
        game_info = config.GAMES[game_id]

        # Find or create game category
        category = discord.utils.get(guild.categories, name=game_info['category_name'])
        if not category:
            category = await guild.create_category(game_info['category_name'])

        # Initialize storage for this game
        if game_id not in self.game_channels:
            self.game_channels[game_id] = {}

        # Create all channels for this game
        channels_to_create = [
            ('general', f"💬│{config.GENERAL_CHANNEL_NAME}"),
            ('queue', f"🎮│{config.QUEUE_CHANNEL_NAME}"),
            ('upcoming', f"⏳│{config.UPCOMING_MATCHES_CHANNEL_NAME}"),
            ('history', f"📜│{config.MATCH_HISTORY_CHANNEL_NAME}"),
            ('leaderboard', f"🏆│{config.LEADERBOARD_CHANNEL_NAME}")
        ]

        for channel_type, channel_name in channels_to_create:
            channel = discord.utils.get(guild.text_channels, name=channel_name, category=category)
            if not channel:
                channel = await guild.create_text_channel(channel_name, category=category)

            self.game_channels[game_id][channel_type] = channel.id

            # Set permissions
            if channel_type != 'general':  # General is for chatting
                await channel.set_permissions(
                    guild.me,
                    send_messages=True,
                    embed_links=True,
                    read_messages=True,
                    read_message_history=True,
                    manage_messages=True
                )
                await channel.set_permissions(
                    guild.default_role,
                    send_messages=False,
                    add_reactions=False
                )

        # Initial updates for info channels
        await self.update_queue(guild, game_id)
        await self.update_leaderboard(guild, game_id)
        await self.update_match_history(guild, game_id)
        await self.update_upcoming_matches(guild, game_id)

    def get_channel(self, guild, game_id: str, channel_type: str):
        """Get a specific channel for a game"""
        if game_id not in self.game_channels:
            return None
        channel_id = self.game_channels[game_id].get(channel_type)
        return guild.get_channel(channel_id) if channel_id else None

    async def update_queue(self, guild, game_id: str):
        """Update queue channel for specific game"""
        channel = self.get_channel(guild, game_id, 'queue')
        if not channel:
            return

        game_info = config.GAMES[game_id]
        online_players = await db.get_online_players(game_id)

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['short_name']} - Queue",
            description=f"Players waiting: **{len(online_players)}**",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )

        if online_players:
            queue_text = ""
            for i, player in enumerate(online_players, 1):
                stats = await db.get_game_stats(player['user_id'], game_id)
                priority_star = "⭐" if stats.get('queue_priority', 0) > 0 else ""
                skill = player['skill_levels'].get(game_id, 5)
                queue_text += f"{i}. {priority_star}**{player['username']}** (Skill: {skill}/10)\n"
            embed.add_field(name="Players in Queue", value=queue_text, inline=False)
            embed.set_footer(text="⭐ = Priority • Updated")
        else:
            embed.add_field(name="Queue Status", value="*Queue is empty*", inline=False)
            embed.set_footer(text="Updated")

        await channel.purge(limit=100)
        await channel.send(embed=embed)

    async def update_leaderboard(self, guild, game_id: str):
        """Update leaderboard channel for specific game"""
        channel = self.get_channel(guild, game_id, 'leaderboard')
        if not channel:
            return

        game_info = config.GAMES[game_id]
        players = await db.get_leaderboard(game_id, 15)

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['short_name']} - Leaderboard",
            description="Top players by points",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        if players:
            leaderboard_text = ""
            for i, player_stats in enumerate(players, 1):
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`{i:2d}.`"

                matches = player_stats['matches_played']
                wins = player_stats['wins']
                win_rate = (wins / matches * 100) if matches > 0 else 0

                # Check if this game uses custom stats
                if game_id == 'rocket_league':
                    # Show Rocket League specific stats
                    leaderboard_text += (
                        f"{medal} **{player_stats['username']}**\n"
                        f"     └ Points: {player_stats['points']} | "
                        f"⚽ {player_stats.get('goals', 0)} | "
                        f"🎯 {player_stats.get('assists', 0)} | "
                        f"🛡️ {player_stats.get('saves', 0)} | "
                        f"🎾 {player_stats.get('shots', 0)}\n\n"
                    )
                else:
                    # Standard display for other games
                    leaderboard_text += (
                        f"{medal} **{player_stats['username']}**\n"
                        f"     └ Points: {player_stats['points']} | "
                        f"Matches: {matches} | "
                        f"Wins: {wins} ({win_rate:.0f}%)\n\n"
                    )

            embed.description = leaderboard_text
        else:
            embed.add_field(name="No Data", value="*No matches played yet*", inline=False)

        if game_id == 'rocket_league':
            embed.set_footer(text="⚽Goals 🎯Assists 🛡️Saves 🎾Shots • Updated")
        else:
            embed.set_footer(text="Updated")

        await channel.purge(limit=100)
        await channel.send(embed=embed)

    async def update_match_history(self, guild, game_id: str):
        """Update match history channel for specific game"""
        channel = self.get_channel(guild, game_id, 'history')
        if not channel:
            return

        game_info = config.GAMES[game_id]
        matches = await db.get_match_history(game_id, 10)

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['short_name']} - Match History",
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

        await channel.purge(limit=100)
        await channel.send(embed=embed)

    async def update_upcoming_matches(self, guild, game_id: str):
        """Update upcoming matches channel for specific game"""
        channel = self.get_channel(guild, game_id, 'upcoming')
        if not channel:
            return

        game_info = config.GAMES[game_id]
        active_match = await db.get_active_match(game_id)
        pending_match = await db.get_pending_match(game_id)

        embed = discord.Embed(
            title=f"{game_info['emoji']} {game_info['short_name']} - Upcoming Matches",
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

        await channel.purge(limit=100)
        await channel.send(embed=embed)

    async def setup_total_leaderboard(self, guild):
        """Set up the overall leaderboard category and channel"""
        # Find or create category
        category = discord.utils.get(guild.categories, name=config.TOTAL_LEADERBOARD_CATEGORY)
        if not category:
            category = await guild.create_category(config.TOTAL_LEADERBOARD_CATEGORY)

        # Create channel
        channel = discord.utils.get(guild.text_channels, name=config.TOTAL_LEADERBOARD_CHANNEL, category=category)
        if not channel:
            channel = await guild.create_text_channel(config.TOTAL_LEADERBOARD_CHANNEL, category=category)

        # Set permissions (read-only)
        await channel.set_permissions(
            guild.me,
            send_messages=True,
            embed_links=True,
            read_messages=True,
            read_message_history=True,
            manage_messages=True
        )
        await channel.set_permissions(
            guild.default_role,
            send_messages=False,
            add_reactions=False
        )

        # Store channel ID
        self.total_leaderboard_channel_id = channel.id

        # Initial update
        await self.update_total_leaderboard(guild)

        print("✅ Total leaderboard set up")

    async def update_total_leaderboard(self, guild):
        """Update the overall leaderboard showing total points across all games"""
        channel_id = getattr(self, 'total_leaderboard_channel_id', None)

        if not channel_id:
            # Try to find it
            category = discord.utils.get(guild.categories, name=config.TOTAL_LEADERBOARD_CATEGORY)
            if category:
                channel = discord.utils.get(guild.text_channels, name=config.TOTAL_LEADERBOARD_CHANNEL,
                                            category=category)
                if channel:
                    channel_id = channel.id
                    self.total_leaderboard_channel_id = channel_id

        if not channel_id:
            return

        channel = guild.get_channel(channel_id)
        if not channel:
            return

        # Get all players and calculate total points
        all_players = await db.get_all_players()

        player_totals = []

        for player in all_players:
            total_points = 0
            total_matches = 0

            # Sum across all games
            for game_id in config.GAMES.keys():
                stats = await db.get_game_stats(player['user_id'], game_id)
                total_points += stats.get('points', 0)
                total_matches += stats.get('matches_played', 0)

            if total_points > 0 or total_matches > 0:
                player_totals.append({
                    'username': player['username'],
                    'total_points': total_points,
                    'total_matches': total_matches,
                    'user_id': player['user_id']
                })

        # Sort by total points
        player_totals.sort(key=lambda x: x['total_points'], reverse=True)

        embed = discord.Embed(
            title="🏆 Overall Leaderboard",
            description="Total points across all games",
            color=discord.Color.gold(),
            timestamp=datetime.utcnow()
        )

        if player_totals:
            leaderboard_text = ""
            for i, player in enumerate(player_totals[:20], 1):  # Top 20
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`{i:2d}.`"

                leaderboard_text += (
                    f"{medal} **{player['username']}**\n"
                    f"     └ Total Points: {player['total_points']:.2f} | "
                    f"Total Matches: {player['total_matches']}\n\n"
                )

            embed.description = leaderboard_text
        else:
            embed.add_field(name="No Data", value="*No matches played yet*", inline=False)

        embed.set_footer(text="Combined score from all games • Updated")

        try:
            await channel.purge(limit=100)
            await channel.send(embed=embed)
        except Exception as e:
            print(f"Error updating total leaderboard: {e}")

# Global instance
channel_manager = None


def get_channel_manager(bot):
    """Get or create channel manager instance"""
    global channel_manager
    if channel_manager is None:
        channel_manager = MultiGameChannelManager(bot)
    return channel_manager