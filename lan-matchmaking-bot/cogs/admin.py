import discord
from discord.ext import commands
from discord import app_commands
from utils.database import db
import config
from bson import ObjectId


def is_admin():
    """Check if user has admin role"""

    async def predicate(interaction: discord.Interaction):
        admin_role = discord.utils.get(interaction.user.roles, name=config.ADMIN_ROLE_NAME)
        return admin_role is not None

    return app_commands.check(predicate)


class AdminCommands(commands.Cog):
    """Commands for administrators"""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="enablematchmaking", description="[ADMIN] Enable matchmaking")
    @is_admin()
    async def enable_matchmaking(self, interaction: discord.Interaction):
        """Enable matchmaking system"""
        await db.set_system_setting('matchmaking_enabled', True)
        await interaction.response.send_message("✅ Matchmaking has been enabled!")

    @app_commands.command(name="disablematchmaking", description="[ADMIN] Disable matchmaking")
    @is_admin()
    async def disable_matchmaking(self, interaction: discord.Interaction):
        """Disable matchmaking system"""
        await db.set_system_setting('matchmaking_enabled', False)
        await interaction.response.send_message("✅ Matchmaking has been disabled!")

    @app_commands.command(name="setpoints", description="[ADMIN] Set a player's points")
    @app_commands.describe(member="The player", points="New point value")
    @is_admin()
    async def set_points(self, interaction: discord.Interaction, member: discord.Member, points: int):
        """Set player points"""
        player = await db.get_player(member.id)

        if not player:
            await interaction.response.send_message(
                f"❌ {member.name} is not registered!",
                ephemeral=True
            )
            return

        await db.update_player(member.id, {'points': points})
        await interaction.response.send_message(
            f"✅ Set {member.name}'s points to {points}"
        )

    @app_commands.command(name="startmatch", description="[ADMIN] Start the pending match")
    @is_admin()
    async def start_match(self, interaction: discord.Interaction):
        """Start pending match"""
        # Defer immediately - gives us 15 minutes to respond
        await interaction.response.defer()

        pending_match = await db.get_pending_match()

        if not pending_match:
            await interaction.followup.send(
                "❌ No pending match to start!",
                ephemeral=True
            )
            return

        # Update match status
        await db.update_match(
            pending_match['_id'],
            {
                'status': 'active',
                'started_at': discord.utils.utcnow()
            }
        )

        # Set all players to offline
        all_players = pending_match['team1'] + pending_match['team2']
        for player in all_players:
            await db.update_player(player['user_id'], {'status': 'offline'})

        # Create channels
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.create_match_channels(interaction.guild, pending_match)

        # Notify players
        team1_names = ", ".join([p['username'] for p in pending_match['team1']])
        team2_names = ", ".join([p['username'] for p in pending_match['team2']])

        embed = discord.Embed(
            title="🎮 Match Started!",
            description="The match has begun! Good luck!",
            color=discord.Color.green()
        )
        embed.add_field(name="🔴 Team 1", value=team1_names, inline=False)
        embed.add_field(name="🔵 Team 2", value=team2_names, inline=False)

        # Use followup instead of response
        await interaction.followup.send(embed=embed)

        # Notify players via DM
        for player in all_players:
            member = interaction.guild.get_member(player['user_id'])
            if member:
                try:
                    await member.send(embed=embed)
                except:
                    pass

        # Check queue for next match
        if matchmaking_cog:
            await matchmaking_cog.check_and_create_match(interaction.guild)

    @app_commands.command(name="cancelmatch", description="[ADMIN] Cancel the pending match")
    @is_admin()
    async def cancel_match(self, interaction: discord.Interaction):
        """Cancel pending match"""
        pending_match = await db.get_pending_match()

        if not pending_match:
            await interaction.response.send_message(
                "❌ No pending match to cancel!",
                ephemeral=True
            )
            return

        # Update match status
        await db.update_match(pending_match['_id'], {'status': 'cancelled'})

        # Players stay in queue (remain online)

        await interaction.response.send_message("✅ Match has been cancelled.")

        # Check queue again
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.check_and_create_match(interaction.guild)

    @app_commands.command(name="endmatch", description="[ADMIN] End the active match")
    @is_admin()
    async def end_match(self, interaction: discord.Interaction):
        """End active match"""
        active_match = await db.get_active_match()

        if not active_match:
            await interaction.response.send_message(
                "❌ No active match to end!",
                ephemeral=True
            )
            return

        # Update match status
        await db.update_match(
            active_match['_id'],
            {
                'status': 'awaiting_points',
                'ended_at': discord.utils.utcnow()
            }
        )

        # Notify players to submit points
        all_players = active_match['team1'] + active_match['team2']

        embed = discord.Embed(
            title="🏁 Match Ended!",
            description="Please submit your points using `/submitpoints <your_points>`",
            color=discord.Color.blue()
        )

        await interaction.response.send_message(embed=embed)

        for player in all_players:
            member = interaction.guild.get_member(player['user_id'])
            if member:
                try:
                    await member.send(embed=embed)
                except:
                    pass

        # Start points entry timer
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.start_points_entry_timer(
                interaction.guild,
                str(active_match['_id'])
            )

    @app_commands.command(name="verifypoints", description="[ADMIN] Verify and finalize match points")
    @is_admin()
    async def verify_points(self, interaction: discord.Interaction):
        """Verify points for completed match"""
        # Defer immediately
        await interaction.response.defer()

        # Find match awaiting points
        match = await db.db.matches.find_one({'status': 'awaiting_points'})

        if not match:
            await interaction.followup.send(
                "❌ No match awaiting point verification!",
                ephemeral=True
            )
            return

        points_submitted = match.get('points_submitted', {})
        all_players = match['team1'] + match['team2']

        # Check if all players submitted points
        if len(points_submitted) < len(all_players):
            missing = []
            for player in all_players:
                if str(player['user_id']) not in points_submitted:
                    missing.append(player['username'])

            await interaction.followup.send(
                f"⚠️ Not all players have submitted points!\nMissing: {', '.join(missing)}",
                ephemeral=True
            )
            return

        # Calculate team scores
        team1_score = sum(points_submitted.get(str(p['user_id']), 0) for p in match['team1'])
        team2_score = sum(points_submitted.get(str(p['user_id']), 0) for p in match['team2'])

        winning_team = 1 if team1_score > team2_score else 2 if team2_score > team1_score else 0

        # Update player stats and points
        for player in all_players:
            player_points = points_submitted.get(str(player['user_id']), 0)
            player_data = await db.get_player(player['user_id'])

            is_winner = (player in match['team1'] and winning_team == 1) or \
                        (player in match['team2'] and winning_team == 2)

            new_total_points = player_data['points'] + player_points
            new_matches_played = player_data['matches_played'] + 1
            new_wins = player_data['wins'] + (1 if is_winner else 0)
            new_losses = player_data['losses'] + (0 if is_winner or winning_team == 0 else 1)

            await db.update_player(player['user_id'], {
                'points': new_total_points,
                'matches_played': new_matches_played,
                'wins': new_wins,
                'losses': new_losses
            })

        # Update match
        await db.update_match(match['_id'], {
            'status': 'completed',
            'team1_score': team1_score,
            'team2_score': team2_score,
            'winning_team': winning_team,
            'points_verified': True,
            'verified_at': discord.utils.utcnow()
        })

        # Delete channels
        matchmaking_cog = self.bot.get_cog('MatchmakingCommands')
        if matchmaking_cog:
            await matchmaking_cog.delete_match_channels(str(match['_id']))

        # Announce results
        embed = discord.Embed(
            title="🏆 Match Complete!",
            color=discord.Color.gold()
        )

        team1_names = ", ".join([p['username'] for p in match['team1']])
        team2_names = ", ".join([p['username'] for p in match['team2']])

        embed.add_field(name="🔴 Team 1", value=f"{team1_names}\nScore: {team1_score}", inline=False)
        embed.add_field(name="🔵 Team 2", value=f"{team2_names}\nScore: {team2_score}", inline=False)

        if winning_team == 0:
            embed.add_field(name="Result", value="🤝 It's a tie!", inline=False)
        else:
            embed.add_field(name="Winner", value=f"🎉 Team {winning_team} wins!", inline=False)

        # Use followup instead of response
        await interaction.followup.send(embed=embed)

        # Check queue for next match
        if matchmaking_cog:
            await matchmaking_cog.check_and_create_match(interaction.guild)

    @app_commands.command(name="custommatch", description="[ADMIN] Create a custom match")
    @app_commands.describe(
        p1="Player 1", p2="Player 2", p3="Player 3",
        p4="Player 4", p5="Player 5", p6="Player 6"
    )
    @is_admin()
    async def custom_match(
            self,
            interaction: discord.Interaction,
            p1: discord.Member, p2: discord.Member, p3: discord.Member,
            p4: discord.Member, p5: discord.Member, p6: discord.Member
    ):
        """Create a custom match with specific players"""
        # Defer if this might take time
        await interaction.response.defer()

        players_input = [p1, p2, p3, p4, p5, p6]

        # Get player data
        players = []
        for member in players_input:
            player = await db.get_player(member.id)
            if not player:
                await interaction.followup.send(
                    f"❌ {member.name} is not registered!",
                    ephemeral=True
                )
                return
            players.append(player)

        # Manual team assignment (first 3 in team 1, next 3 in team 2)
        team1 = players[:3]
        team2 = players[3:]

        # Create match
        match_data = {
            'team1': team1,
            'team2': team2,
            'imbalance': abs(sum(p['skill_level'] for p in team1) - sum(p['skill_level'] for p in team2)),
            'status': 'pending',
            'points_submitted': {},
            'points_verified': False,
            'custom_match': True
        }

        match = await db.create_match(match_data)

        # Notify
        team1_names = ", ".join([p['username'] for p in team1])
        team2_names = ", ".join([p['username'] for p in team2])

        embed = discord.Embed(
            title="🎮 Custom Match Created!",
            color=discord.Color.purple()
        )
        embed.add_field(name="🔴 Team 1", value=team1_names, inline=False)
        embed.add_field(name="🔵 Team 2", value=team2_names, inline=False)
        embed.set_footer(text="Use /startmatch to begin")

        await interaction.followup.send(embed=embed)

    @app_commands.command(name="resetplayer", description="[ADMIN] Reset a player's stats")
    @app_commands.describe(member="The player to reset")
    @is_admin()
    async def reset_player(self, interaction: discord.Interaction, member: discord.Member):
        """Reset player stats"""
        player = await db.get_player(member.id)

        if not player:
            await interaction.response.send_message(
                f"❌ {member.name} is not registered!",
                ephemeral=True
            )
            return

        await db.update_player(member.id, {
            'points': 0,
            'matches_played': 0,
            'wins': 0,
            'losses': 0,
            'status': 'offline'
        })

        await interaction.response.send_message(
            f"✅ Reset stats for {member.name}"
        )

    @app_commands.command(name="listplayers", description="[ADMIN] List all registered players")
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

        # Split into chunks if too many players
        description = ""
        for player in players[:25]:  # Discord embed field limit
            status_emoji = "🟢" if player['status'] == 'online' else "⚪"
            description += f"{status_emoji} **{player['username']}** - Skill: {player['skill_level']}/10, Points: {player['points']}\n"

        if len(players) > 25:
            description += f"\n_...and {len(players) - 25} more_"

        embed.description = description
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="checkadmin", description="Check if you have admin access")
    async def check_admin(self, interaction: discord.Interaction):
        """Check admin status"""
        admin_role = discord.utils.get(interaction.user.roles, name=config.ADMIN_ROLE_NAME)

        if admin_role:
            await interaction.response.send_message(
                f"✅ You have the '{config.ADMIN_ROLE_NAME}' role!",
                ephemeral=True
            )
        else:
            roles = [role.name for role in interaction.user.roles if role.name != "@everyone"]
            await interaction.response.send_message(
                f"❌ You don't have the '{config.ADMIN_ROLE_NAME}' role.\n"
                f"Your roles: {', '.join(roles) if roles else 'None'}",
                ephemeral=True
            )

async def setup(bot):
    """Load the cog"""
    await bot.add_cog(AdminCommands(bot))
    print("✅ Admin commands loaded")