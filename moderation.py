import discord
from discord.ext import commands
import sqlite3
import asyncio
from datetime import datetime, timedelta
from cogs.premium import is_premium_user, is_premium_guild, require_premium

DATABASE_FILE = "bot_database.db"

COLORS = {
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500,
    'info': 0x0099FF,
    'mod': 0xFF4500
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

class ModerationSystem(commands.Cog):
    """Complete moderation system with automod and advanced features"""
    
    def __init__(self, bot):
        self.bot = bot
        self.init_moderation_database()
        self.automod_filters = {}
    
    def init_moderation_database(self):
        """Initialize moderation database tables"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Moderation logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS mod_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT,
                    duration INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # AutoMod settings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS automod_settings (
                    guild_id INTEGER PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 1,
                    spam_filter BOOLEAN DEFAULT 1,
                    link_filter BOOLEAN DEFAULT 0,
                    invite_filter BOOLEAN DEFAULT 1,
                    mention_filter BOOLEAN DEFAULT 1,
                    caps_filter BOOLEAN DEFAULT 0,
                    bad_words TEXT DEFAULT '[]',
                    whitelist_channels TEXT DEFAULT '[]',
                    whitelist_roles TEXT DEFAULT '[]',
                    log_channel INTEGER,
                    punishment TEXT DEFAULT 'warn'
                )
            ''')
            
            # User warnings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_warnings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    moderator_id INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Temporary punishments
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS temp_punishments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    punishment_type TEXT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    moderator_id INTEGER,
                    reason TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Moderation system database initialized")
            
        except Exception as e:
            print(f"❌ Moderation database initialization failed: {e}")
    
    @discord.app_commands.command(name="ban", description="🔨 Ban a user from the server")
    @discord.app_commands.describe(
        user="User to ban",
        reason="Reason for ban",
        delete_days="Days of messages to delete (0-7)"
    )
    async def ban(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided", delete_days: int = 1):
        """Ban a user"""
        if not interaction.user.guild_permissions.ban_members:
            embed = create_error_embed("Permission Denied", "You need `Ban Members` permission to use this command.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if user.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            embed = create_error_embed("Insufficient Permissions", "You cannot ban users with equal or higher roles.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Log to database
            self.log_moderation_action(interaction.guild.id, user.id, interaction.user.id, "ban", reason)
            
            # Ban user
            await user.ban(reason=f"{reason} - By {interaction.user}", delete_message_days=min(7, max(0, delete_days)))
            
            embed = create_success_embed(
                "🔨 User Banned",
                f"**{user.mention}** has been banned",
                interaction.user
            )
            
            embed.add_field(name="📝 Reason", value=reason, inline=False)
            embed.add_field(name="🗑️ Messages Deleted", value=f"{delete_days} day{'s' if delete_days != 1 else ''}", inline=True)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Ban Failed", f"Could not ban user: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="kick", description="👢 Kick a user from the server")
    @discord.app_commands.describe(user="User to kick", reason="Reason for kick")
    async def kick(self, interaction: discord.Interaction, user: discord.Member, reason: str = "No reason provided"):
        """Kick a user"""
        if not interaction.user.guild_permissions.kick_members:
            embed = create_error_embed("Permission Denied", "You need `Kick Members` permission to use this command.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if user.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
            embed = create_error_embed("Insufficient Permissions", "You cannot kick users with equal or higher roles.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Log to database
            self.log_moderation_action(interaction.guild.id, user.id, interaction.user.id, "kick", reason)
            
            # Kick user
            await user.kick(reason=f"{reason} - By {interaction.user}")
            
            embed = create_success_embed(
                "👢 User Kicked",
                f"**{user.mention}** has been kicked",
                interaction.user
            )
            
            embed.add_field(name="📝 Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Kick Failed", f"Could not kick user: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="timeout", description="⏰ Timeout a user")
    @discord.app_commands.describe(
        user="User to timeout",
        duration="Duration (e.g., 10m, 1h, 2d)",
        reason="Reason for timeout"
    )
    async def timeout(self, interaction: discord.Interaction, user: discord.Member, duration: str, reason: str = "No reason provided"):
        """Timeout a user"""
        if not interaction.user.guild_permissions.moderate_members:
            embed = create_error_embed("Permission Denied", "You need `Timeout Members` permission to use this command.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Parse duration
            total_seconds = 0
            duration_parts = duration.lower().split()
            
            for part in duration_parts:
                if part.endswith('d'):
                    total_seconds += int(part[:-1]) * 86400
                elif part.endswith('h'):
                    total_seconds += int(part[:-1]) * 3600
                elif part.endswith('m'):
                    total_seconds += int(part[:-1]) * 60
                elif part.endswith('s'):
                    total_seconds += int(part[:-1])
            
            if total_seconds <= 0 or total_seconds > 2419200:  # Max 28 days
                embed = create_error_embed("Invalid Duration", "Duration must be between 1 second and 28 days!")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            timeout_until = datetime.now() + timedelta(seconds=total_seconds)
            
            # Apply timeout
            await user.timeout(timeout_until, reason=f"{reason} - By {interaction.user}")
            
            # Log to database
            self.log_moderation_action(interaction.guild.id, user.id, interaction.user.id, "timeout", reason, total_seconds)
            
            embed = create_success_embed(
                "⏰ User Timed Out",
                f"**{user.mention}** has been timed out",
                interaction.user
            )
            
            embed.add_field(name="📝 Reason", value=reason, inline=False)
            embed.add_field(name="⏰ Duration", value=duration, inline=True)
            embed.add_field(name="🕐 Until", value=f"<t:{int(timeout_until.timestamp())}:F>", inline=True)
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            embed = create_error_embed("Invalid Duration", "Please use format like: 10m, 1h, 2d")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed("Timeout Failed", f"Could not timeout user: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="warn", description="⚠️ Warn a user")
    @discord.app_commands.describe(user="User to warn", reason="Reason for warning")
    async def warn(self, interaction: discord.Interaction, user: discord.Member, reason: str):
        """Warn a user"""
        if not interaction.user.guild_permissions.manage_messages:
            embed = create_error_embed("Permission Denied", "You need `Manage Messages` permission to warn users.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            # Add warning to database
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_warnings (user_id, guild_id, moderator_id, reason)
                VALUES (?, ?, ?, ?)
            ''', (user.id, interaction.guild.id, interaction.user.id, reason))
            
            # Get warning count
            cursor.execute('SELECT COUNT(*) FROM user_warnings WHERE user_id = ? AND guild_id = ? AND active = 1', (user.id, interaction.guild.id))
            warning_count = cursor.fetchone()[0]
            
            conn.commit()
            conn.close()
            
            # Log moderation action
            self.log_moderation_action(interaction.guild.id, user.id, interaction.user.id, "warn", reason)
            
            embed = create_success_embed(
                "⚠️ User Warned",
                f"**{user.mention}** has been warned",
                interaction.user
            )
            
            embed.add_field(name="📝 Reason", value=reason, inline=False)
            embed.add_field(name="📊 Total Warnings", value=f"**{warning_count}** warning{'s' if warning_count != 1 else ''}", inline=True)
            
            await interaction.response.send_message(embed=embed)
            
            # Send DM to user
            try:
                dm_embed = create_embed(
                    title="⚠️ Warning Received",
                    description=f"You have been warned in **{interaction.guild.name}**",
                    color=COLORS['warning']
                )
                dm_embed.add_field(name="📝 Reason", value=reason, inline=False)
                dm_embed.add_field(name="👮 Moderator", value=interaction.user.mention, inline=True)
                await user.send(embed=dm_embed)
            except:
                pass
            
        except Exception as e:
            embed = create_error_embed("Warning Failed", f"Could not warn user: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="purge", description="🗑️ Delete multiple messages")
    @discord.app_commands.describe(
        amount="Number of messages to delete (1-100)",
        user="Only delete messages from this user"
    )
    async def purge(self, interaction: discord.Interaction, amount: int, user: discord.Member = None):
        """Purge messages"""
        if not interaction.user.guild_permissions.manage_messages:
            embed = create_error_embed("Permission Denied", "You need `Manage Messages` permission to purge messages.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if amount < 1 or amount > 100:
            embed = create_error_embed("Invalid Amount", "You can only delete between 1 and 100 messages!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            if user:
                # Delete messages from specific user
                deleted = []
                async for message in interaction.channel.history(limit=200):
                    if len(deleted) >= amount:
                        break
                    if message.author == user:
                        deleted.append(message)
                
                await interaction.channel.delete_messages(deleted)
                count = len(deleted)
            else:
                # Delete recent messages
                deleted = await interaction.channel.purge(limit=amount)
                count = len(deleted)
            
            embed = create_success_embed(
                "🗑️ Messages Purged",
                f"Deleted **{count}** message{'s' if count != 1 else ''}",
                interaction.user
            )
            
            if user:
                embed.add_field(name="👤 Target User", value=user.mention, inline=True)
            
            await interaction.followup.send(embed=embed, delete_after=10)
            
        except Exception as e:
            embed = create_error_embed("Purge Failed", f"Could not delete messages: {str(e)}")
            await interaction.followup.send(embed=embed)
    
    @discord.app_commands.command(name="lock", description="🔒 Lock a channel")
    @discord.app_commands.describe(channel="Channel to lock", reason="Reason for locking")
    async def lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided"):
        """Lock a channel"""
        if not interaction.user.guild_permissions.manage_channels:
            embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to lock channels.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        target_channel = channel or interaction.channel
        
        try:
            # Remove send message permission for @everyone
            overwrite = target_channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = False
            await target_channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Locked by {interaction.user}: {reason}")
            
            embed = create_success_embed(
                "🔒 Channel Locked",
                f"**{target_channel.mention}** has been locked",
                interaction.user
            )
            
            embed.add_field(name="📝 Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Lock Failed", f"Could not lock channel: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="unlock", description="🔓 Unlock a channel")
    @discord.app_commands.describe(channel="Channel to unlock", reason="Reason for unlocking")
    async def unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None, reason: str = "No reason provided"):
        """Unlock a channel"""
        if not interaction.user.guild_permissions.manage_channels:
            embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to unlock channels.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        target_channel = channel or interaction.channel
        
        try:
            # Restore send message permission for @everyone
            overwrite = target_channel.overwrites_for(interaction.guild.default_role)
            overwrite.send_messages = None
            await target_channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Unlocked by {interaction.user}: {reason}")
            
            embed = create_success_embed(
                "🔓 Channel Unlocked",
                f"**{target_channel.mention}** has been unlocked",
                interaction.user
            )
            
            embed.add_field(name="📝 Reason", value=reason, inline=False)
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Unlock Failed", f"Could not unlock channel: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="slowmode", description="🐌 Set channel slowmode")
    @discord.app_commands.describe(
        seconds="Slowmode delay in seconds (0 to disable)",
        channel="Channel to set slowmode for"
    )
    async def slowmode(self, interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
        """Set channel slowmode"""
        if not interaction.user.guild_permissions.manage_channels:
            embed = create_error_embed("Permission Denied", "You need `Manage Channels` permission to set slowmode.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        target_channel = channel or interaction.channel
        
        if seconds < 0 or seconds > 21600:  # Max 6 hours
            embed = create_error_embed("Invalid Duration", "Slowmode must be between 0 and 21600 seconds (6 hours)!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        try:
            await target_channel.edit(slowmode_delay=seconds)
            
            if seconds == 0:
                embed = create_success_embed(
                    "🚀 Slowmode Disabled",
                    f"Slowmode disabled in **{target_channel.mention}**",
                    interaction.user
                )
            else:
                embed = create_success_embed(
                    "🐌 Slowmode Set",
                    f"Slowmode set to **{seconds} seconds** in **{target_channel.mention}**",
                    interaction.user
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Slowmode Failed", f"Could not set slowmode: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="automod_setup", description="🛡️ Setup automated moderation")
    async def automod_setup(self, interaction: discord.Interaction):
        """Setup automod with interactive interface"""
        if not interaction.user.guild_permissions.manage_guild:
            embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to setup AutoMod.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        embed = create_embed(
            title="🛡️ AutoMod Setup",
            description="**Configure automated moderation for your server**",
            color=COLORS['mod']
        )
        
        embed.add_field(
            name="⚙️ Available Filters",
            value="• **Spam Filter** - Detect repetitive messages\n• **Link Filter** - Block unauthorized links\n• **Invite Filter** - Block Discord invites\n• **Mention Filter** - Limit mass mentions\n• **Caps Filter** - Limit excessive caps",
            inline=False
        )
        
        embed.add_field(
            name="🎯 Punishment Options",
            value="• **Warn** - Give warning points\n• **Mute** - Temporary timeout\n• **Kick** - Remove from server\n• **Ban** - Permanent removal",
            inline=False
        )
        
        view = AutoModSetupView(interaction.user.id, interaction.guild.id)
        await interaction.response.send_message(embed=embed, view=view)
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """AutoMod message filtering"""
        if message.author.bot or not message.guild:
            return
        
        # Check if automod is enabled for this guild
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM automod_settings WHERE guild_id = ?', (message.guild.id,))
            settings = cursor.fetchone()
            conn.close()
            
            if not settings or not settings[1]:  # enabled column
                return
            
            # Apply filters
            await self.apply_automod_filters(message, settings)
            
        except Exception as e:
            print(f"AutoMod error: {e}")
    
    async def apply_automod_filters(self, message, settings):
        """Apply automod filters to message"""
        try:
            violations = []
            
            # Spam filter (repeated characters)
            if settings[2]:  # spam_filter
                if len(set(message.content.lower())) < len(message.content) / 3 and len(message.content) > 10:
                    violations.append("spam")
            
            # Link filter
            if settings[3]:  # link_filter
                if any(word in message.content.lower() for word in ['http://', 'https://', 'www.']):
                    violations.append("link")
            
            # Invite filter
            if settings[4]:  # invite_filter
                if 'discord.gg/' in message.content.lower() or 'discord.com/invite/' in message.content.lower():
                    violations.append("invite")
            
            # Mention filter
            if settings[5]:  # mention_filter
                if len(message.mentions) > 5:
                    violations.append("mentions")
            
            # Caps filter
            if settings[6]:  # caps_filter
                if len(message.content) > 10:
                    caps_ratio = sum(1 for c in message.content if c.isupper()) / len(message.content)
                    if caps_ratio > 0.7:
                        violations.append("caps")
            
            # Handle violations
            if violations:
                await self.handle_automod_violation(message, violations, settings)
                
        except Exception as e:
            print(f"AutoMod filter error: {e}")
    
    async def handle_automod_violation(self, message, violations, settings):
        """Handle automod violations"""
        try:
            # Delete message
            await message.delete()
            
            # Apply punishment based on settings
            punishment = settings[12]  # punishment column
            
            if punishment == "warn":
                # Add warning
                conn = sqlite3.connect(DATABASE_FILE)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_warnings (user_id, guild_id, moderator_id, reason)
                    VALUES (?, ?, ?, ?)
                ''', (message.author.id, message.guild.id, self.bot.user.id, f"AutoMod: {', '.join(violations)}"))
                conn.commit()
                conn.close()
            
            elif punishment == "timeout":
                # Apply 10 minute timeout
                timeout_until = datetime.now() + timedelta(minutes=10)
                await message.author.timeout(timeout_until, reason=f"AutoMod: {', '.join(violations)}")
            
            # Send notification
            embed = create_embed(
                title="🛡️ AutoMod Action",
                description=f"Message from **{message.author.mention}** was deleted",
                color=COLORS['mod']
            )
            
            embed.add_field(
                name="🚨 Violations",
                value="\n".join([f"• {v.title()}" for v in violations]),
                inline=True
            )
            
            embed.add_field(
                name="⚖️ Action Taken",
                value=punishment.title(),
                inline=True
            )
            
            await message.channel.send(embed=embed, delete_after=10)
            
        except Exception as e:
            print(f"AutoMod punishment error: {e}")
    
    def log_moderation_action(self, guild_id: int, user_id: int, moderator_id: int, action: str, reason: str, duration: int = None):
        """Log moderation action to database"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mod_logs (guild_id, user_id, moderator_id, action, reason, duration)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (guild_id, user_id, moderator_id, action, reason, duration))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error logging moderation action: {e}")
    
    @discord.app_commands.command(name="warnings", description="📋 View user warnings")
    @discord.app_commands.describe(user="User to check warnings for")
    async def warnings(self, interaction: discord.Interaction, user: discord.Member):
        """View user warnings"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT reason, moderator_id, created_at FROM user_warnings 
                WHERE user_id = ? AND guild_id = ? AND active = 1
                ORDER BY created_at DESC
            ''', (user.id, interaction.guild.id))
            warnings = cursor.fetchall()
            conn.close()
            
            if not warnings:
                embed = create_embed(
                    title="📋 User Warnings",
                    description=f"**{user.mention}** has no warnings",
                    color=COLORS['success']
                )
            else:
                embed = create_embed(
                    title="📋 User Warnings",
                    description=f"**{user.mention}** has **{len(warnings)}** warning{'s' if len(warnings) != 1 else ''}",
                    color=COLORS['warning']
                )
                
                warning_text = ""
                for i, (reason, mod_id, created_at) in enumerate(warnings[:10]):
                    moderator = interaction.guild.get_member(mod_id)
                    mod_name = moderator.display_name if moderator else f"User {mod_id}"
                    date = datetime.fromisoformat(created_at).strftime("%Y-%m-%d")
                    warning_text += f"**{i+1}.** {reason}\n*By {mod_name} on {date}*\n\n"
                
                embed.add_field(
                    name="⚠️ Warning History",
                    value=warning_text[:1024],  # Discord limit
                    inline=False
                )
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Error", f"Could not load warnings: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class AutoModSetupView(discord.ui.View):
    """Interactive AutoMod setup"""
    
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="🛡️ Configure Filters", style=discord.ButtonStyle.primary)
    async def configure_filters(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        view = AutoModFiltersView(self.user_id, self.guild_id)
        embed = create_embed(
            title="🛡️ AutoMod Filters",
            description="**Configure which filters to enable**",
            color=COLORS['mod']
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @discord.ui.button(label="⚖️ Set Punishments", style=discord.ButtonStyle.secondary)
    async def set_punishments(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        view = AutoModPunishmentView(self.user_id, self.guild_id)
        embed = create_embed(
            title="⚖️ AutoMod Punishments",
            description="**Configure how violations are punished**",
            color=COLORS['mod']
        )
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

class AutoModFiltersView(discord.ui.View):
    """AutoMod filters configuration"""
    
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="🔄 Toggle Spam Filter", style=discord.ButtonStyle.secondary)
    async def toggle_spam(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        await self.toggle_filter(interaction, "spam_filter", "Spam Filter")
    
    @discord.ui.button(label="🔗 Toggle Link Filter", style=discord.ButtonStyle.secondary)
    async def toggle_links(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        await self.toggle_filter(interaction, "link_filter", "Link Filter")
    
    @discord.ui.button(label="📨 Toggle Invite Filter", style=discord.ButtonStyle.secondary)
    async def toggle_invites(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        await self.toggle_filter(interaction, "invite_filter", "Invite Filter")
    
    async def toggle_filter(self, interaction: discord.Interaction, filter_name: str, display_name: str):
        """Toggle a specific filter"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Get current status
            cursor.execute(f'SELECT {filter_name} FROM automod_settings WHERE guild_id = ?', (self.guild_id,))
            result = cursor.fetchone()
            
            new_status = not (result[0] if result else False)
            
            if result:
                cursor.execute(f'UPDATE automod_settings SET {filter_name} = ? WHERE guild_id = ?', (new_status, self.guild_id))
            else:
                cursor.execute('INSERT INTO automod_settings (guild_id, {}) VALUES (?, ?)'.format(filter_name), (self.guild_id, new_status))
            
            conn.commit()
            conn.close()
            
            embed = create_success_embed(
                f"✅ {display_name} Updated",
                f"{display_name} is now **{'Enabled' if new_status else 'Disabled'}**",
                interaction.user
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = create_error_embed("Configuration Error", f"Could not update filter: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class AutoModPunishmentView(discord.ui.View):
    """AutoMod punishment configuration"""
    
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.select(
        placeholder="⚖️ Select punishment type...",
        options=[
            discord.SelectOption(label="⚠️ Warn", description="Give user a warning", value="warn"),
            discord.SelectOption(label="🔇 Timeout", description="Temporary timeout", value="timeout"),
            discord.SelectOption(label="👢 Kick", description="Remove from server", value="kick"),
            discord.SelectOption(label="🔨 Ban", description="Permanent removal", value="ban")
        ]
    )
    async def punishment_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        punishment = select.values[0]
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Update punishment setting
            cursor.execute('''
                INSERT OR REPLACE INTO automod_settings (guild_id, punishment)
                VALUES (?, ?)
            ''', (self.guild_id, punishment))
            
            conn.commit()
            conn.close()
            
            embed = create_success_embed(
                "⚖️ Punishment Set",
                f"AutoMod violations will now result in: **{punishment.title()}**",
                interaction.user
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = create_error_embed("Configuration Error", f"Could not set punishment: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(ModerationSystem(bot))