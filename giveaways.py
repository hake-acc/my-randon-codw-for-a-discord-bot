import discord
from discord.ext import commands
import sqlite3
import random
import asyncio
from datetime import datetime, timedelta
from cogs.premium import is_premium_user, is_premium_guild

DATABASE_FILE = "bot_database.db"

COLORS = {
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500,
    'info': 0x0099FF,
    'giveaway': 0xFF69B4
}

def create_embed(title, description, color=COLORS['info']):
    """Create a consistent embed"""
    embed = discord.Embed(title=title, description=description, color=color)
    embed.timestamp = datetime.now()
    return embed

def create_success_embed(title, description, user=None):
    """Create a success embed"""
    embed = create_embed(title, description, COLORS['success'])
    if user:
        embed.set_footer(text=f"Requested by {user.display_name}", icon_url=user.display_avatar.url)
    return embed

def create_error_embed(title, description):
    """Create an error embed"""
    return create_embed(title, description, COLORS['error'])

class GiveawaySystem(commands.Cog):
    """Complete giveaway system with requirements and interactive setup"""
    
    def __init__(self, bot):
        self.bot = bot
        self.init_giveaway_database()
        self.active_giveaways = {}
    
    def init_giveaway_database(self):
        """Initialize giveaway database tables"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Giveaways table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    host_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    prize TEXT NOT NULL,
                    winners INTEGER DEFAULT 1,
                    ends_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    requirements TEXT,
                    entries TEXT DEFAULT '[]',
                    ended BOOLEAN DEFAULT 0,
                    winner_ids TEXT
                )
            ''')
            
            # Giveaway entries
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS giveaway_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    giveaway_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    entered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(giveaway_id, user_id)
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Giveaway system database initialized")
            
        except Exception as e:
            print(f"❌ Giveaway database initialization failed: {e}")
    
    @discord.app_commands.command(name="giveaway", description="🎉 Create and manage giveaways")
    @discord.app_commands.describe(action="What would you like to do?")
    @discord.app_commands.choices(action=[
        discord.app_commands.Choice(name="🎉 Create Giveaway", value="create"),
        discord.app_commands.Choice(name="📊 List Active", value="list"),
        discord.app_commands.Choice(name="🏁 End Early", value="end"),
        discord.app_commands.Choice(name="🔄 Reroll", value="reroll")
    ])
    async def giveaway(self, interaction: discord.Interaction, action: discord.app_commands.Choice[str]):
        """Main giveaway command"""
        
        if action.value == "create":
            await self.show_giveaway_setup(interaction)
        elif action.value == "list":
            await self.show_active_giveaways(interaction)
        elif action.value == "end":
            await self.show_end_giveaway_interface(interaction)
        elif action.value == "reroll":
            await self.show_reroll_interface(interaction)
    
    async def show_giveaway_setup(self, interaction: discord.Interaction):
        """Show interactive giveaway setup"""
        if not interaction.user.guild_permissions.manage_guild:
            embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to create giveaways.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Check premium limits
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM giveaways WHERE guild_id = ? AND ended = 0', (interaction.guild.id,))
            active_count = cursor.fetchone()[0]
            conn.close()
            
            max_giveaways = 10 if (is_premium_user(interaction.user.id) or is_premium_guild(interaction.guild.id)) else 3
            
            if active_count >= max_giveaways:
                embed = create_error_embed(
                    "Giveaway Limit Reached",
                    f"You can have maximum **{max_giveaways}** active giveaways.\n{'Upgrade to premium for more!' if max_giveaways == 3 else ''}"
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
                
        except:
            pass
        
        embed = create_embed(
            title="🎉 Giveaway Setup",
            description="**Create an interactive giveaway with requirements and preview**",
            color=COLORS['giveaway']
        )
        
        embed.add_field(
            name="🎯 Setup Steps",
            value="• **🎁 Prize & Details** - Set title, prize, and duration\n• **📋 Requirements** - Set entry requirements\n• **🔄 Preview** - See how it will look\n• **✅ Launch** - Start the giveaway",
            inline=False
        )
        
        embed.add_field(
            name="✨ Features",
            value="• **🎲 Random Winner Selection**\n• **📊 Real-time Entry Tracking**\n• **⚙️ Custom Requirements**\n• **🔄 Auto-End with Results**",
            inline=False
        )
        
        view = GiveawaySetupView(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view)
    
    async def show_active_giveaways(self, interaction: discord.Interaction):
        """Show active giveaways"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, prize, ends_at, winners, channel_id 
                FROM giveaways WHERE guild_id = ? AND ended = 0
                ORDER BY ends_at ASC
            ''', (interaction.guild.id,))
            giveaways = cursor.fetchall()
            conn.close()
            
            if not giveaways:
                embed = create_embed(
                    title="🎉 Active Giveaways",
                    description="**No active giveaways**\n\nUse `/giveaway create` to start one!",
                    color=COLORS['warning']
                )
            else:
                embed = create_embed(
                    title="🎉 Active Giveaways",
                    description=f"**{len(giveaways)} active giveaway{'s' if len(giveaways) != 1 else ''}**",
                    color=COLORS['giveaway']
                )
                
                for gw_id, title, prize, ends_at, winners, channel_id in giveaways[:10]:
                    channel = interaction.guild.get_channel(channel_id)
                    channel_name = channel.name if channel else "Unknown"
                    
                    ends_dt = datetime.fromisoformat(ends_at)
                    time_left = ends_dt - datetime.now()
                    
                    if time_left.total_seconds() > 0:
                        days = time_left.days
                        hours, remainder = divmod(time_left.seconds, 3600)
                        minutes = remainder // 60
                        time_str = f"{days}d {hours}h {minutes}m" if days > 0 else f"{hours}h {minutes}m"
                    else:
                        time_str = "Ending soon..."
                    
                    embed.add_field(
                        name=f"🎁 {title}",
                        value=f"**Prize:** {prize}\n**Winners:** {winners}\n**Channel:** #{channel_name}\n**Ends in:** {time_str}",
                        inline=True
                    )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Error", f"Could not load giveaways: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class GiveawaySetupView(discord.ui.View):
    """Interactive giveaway setup interface"""
    
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.config = {
            'title': None,
            'prize': None,
            'duration': None,
            'winners': 1,
            'requirements': {},
            'channel': None
        }
    
    @discord.ui.button(label="🎁 Set Prize & Details", style=discord.ButtonStyle.primary, emoji="🎁")
    async def set_prize(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        modal = GiveawayDetailsModal(self.config)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="📋 Set Requirements", style=discord.ButtonStyle.secondary, emoji="📋")
    async def set_requirements(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        view = GiveawayRequirementsView(self.user_id, self.config)
        embed = create_embed(
            title="📋 Giveaway Requirements",
            description="**Set entry requirements for your giveaway**",
            color=COLORS['info']
        )
        
        embed.add_field(
            name="⚙️ Available Requirements",
            value="• **🎭 Required Role** - Must have specific role\n• **📝 Message Count** - Minimum messages in server\n• **⏰ Server Age** - How long they've been in server\n• **📊 Level Requirement** - Minimum level needed",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="🔄 Preview Giveaway", style=discord.ButtonStyle.success, emoji="🔄")
    async def preview_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        if not all([self.config['title'], self.config['prize'], self.config['duration']]):
            embed = create_error_embed("Missing Details", "Please set prize & details first!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Create preview embed
        embed = await self.create_giveaway_embed(preview=True)
        await interaction.response.send_message(content="🔄 **Giveaway Preview:**", embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🚀 Launch Giveaway", style=discord.ButtonStyle.danger, emoji="🚀")
    async def launch_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        if not all([self.config['title'], self.config['prize'], self.config['duration']]):
            embed = create_error_embed("Missing Configuration", "Please complete the giveaway setup first!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Launch the giveaway
        await self.create_giveaway(interaction)
    
    async def create_giveaway_embed(self, preview=False):
        """Create the giveaway embed"""
        title = f"🎉 {self.config['title']}" if not preview else f"🔄 PREVIEW: {self.config['title']}"
        
        embed = create_embed(
            title=title,
            description=f"**Prize:** {self.config['prize']}\n**Winners:** {self.config['winners']}\n**Duration:** {self.config['duration']}",
            color=COLORS['warning'] if preview else COLORS['giveaway']
        )
        
        if self.config['requirements']:
            req_text = []
            for req_type, req_value in self.config['requirements'].items():
                if req_type == 'role':
                    req_text.append(f"• Must have role: <@&{req_value}>")
                elif req_type == 'messages':
                    req_text.append(f"• Minimum {req_value} messages")
                elif req_type == 'server_age':
                    req_text.append(f"• Must be in server for {req_value} days")
                elif req_type == 'level':
                    req_text.append(f"• Minimum level {req_value}")
            
            if req_text:
                embed.add_field(
                    name="📋 Requirements",
                    value="\n".join(req_text),
                    inline=False
                )
        
        if not preview:
            embed.add_field(
                name="🎯 How to Enter",
                value="React with 🎉 to enter this giveaway!",
                inline=False
            )
            
            embed.set_footer(text="Good luck to all participants!")
        else:
            embed.set_footer(text="This is a preview - giveaway not yet created")
        
        return embed
    
    async def create_giveaway(self, interaction: discord.Interaction):
        """Create and start the giveaway"""
        try:
            # Create giveaway embed
            embed = await self.create_giveaway_embed()
            
            # Send giveaway message
            channel = interaction.channel
            giveaway_msg = await channel.send(embed=embed)
            await giveaway_msg.add_reaction("🎉")
            
            # Calculate end time
            duration_parts = self.config['duration'].split()
            total_seconds = 0
            
            for part in duration_parts:
                if part.endswith('d'):
                    total_seconds += int(part[:-1]) * 86400
                elif part.endswith('h'):
                    total_seconds += int(part[:-1]) * 3600
                elif part.endswith('m'):
                    total_seconds += int(part[:-1]) * 60
            
            ends_at = datetime.now() + timedelta(seconds=total_seconds)
            
            # Save to database
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO giveaways (guild_id, channel_id, message_id, host_id, title, prize, 
                                     winners, ends_at, requirements)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                interaction.guild.id, channel.id, giveaway_msg.id, interaction.user.id,
                self.config['title'], self.config['prize'], self.config['winners'],
                ends_at.isoformat(), str(self.config['requirements'])
            ))
            
            giveaway_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            # Schedule giveaway end
            asyncio.create_task(self.schedule_giveaway_end(giveaway_id, total_seconds))
            
            embed = create_success_embed(
                "🎉 Giveaway Created!",
                f"**{self.config['title']}** giveaway has been started!\n\nUsers can now react with 🎉 to enter.",
                interaction.user
            )
            
            embed.add_field(
                name="📊 Details",
                value=f"Prize: **{self.config['prize']}**\nWinners: **{self.config['winners']}**\nEnds: **{ends_at.strftime('%Y-%m-%d %H:%M UTC')}**",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = create_error_embed("Creation Failed", f"Could not create giveaway: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def schedule_giveaway_end(self, giveaway_id: int, duration: int):
        """Schedule giveaway to end"""
        await asyncio.sleep(duration)
        await self.end_giveaway(giveaway_id)
    
    async def end_giveaway(self, giveaway_id: int):
        """End giveaway and pick winners"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Get giveaway data
            cursor.execute('''
                SELECT guild_id, channel_id, message_id, title, prize, winners, host_id
                FROM giveaways WHERE id = ? AND ended = 0
            ''', (giveaway_id,))
            giveaway_data = cursor.fetchone()
            
            if not giveaway_data:
                conn.close()
                return
            
            guild_id, channel_id, message_id, title, prize, winners, host_id = giveaway_data
            
            # Get entries
            cursor.execute('SELECT user_id FROM giveaway_entries WHERE giveaway_id = ?', (giveaway_id,))
            entries = [row[0] for row in cursor.fetchall()]
            
            # Pick winners
            if len(entries) < winners:
                winner_ids = entries
            else:
                winner_ids = random.sample(entries, winners)
            
            # Update giveaway as ended
            cursor.execute('''
                UPDATE giveaways SET ended = 1, winner_ids = ? WHERE id = ?
            ''', (str(winner_ids), giveaway_id))
            
            conn.commit()
            conn.close()
            
            # Get guild and channel
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            
            channel = guild.get_channel(channel_id)
            if not channel:
                return
            
            # Create results embed
            if winner_ids:
                winners_text = "\n".join([f"🎉 <@{user_id}>" for user_id in winner_ids])
                embed = create_success_embed(
                    f"🎉 {title} - ENDED",
                    f"**Prize:** {prize}\n\n**🏆 Winner{'s' if len(winner_ids) != 1 else ''}:**\n{winners_text}",
                )
                
                embed.add_field(
                    name="📊 Statistics",
                    value=f"Total Entries: **{len(entries)}**\nWinners Selected: **{len(winner_ids)}**",
                    inline=False
                )
            else:
                embed = create_embed(
                    title=f"🎉 {title} - ENDED",
                    description=f"**Prize:** {prize}\n\n❌ **No valid entries** - Giveaway cancelled",
                    color=COLORS['error']
                )
            
            # Try to edit original message
            try:
                message = await channel.fetch_message(message_id)
                await message.edit(embed=embed)
            except:
                await channel.send(embed=embed)
                
        except Exception as e:
            print(f"Error ending giveaway: {e}")
    
    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        """Handle giveaway entries"""
        if user.bot or str(reaction.emoji) != "🎉":
            return
        
        try:
            # Check if this is a giveaway message
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, requirements FROM giveaways 
                WHERE message_id = ? AND ended = 0
            ''', (reaction.message.id,))
            giveaway_data = cursor.fetchone()
            
            if not giveaway_data:
                conn.close()
                return
            
            giveaway_id, requirements_str = giveaway_data
            
            # Check requirements
            if requirements_str:
                requirements = eval(requirements_str)  # In production, use json.loads
                
                # Validate requirements
                if not await self.check_requirements(user, reaction.message.guild, requirements):
                    # Send DM about requirements not met
                    try:
                        req_embed = create_error_embed(
                            "Entry Requirements Not Met",
                            "You don't meet the requirements for this giveaway."
                        )
                        await user.send(embed=req_embed)
                    except:
                        pass
                    await reaction.remove(user)
                    conn.close()
                    return
            
            # Add entry
            cursor.execute('''
                INSERT OR IGNORE INTO giveaway_entries (giveaway_id, user_id)
                VALUES (?, ?)
            ''', (giveaway_id, user.id))
            
            conn.commit()
            conn.close()
            
        except Exception as e:
            print(f"Error handling giveaway entry: {e}")
    
    async def check_requirements(self, user, guild, requirements):
        """Check if user meets giveaway requirements"""
        try:
            member = guild.get_member(user.id)
            if not member:
                return False
            
            # Check role requirement
            if 'role' in requirements:
                required_role_id = requirements['role']
                if not any(role.id == required_role_id for role in member.roles):
                    return False
            
            # Check message count requirement
            if 'messages' in requirements:
                # This would need to check against leveling system
                pass
            
            # Check server age requirement
            if 'server_age' in requirements:
                days_required = requirements['server_age']
                if (datetime.now() - member.joined_at).days < days_required:
                    return False
            
            # Check level requirement
            if 'level' in requirements:
                # This would need to check against leveling system
                pass
            
            return True
            
        except Exception as e:
            print(f"Error checking requirements: {e}")
            return False

class GiveawayDetailsModal(discord.ui.Modal):
    """Modal for giveaway details"""
    
    def __init__(self, config):
        super().__init__(title="🎁 Giveaway Details")
        self.config = config
        
        self.title_input = discord.ui.TextInput(
            label="Giveaway Title",
            placeholder="Amazing Prize Giveaway!",
            max_length=100,
            required=True
        )
        
        self.prize_input = discord.ui.TextInput(
            label="Prize Description",
            placeholder="Discord Nitro, $50 Gift Card, etc.",
            max_length=200,
            required=True
        )
        
        self.duration_input = discord.ui.TextInput(
            label="Duration",
            placeholder="1d 12h 30m (or combinations like 2d, 5h, 30m)",
            max_length=50,
            required=True
        )
        
        self.winners_input = discord.ui.TextInput(
            label="Number of Winners",
            placeholder="1",
            max_length=2,
            required=True,
            default="1"
        )
        
        self.add_item(self.title_input)
        self.add_item(self.prize_input)
        self.add_item(self.duration_input)
        self.add_item(self.winners_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.config['title'] = self.title_input.value
            self.config['prize'] = self.prize_input.value
            self.config['duration'] = self.duration_input.value
            self.config['winners'] = int(self.winners_input.value)
            
            embed = create_success_embed(
                "✅ Giveaway Details Set",
                f"**Title:** {self.config['title']}\n**Prize:** {self.config['prize']}\n**Duration:** {self.config['duration']}\n**Winners:** {self.config['winners']}",
                interaction.user
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            embed = create_error_embed("Invalid Input", "Number of winners must be a valid number!")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class GiveawayRequirementsView(discord.ui.View):
    """View for setting giveaway requirements"""
    
    def __init__(self, user_id: int, config):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.config = config
    
    @discord.ui.button(label="🎭 Role Requirement", style=discord.ButtonStyle.secondary)
    async def role_requirement(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        # Show role selection
        from cogs.leveling import RoleSelectView  # Import here to avoid circular imports
        view = RoleSelectView(self.user_id, self.config['requirements'], 'role', interaction.guild)
        await interaction.response.send_message("🎭 **Select Required Role**", view=view, ephemeral=True)
    
    @discord.ui.button(label="📝 Message Count", style=discord.ButtonStyle.secondary)
    async def message_requirement(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        modal = MessageRequirementModal(self.config)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="⏰ Server Age", style=discord.ButtonStyle.secondary)
    async def age_requirement(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        modal = ServerAgeModal(self.config)
        await interaction.response.send_modal(modal)

class MessageRequirementModal(discord.ui.Modal):
    """Modal for message count requirement"""
    
    def __init__(self, config):
        super().__init__(title="📝 Message Requirement")
        self.config = config
        
        self.messages_input = discord.ui.TextInput(
            label="Minimum Messages",
            placeholder="Minimum number of messages required (e.g., 50, 100)",
            max_length=10,
            required=True
        )
        self.add_item(self.messages_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            min_messages = int(self.messages_input.value)
            self.config['requirements']['messages'] = min_messages
            
            embed = create_success_embed(
                "✅ Message Requirement Set",
                f"Users need **{min_messages}** messages to enter",
                interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            embed = create_error_embed("Invalid Input", "Please enter a valid number!")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class ServerAgeModal(discord.ui.Modal):
    """Modal for server age requirement"""
    
    def __init__(self, config):
        super().__init__(title="⏰ Server Age Requirement")
        self.config = config
        
        self.days_input = discord.ui.TextInput(
            label="Minimum Days in Server",
            placeholder="How many days user must be in server (e.g., 7, 14, 30)",
            max_length=10,
            required=True
        )
        self.add_item(self.days_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            min_days = int(self.days_input.value)
            self.config['requirements']['server_age'] = min_days
            
            embed = create_success_embed(
                "✅ Server Age Requirement Set",
                f"Users need to be in server for **{min_days} days** to enter",
                interaction.user
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            embed = create_error_embed("Invalid Input", "Please enter a valid number of days!")
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(GiveawaySystem(bot))