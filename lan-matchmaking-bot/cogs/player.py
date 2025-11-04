import discord
from discord.ext import commands
from discord import app_commands
from utils.database import db
import config


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
            "✅ Registration successful! Use `/setskill` to set your skill level (1-10).",
            ephemeral=True
        )

    @app_commands.command(name="setskill", description="Set your skill level (1-10)")
    @app_commands.describe(level="Your skill level from 1 (beginner) to 10 (expert)")
    async def setskill(self, interaction: discord.Interaction, level: int):
        """Set player skill level"""
        # Validate skill level
        if level < 1 or level > 10:
            await interaction.response.send_message(
                "❌ Skill level must be between 1 and 10!",
                ephemeral=True
            )
            return

        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        await db.update_player(interaction.user.id, {'skill_level': level})
        await interaction.response.send_message(
            f"✅ Skill level set to {level}/10",
            ephemeral=True
        )

    @app_commands.command(name="online", description="Set yourself as online for matchmaking")
    async def go_online(self, interaction: discord.Interaction):
        """Set player status to online"""
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        # Check if matchmaking is enabled
        matchmaking_enabled = await db.get_system_setting('matchmaking_enabled')
        if not matchmaking_enabled:
            await interaction.response.send_message(
                "❌ Matchmaking is currently disabled by admins.",
                ephemeral=True
            )
            return

        if player['status'] == 'online':
            await interaction.response.send_message(
                "⚠️ You're already online!",
                ephemeral=True
            )
            return

        # Check if player is in an active match
        active_match = await db.get_active_match()
        if active_match:
            all_player_ids = [p['user_id'] for p in active_match['team1'] + active_match['team2']]
            if interaction.user.id in all_player_ids:
                await interaction.response.send_message(
                    "❌ You're currently in an active match!",
                    ephemeral=True
                )
                return

        await db.update_player(interaction.user.id, {'status': 'online'})
        await interaction.response.send_message(
            "✅ You are now online and in the matchmaking queue!",
            ephemeral=True
        )

        # Trigger matchmaking check
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.check_and_create_match(interaction.guild)

    @app_commands.command(name="offline", description="Set yourself as offline (leave queue)")
    async def go_offline(self, interaction: discord.Interaction):
        """Set player status to offline"""
        player = await db.get_player(interaction.user.id)

        if not player:
            await interaction.response.send_message(
                "❌ You need to register first! Use `/register`",
                ephemeral=True
            )
            return

        if player['status'] == 'offline':
            await interaction.response.send_message(
                "⚠️ You're already offline!",
                ephemeral=True
            )
            return

        await db.update_player(interaction.user.id, {'status': 'offline'})
        await interaction.response.send_message(
            "✅ You are now offline and removed from the queue.",
            ephemeral=True
        )

    @app_commands.command(name="profile", description="View your profile")
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
        embed.add_field(name="Skill Level", value=f"{player['skill_level']}/10", inline=True)
        embed.add_field(name="Status", value=player['status'].title(), inline=True)
        embed.add_field(name="Points", value=player['points'], inline=True)
        embed.add_field(name="Matches Played", value=player['matches_played'], inline=True)
        embed.add_field(name="Wins", value=player['wins'], inline=True)
        embed.add_field(name="Losses", value=player['losses'], inline=True)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="View the top players")
    async def leaderboard(self, interaction: discord.Interaction):
        """Display leaderboard"""
        players = await db.get_leaderboard(10)

        if not players:
            await interaction.response.send_message("❌ No players registered yet!")
            return

        embed = discord.Embed(
            title="🏆 Leaderboard - Top 10 Players",
            color=discord.Color.gold()
        )

        description = ""
        for i, player in enumerate(players, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            description += f"{medal} **{player['username']}** - {player['points']} pts (Skill: {player['skill_level']}/10)\n"

        embed.description = description
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="queue", description="View current matchmaking queue")
    async def view_queue(self, interaction: discord.Interaction):
        """View players in queue"""
        online_players = await db.get_online_players()

        if not online_players:
            await interaction.response.send_message("📭 Queue is empty!")
            return

        embed = discord.Embed(
            title=f"📋 Matchmaking Queue ({len(online_players)} players)",
            color=discord.Color.green()
        )

        description = ""
        for i, player in enumerate(online_players, 1):
            priority_star = "⭐" if player.get('queue_priority', 0) > 0 else ""
            description += f"{i}. {priority_star}**{player['username']}** (Skill: {player['skill_level']}/10)\n"

        embed.description = description
        embed.set_footer(text="⭐ = Priority (skipped in previous match)")

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="matches", description="View match information")
    async def matches(self, interaction: discord.Interaction):
        """View active, pending, and recent matches"""
        active_match = await db.get_active_match()
        pending_match = await db.get_pending_match()
        match_history = await db.get_match_history(5)

        embed = discord.Embed(
            title="🎮 Match Information",
            color=discord.Color.purple()
        )

        # Active match
        if active_match:
            team1_names = ", ".join([p['username'] for p in active_match['team1']])
            team2_names = ", ".join([p['username'] for p in active_match['team2']])
            active_text = f"🔴 **Team 1:** {team1_names}\n🔵 **Team 2:** {team2_names}"
            embed.add_field(name="⚡ Active Match", value=active_text, inline=False)
        else:
            embed.add_field(name="⚡ Active Match", value="None", inline=False)

        # Pending match
        if pending_match:
            team1_names = ", ".join([p['username'] for p in pending_match['team1']])
            team2_names = ", ".join([p['username'] for p in pending_match['team2']])
            pending_text = f"🔴 **Team 1:** {team1_names}\n🔵 **Team 2:** {team2_names}"
            embed.add_field(name="⏳ Upcoming Match", value=pending_text, inline=False)
        else:
            embed.add_field(name="⏳ Upcoming Match", value="None", inline=False)

        # Match history
        if match_history:
            history_text = ""
            for match in match_history[:3]:
                winner = match.get('winning_team', 'N/A')
                team1_score = match.get('team1_score', 0)
                team2_score = match.get('team2_score', 0)
                history_text += f"• Team 1: {team1_score} - Team 2: {team2_score} (Winner: Team {winner})\n"
            embed.add_field(name="📜 Recent Matches", value=history_text or "None", inline=False)

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    """Load the cog"""
    await bot.add_cog(PlayerCommands(bot))
    # Sync slash commands
    await bot.tree.sync()
    print("✅ Player commands loaded")