import discord
from discord.ext import commands
import sqlite3
import random
import asyncio
from datetime import datetime
from cogs.premium import is_premium_user, is_premium_guild
from PIL import Image, ImageDraw, ImageFont
import io

DATABASE_FILE = "bot_database.db"

COLORS = {
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500,
    'info': 0x0099FF,
    'gold': 0xFFD700,
    'purple': 0x9932CC
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

class LevelingSystem(commands.Cog):
    """Complete XP and leveling system with rank cards and role rewards"""
    
    def __init__(self, bot):
        self.bot = bot
        self.init_leveling_database()
        self.xp_cooldowns = {}
    
    def init_leveling_database(self):
        """Initialize leveling database tables"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # User levels
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_levels (
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 0,
                    total_xp INTEGER DEFAULT 0,
                    last_message TIMESTAMP,
                    message_count INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, guild_id)
                )
            ''')
            
            # Level rewards (roles given at certain levels)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS level_rewards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    level INTEGER NOT NULL,
                    role_id INTEGER NOT NULL,
                    created_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Leveling settings per guild
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS leveling_settings (
                    guild_id INTEGER PRIMARY KEY,
                    enabled BOOLEAN DEFAULT 1,
                    xp_per_message INTEGER DEFAULT 15,
                    xp_cooldown INTEGER DEFAULT 60,
                    level_up_message TEXT DEFAULT 'Congratulations {user}! You reached level {level}!',
                    level_up_channel INTEGER,
                    no_xp_channels TEXT,
                    no_xp_roles TEXT,
                    double_xp_channels TEXT,
                    double_xp_roles TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
            print("✅ Leveling system database initialized")
            
        except Exception as e:
            print(f"❌ Leveling database initialization failed: {e}")
    
    def calculate_level(self, total_xp: int) -> int:
        """Calculate level from total XP"""
        # Level formula: level = floor(sqrt(total_xp / 100))
        return int((total_xp / 100) ** 0.5)
    
    def xp_for_level(self, level: int) -> int:
        """Calculate XP needed for specific level"""
        return (level ** 2) * 100
    
    def xp_for_next_level(self, current_level: int) -> int:
        """Calculate XP needed for next level"""
        return self.xp_for_level(current_level + 1)
    
    def get_user_level_data(self, user_id: int, guild_id: int) -> dict:
        """Get user's level data"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT xp, level, total_xp, message_count 
                FROM user_levels WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            result = cursor.fetchone()
            conn.close()
            
            if result:
                xp, level, total_xp, message_count = result
                return {
                    'xp': xp,
                    'level': level,
                    'total_xp': total_xp,
                    'message_count': message_count,
                    'xp_needed': self.xp_for_next_level(level) - total_xp
                }
            else:
                return {'xp': 0, 'level': 0, 'total_xp': 0, 'message_count': 0, 'xp_needed': 100}
                
        except Exception as e:
            print(f"Error getting user level data: {e}")
            return {'xp': 0, 'level': 0, 'total_xp': 0, 'message_count': 0, 'xp_needed': 100}
    
    async def add_xp(self, user_id: int, guild_id: int, xp_amount: int = None) -> bool:
        """Add XP to user and check for level up"""
        # Check cooldown
        cooldown_key = f"{user_id}_{guild_id}"
        if cooldown_key in self.xp_cooldowns:
            if datetime.now() < self.xp_cooldowns[cooldown_key]:
                return False
        
        # Set cooldown (shorter for premium)
        cooldown_seconds = 30 if (is_premium_user(user_id) or is_premium_guild(guild_id)) else 60
        self.xp_cooldowns[cooldown_key] = datetime.now() + timedelta(seconds=cooldown_seconds)
        
        # Calculate XP gain
        if xp_amount is None:
            base_xp = random.randint(10, 25)
            premium_bonus = random.randint(5, 10) if (is_premium_user(user_id) or is_premium_guild(guild_id)) else 0
            xp_amount = base_xp + premium_bonus
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Get current data
            cursor.execute('''
                SELECT xp, level, total_xp FROM user_levels 
                WHERE user_id = ? AND guild_id = ?
            ''', (user_id, guild_id))
            result = cursor.fetchone()
            
            if result:
                current_xp, current_level, total_xp = result
                new_total_xp = total_xp + xp_amount
                new_level = self.calculate_level(new_total_xp)
                new_xp = new_total_xp - self.xp_for_level(new_level)
                
                cursor.execute('''
                    UPDATE user_levels 
                    SET xp = ?, level = ?, total_xp = ?, last_message = datetime('now'),
                        message_count = message_count + 1
                    WHERE user_id = ? AND guild_id = ?
                ''', (new_xp, new_level, new_total_xp, user_id, guild_id))
            else:
                # Create new user
                new_level = self.calculate_level(xp_amount)
                new_xp = xp_amount - self.xp_for_level(new_level)
                
                cursor.execute('''
                    INSERT INTO user_levels (user_id, guild_id, xp, level, total_xp, last_message, message_count)
                    VALUES (?, ?, ?, ?, ?, datetime('now'), 1)
                ''', (user_id, guild_id, new_xp, new_level, xp_amount))
                
                current_level = 0
            
            conn.commit()
            conn.close()
            
            # Check for level up
            if new_level > current_level:
                await self.handle_level_up(user_id, guild_id, new_level)
                return True
            
            return False
            
        except Exception as e:
            print(f"Error adding XP: {e}")
            return False
    
    async def handle_level_up(self, user_id: int, guild_id: int, new_level: int):
        """Handle level up event"""
        try:
            guild = self.bot.get_guild(guild_id)
            user = guild.get_member(user_id) if guild else None
            
            if not guild or not user:
                return
            
            # Check for level rewards
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT role_id FROM level_rewards 
                WHERE guild_id = ? AND level = ? AND active = 1
            ''', (guild_id, new_level))
            rewards = cursor.fetchall()
            
            # Get leveling settings
            cursor.execute('''
                SELECT level_up_message, level_up_channel 
                FROM leveling_settings WHERE guild_id = ?
            ''', (guild_id,))
            settings = cursor.fetchone()
            conn.close()
            
            # Apply role rewards
            roles_given = []
            for (role_id,) in rewards:
                role = guild.get_role(role_id)
                if role and role not in user.roles:
                    try:
                        await user.add_roles(role, reason=f"Level {new_level} reward")
                        roles_given.append(role.name)
                    except:
                        pass
            
            # Send level up message
            if settings:
                message_template = settings[0] or "Congratulations {user}! You reached level {level}!"
                channel_id = settings[1]
            else:
                message_template = "Congratulations {user}! You reached level {level}!"
                channel_id = None
            
            message = message_template.format(user=user.mention, level=new_level)
            
            embed = create_success_embed(
                "🎉 Level Up!",
                message,
                user
            )
            
            embed.add_field(
                name="📊 New Level",
                value=f"**Level {new_level}**",
                inline=True
            )
            
            if roles_given:
                embed.add_field(
                    name="🎁 Role Rewards",
                    value="\n".join(f"• {role_name}" for role_name in roles_given),
                    inline=True
                )
            
            # Send to specified channel or try to find general channel
            channel = None
            if channel_id:
                channel = guild.get_channel(channel_id)
            
            if not channel:
                # Try to find a suitable channel
                for ch in guild.text_channels:
                    if ch.name.lower() in ['general', 'chat', 'main', 'level-up', 'levels']:
                        channel = ch
                        break
                
                if not channel:
                    channel = guild.system_channel or guild.text_channels[0] if guild.text_channels else None
            
            if channel:
                try:
                    await channel.send(embed=embed)
                except:
                    pass
                
        except Exception as e:
            print(f"Error handling level up: {e}")
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Award XP for messages"""
        if message.author.bot or not message.guild:
            return
        
        # Check if leveling is enabled
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('SELECT enabled FROM leveling_settings WHERE guild_id = ?', (message.guild.id,))
            result = cursor.fetchone()
            conn.close()
            
            if result and not result[0]:
                return
        except:
            pass
        
        # Add XP
        await self.add_xp(message.author.id, message.guild.id)
    
    @discord.app_commands.command(name="rank", description="📊 Check your or someone's rank")
    @discord.app_commands.describe(user="User to check rank for")
    async def rank(self, interaction: discord.Interaction, user: discord.Member = None):
        """Show user rank with card"""
        target_user = user or interaction.user
        level_data = self.get_user_level_data(target_user.id, interaction.guild.id)
        
        # Get user's rank
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) + 1 FROM user_levels 
                WHERE guild_id = ? AND total_xp > ?
            ''', (interaction.guild.id, level_data['total_xp']))
            rank = cursor.fetchone()[0]
            conn.close()
        except:
            rank = 1
        
        # Create rank card
        rank_card = await self.create_rank_card(target_user, level_data, rank)
        
        embed = create_embed(
            title=f"📊 {target_user.display_name}'s Rank",
            description=f"**Level {level_data['level']}** • **Rank #{rank}**",
            color=COLORS['purple']
        )
        
        embed.add_field(
            name="📈 Progress",
            value=f"XP: **{level_data['total_xp']:,}**\nNext Level: **{level_data['xp_needed']:,} XP**\nMessages: **{level_data['message_count']:,}**",
            inline=True
        )
        
        if rank_card:
            file = discord.File(rank_card, filename="rank_card.png")
            embed.set_image(url="attachment://rank_card.png")
            await interaction.response.send_message(embed=embed, file=file)
        else:
            await interaction.response.send_message(embed=embed)
    
    async def create_rank_card(self, user: discord.Member, level_data: dict, rank: int) -> io.BytesIO:
        """Create a visual rank card"""
        try:
            # Create image
            width, height = 800, 200
            img = Image.new('RGB', (width, height), color=(47, 49, 54))
            draw = ImageDraw.Draw(img)
            
            # Try to load fonts (fallback to default if not available)
            try:
                title_font = ImageFont.truetype("arial.ttf", 24)
                text_font = ImageFont.truetype("arial.ttf", 18)
                small_font = ImageFont.truetype("arial.ttf", 14)
            except:
                title_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
                small_font = ImageFont.load_default()
            
            # Colors
            bg_color = (54, 57, 63)
            accent_color = (114, 137, 218)
            text_color = (255, 255, 255)
            
            # Draw background
            draw.rectangle([10, 10, width-10, height-10], fill=bg_color, outline=accent_color, width=2)
            
            # User info
            draw.text((20, 20), f"{user.display_name}", font=title_font, fill=text_color)
            draw.text((20, 50), f"Rank #{rank} • Level {level_data['level']}", font=text_font, fill=accent_color)
            
            # XP Progress bar
            bar_width = 400
            bar_height = 20
            bar_x = 20
            bar_y = 80
            
            # Background bar
            draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], fill=(32, 34, 37), outline=accent_color)
            
            # Progress bar
            current_level_xp = level_data['total_xp'] - self.xp_for_level(level_data['level'])
            next_level_xp = self.xp_for_next_level(level_data['level']) - self.xp_for_level(level_data['level'])
            progress = current_level_xp / next_level_xp if next_level_xp > 0 else 1
            progress_width = int(bar_width * progress)
            
            if progress_width > 0:
                draw.rectangle([bar_x, bar_y, bar_x + progress_width, bar_y + bar_height], fill=accent_color)
            
            # XP text
            draw.text((bar_x, bar_y + 25), f"{current_level_xp:,} / {next_level_xp:,} XP", font=small_font, fill=text_color)
            
            # Statistics
            draw.text((20, 120), f"Total XP: {level_data['total_xp']:,}", font=text_font, fill=text_color)
            draw.text((20, 145), f"Messages: {level_data['message_count']:,}", font=text_font, fill=text_color)
            
            # Save to bytes
            img_bytes = io.BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            return img_bytes
            
        except Exception as e:
            print(f"Error creating rank card: {e}")
            return None
    
    @discord.app_commands.command(name="leaderboard", description="🏆 View server leaderboard")
    @discord.app_commands.describe(page="Page number to view")
    async def leaderboard(self, interaction: discord.Interaction, page: int = 1):
        """Show server leaderboard"""
        page = max(1, page)
        offset = (page - 1) * 10
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                SELECT user_id, level, total_xp, message_count 
                FROM user_levels WHERE guild_id = ? 
                ORDER BY total_xp DESC 
                LIMIT 10 OFFSET ?
            ''', (interaction.guild.id, offset))
            results = cursor.fetchall()
            
            # Get total users
            cursor.execute('SELECT COUNT(*) FROM user_levels WHERE guild_id = ?', (interaction.guild.id,))
            total_users = cursor.fetchone()[0]
            conn.close()
            
            if not results:
                embed = create_embed(
                    title="🏆 Server Leaderboard",
                    description="**No users found on this page**",
                    color=COLORS['warning']
                )
            else:
                embed = create_embed(
                    title="🏆 Server Leaderboard",
                    description=f"**Top users by total XP** • Page {page}",
                    color=COLORS['gold']
                )
                
                leaderboard_text = ""
                for i, (user_id, level, total_xp, msg_count) in enumerate(results):
                    rank = offset + i + 1
                    user = interaction.guild.get_member(user_id)
                    username = user.display_name if user else f"User {user_id}"
                    
                    medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"{rank}."
                    leaderboard_text += f"{medal} **{username}** • Level {level} • {total_xp:,} XP\n"
                
                embed.add_field(
                    name="📊 Rankings",
                    value=leaderboard_text,
                    inline=False
                )
                
                max_pages = (total_users + 9) // 10
                embed.set_footer(text=f"Page {page}/{max_pages} • {total_users} total users")
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Leaderboard Error", f"Could not load leaderboard: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="level_admin", description="🔧 [ADMIN] Manage leveling system")
    @discord.app_commands.describe(
        action="Admin action to perform",
        user="Target user for XP/level changes",
        amount="Amount of XP or levels to add/remove"
    )
    @discord.app_commands.choices(action=[
        discord.app_commands.Choice(name="➕ Add XP", value="add_xp"),
        discord.app_commands.Choice(name="➖ Remove XP", value="remove_xp"),
        discord.app_commands.Choice(name="📈 Set Level", value="set_level"),
        discord.app_commands.Choice(name="🔄 Reset User", value="reset_user"),
        discord.app_commands.Choice(name="⚙️ Configure", value="configure")
    ])
    async def level_admin(self, interaction: discord.Interaction, 
                         action: discord.app_commands.Choice[str],
                         user: discord.Member = None,
                         amount: int = None):
        """Admin leveling management"""
        
        if not interaction.user.guild_permissions.manage_guild:
            embed = create_error_embed("Permission Denied", "You need `Manage Server` permission to use admin commands.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if action.value == "configure":
            await self.show_leveling_config(interaction)
        elif action.value in ["add_xp", "remove_xp", "set_level", "reset_user"]:
            if not user:
                embed = create_error_embed("User Required", "Please specify a user for this action.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            if action.value in ["add_xp", "remove_xp", "set_level"] and amount is None:
                embed = create_error_embed("Amount Required", "Please specify an amount for this action.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            await self.execute_level_admin_action(interaction, action.value, user, amount)
    
    async def show_leveling_config(self, interaction: discord.Interaction):
        """Show leveling configuration interface"""
        view = LevelingConfigView(interaction.user.id, interaction.guild.id)
        
        embed = create_embed(
            title="⚙️ Leveling Configuration",
            description="**Configure the leveling system for your server**",
            color=COLORS['info']
        )
        
        embed.add_field(
            name="🎯 Configuration Options",
            value="• **Toggle System** - Enable/disable leveling\n• **XP Settings** - Amount and cooldowns\n• **Level Rewards** - Roles for reaching levels\n• **Channels** - Where level up messages are sent",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed, view=view)
    
    async def execute_level_admin_action(self, interaction: discord.Interaction, action: str, user: discord.Member, amount: int = None):
        """Execute admin level actions"""
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            if action == "add_xp":
                cursor.execute('''
                    UPDATE user_levels 
                    SET total_xp = total_xp + ?, level = ?, xp = total_xp - ?
                    WHERE user_id = ? AND guild_id = ?
                ''', (amount, self.calculate_level(amount), self.xp_for_level(self.calculate_level(amount)), user.id, interaction.guild.id))
                
                embed = create_success_embed(
                    "✅ XP Added",
                    f"Added **{amount:,} XP** to {user.mention}",
                    interaction.user
                )
                
            elif action == "remove_xp":
                cursor.execute('''
                    UPDATE user_levels 
                    SET total_xp = MAX(0, total_xp - ?), level = ?, xp = MAX(0, total_xp - ?)
                    WHERE user_id = ? AND guild_id = ?
                ''', (amount, self.calculate_level(max(0, amount)), self.xp_for_level(self.calculate_level(max(0, amount))), user.id, interaction.guild.id))
                
                embed = create_success_embed(
                    "✅ XP Removed",
                    f"Removed **{amount:,} XP** from {user.mention}",
                    interaction.user
                )
                
            elif action == "set_level":
                new_total_xp = self.xp_for_level(amount)
                cursor.execute('''
                    UPDATE user_levels 
                    SET level = ?, total_xp = ?, xp = 0
                    WHERE user_id = ? AND guild_id = ?
                ''', (amount, new_total_xp, user.id, interaction.guild.id))
                
                embed = create_success_embed(
                    "✅ Level Set",
                    f"Set {user.mention} to **Level {amount}**",
                    interaction.user
                )
                
            elif action == "reset_user":
                cursor.execute('''
                    UPDATE user_levels 
                    SET level = 0, total_xp = 0, xp = 0, message_count = 0
                    WHERE user_id = ? AND guild_id = ?
                ''', (user.id, interaction.guild.id))
                
                embed = create_success_embed(
                    "✅ User Reset",
                    f"Reset all level data for {user.mention}",
                    interaction.user
                )
            
            conn.commit()
            conn.close()
            
            await interaction.response.send_message(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("Admin Action Failed", f"Could not execute action: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

class LevelingConfigView(discord.ui.View):
    """Interactive leveling configuration"""
    
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.guild_id = guild_id
    
    @discord.ui.button(label="🔄 Toggle System", style=discord.ButtonStyle.primary, emoji="🔄")
    async def toggle_system(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            
            # Check current status
            cursor.execute('SELECT enabled FROM leveling_settings WHERE guild_id = ?', (self.guild_id,))
            result = cursor.fetchone()
            
            new_status = not (result[0] if result else True)
            
            if result:
                cursor.execute('UPDATE leveling_settings SET enabled = ? WHERE guild_id = ?', (new_status, self.guild_id))
            else:
                cursor.execute('INSERT INTO leveling_settings (guild_id, enabled) VALUES (?, ?)', (self.guild_id, new_status))
            
            conn.commit()
            conn.close()
            
            embed = create_success_embed(
                "✅ Leveling System Updated",
                f"Leveling system is now **{'Enabled' if new_status else 'Disabled'}**",
                interaction.user
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except Exception as e:
            embed = create_error_embed("Configuration Error", f"Could not update setting: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.ui.button(label="🎁 Manage Rewards", style=discord.ButtonStyle.secondary, emoji="🎁")
    async def manage_rewards(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Only the command user can configure this.", ephemeral=True)
            return
        
        # Show level rewards management
        modal = LevelRewardModal(self.guild_id)
        await interaction.response.send_modal(modal)

class LevelRewardModal(discord.ui.Modal):
    """Modal for adding level rewards"""
    
    def __init__(self, guild_id: int):
        super().__init__(title="🎁 Add Level Reward")
        self.guild_id = guild_id
        
        self.level_input = discord.ui.TextInput(
            label="Level",
            placeholder="Level to give reward at (e.g., 5, 10, 25)",
            max_length=10,
            required=True
        )
        
        self.role_input = discord.ui.TextInput(
            label="Role ID",
            placeholder="ID of role to give as reward",
            max_length=20,
            required=True
        )
        
        self.add_item(self.level_input)
        self.add_item(self.role_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            level = int(self.level_input.value)
            role_id = int(self.role_input.value)
            
            # Validate role exists
            guild = interaction.guild
            role = guild.get_role(role_id)
            
            if not role:
                embed = create_error_embed("Invalid Role", "The specified role was not found in this server.")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Add to database
            conn = sqlite3.connect(DATABASE_FILE)
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO level_rewards (guild_id, level, role_id, created_by)
                VALUES (?, ?, ?, ?)
            ''', (self.guild_id, level, role_id, interaction.user.id))
            conn.commit()
            conn.close()
            
            embed = create_success_embed(
                "🎁 Level Reward Added",
                f"Users will now receive **{role.name}** role when they reach **Level {level}**!",
                interaction.user
            )
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
        except ValueError:
            embed = create_error_embed("Invalid Input", "Please enter valid numbers for level and role ID.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed("Error", f"Could not add level reward: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(LevelingSystem(bot))