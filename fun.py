import discord
from discord.ext import commands
import random
import sqlite3
import aiohttp
import asyncio
from datetime import datetime
from cogs.premium import is_premium_user, is_premium_guild

DATABASE_FILE = "bot_database.db"

COLORS = {
    'success': 0x00FF00,
    'error': 0xFF0000,
    'warning': 0xFFA500,
    'info': 0x0099FF,
    'fun': 0xFF69B4
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

class FunCommands(commands.Cog):
    """Fun commands and entertainment features"""
    
    def __init__(self, bot):
        self.bot = bot
        self.ai_api_key = None
        self.load_ai_config()
    
    def load_ai_config(self):
        """Load AI API configuration"""
        try:
            import config
            self.ai_api_key = getattr(config, 'AI_API_KEY', None)
        except:
            pass
    
    @discord.app_commands.command(name="8ball", description="🎱 Ask the magic 8-ball a question")
    @discord.app_commands.describe(question="Your question for the 8-ball")
    async def eightball(self, interaction: discord.Interaction, question: str):
        """Magic 8-ball command"""
        responses = [
            "It is certain", "Reply hazy, try again", "Don't count on it",
            "It is decidedly so", "Ask again later", "My reply is no",
            "Without a doubt", "Better not tell you now", "My sources say no",
            "Yes definitely", "Cannot predict now", "Outlook not so good",
            "You may rely on it", "Concentrate and ask again", "Very doubtful",
            "As I see it, yes", "My reply is no", "Signs point to yes",
            "Most likely", "Outlook good", "Yes"
        ]
        
        answer = random.choice(responses)
        
        embed = create_embed(
            title="🎱 Magic 8-Ball",
            description=f"**Question:** {question}\n\n**Answer:** {answer}",
            color=COLORS['fun']
        )
        
        embed.set_footer(text=f"Asked by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="dice", description="🎲 Roll dice")
    @discord.app_commands.describe(
        sides="Number of sides on the dice",
        count="Number of dice to roll"
    )
    async def dice(self, interaction: discord.Interaction, sides: int = 6, count: int = 1):
        """Roll dice"""
        if sides < 2 or sides > 100:
            embed = create_error_embed("Invalid Dice", "Dice must have between 2 and 100 sides!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if count < 1 or count > 10:
            embed = create_error_embed("Invalid Count", "You can roll between 1 and 10 dice!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        rolls = [random.randint(1, sides) for _ in range(count)]
        total = sum(rolls)
        
        embed = create_embed(
            title="🎲 Dice Roll",
            description=f"**Rolling {count}d{sides}**",
            color=COLORS['fun']
        )
        
        if count == 1:
            embed.add_field(
                name="🎯 Result",
                value=f"**{rolls[0]}**",
                inline=False
            )
        else:
            embed.add_field(
                name="🎯 Individual Rolls",
                value=" + ".join([f"**{roll}**" for roll in rolls]),
                inline=False
            )
            embed.add_field(
                name="📊 Total",
                value=f"**{total}**",
                inline=False
            )
        
        embed.set_footer(text=f"Rolled by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="coinflip", description="🪙 Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        """Flip a coin"""
        result = random.choice(["Heads", "Tails"])
        emoji = "🔵" if result == "Heads" else "🔴"
        
        embed = create_embed(
            title="🪙 Coinflip",
            description=f"**{emoji} {result}!**",
            color=COLORS['fun']
        )
        
        embed.set_footer(text=f"Flipped by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="meme", description="😂 Get a random meme")
    async def meme(self, interaction: discord.Interaction):
        """Fetch random meme"""
        await interaction.response.defer()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get('https://api.imgflip.com/get_memes') as response:
                    if response.status == 200:
                        data = await response.json()
                        memes = data['data']['memes']
                        meme = random.choice(memes)
                        
                        embed = create_embed(
                            title="😂 Random Meme",
                            description=f"**{meme['name']}**",
                            color=COLORS['fun']
                        )
                        
                        embed.set_image(url=meme['url'])
                        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
                        
                        await interaction.followup.send(embed=embed)
                    else:
                        embed = create_error_embed("Meme Error", "Could not fetch meme at this time.")
                        await interaction.followup.send(embed=embed)
        
        except Exception as e:
            embed = create_error_embed("Meme Error", f"Failed to get meme: {str(e)}")
            await interaction.followup.send(embed=embed)
    
    @discord.app_commands.command(name="joke", description="😄 Get a random joke")
    async def joke(self, interaction: discord.Interaction):
        """Get random joke"""
        jokes = [
            "Why don't scientists trust atoms? Because they make up everything!",
            "Why did the scarecrow win an award? He was outstanding in his field!",
            "Why don't eggs tell jokes? They'd crack each other up!",
            "What do you call a fake noodle? An impasta!",
            "Why did the math book look so sad? Because it was full of problems!",
            "What do you call a bear with no teeth? A gummy bear!",
            "Why don't programmers like nature? It has too many bugs!",
            "What's the best thing about Switzerland? I don't know, but the flag is a big plus!",
            "Why do programmers prefer dark mode? Because light attracts bugs!",
            "How do you organize a space party? You planet!"
        ]
        
        joke = random.choice(jokes)
        
        embed = create_embed(
            title="😄 Random Joke",
            description=joke,
            color=COLORS['fun']
        )
        
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="ai_chat", description="🤖 [PREMIUM] Chat with AI")
    @discord.app_commands.describe(message="Your message to the AI")
    async def ai_chat(self, interaction: discord.Interaction, message: str):
        """AI chat feature (premium only)"""
        if not (is_premium_user(interaction.user.id) or is_premium_guild(interaction.guild.id)):
            embed = create_error_embed(
                "Premium Required",
                "AI chat is a **premium-only** feature!"
            )
            embed.add_field(
                name="🎫 Get Premium",
                value="Use `/premium redeem <code>` to unlock AI features",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if not self.ai_api_key:
            embed = create_error_embed("AI Unavailable", "AI system is not configured.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            # This is a placeholder for AI integration
            # In a real implementation, you'd call your AI API here
            responses = [
                f"Hello {interaction.user.display_name}! I understand you said: '{message}'. How can I help you today?",
                f"That's interesting! You mentioned: '{message}'. I'd love to discuss this further.",
                f"I see you're asking about: '{message}'. Let me think about this...",
                f"Thanks for sharing: '{message}'. What would you like to know more about?"
            ]
            
            ai_response = random.choice(responses)
            
            embed = create_embed(
                title="🤖 AI Response",
                description=f"**Your message:** {message}\n\n**AI:** {ai_response}",
                color=COLORS['info']
            )
            
            embed.add_field(
                name="💎 Premium Feature",
                value="This AI chat is available to premium users",
                inline=False
            )
            
            embed.set_footer(text="AI responses are generated and may not always be accurate")
            
            await interaction.followup.send(embed=embed)
            
        except Exception as e:
            embed = create_error_embed("AI Error", f"Could not generate response: {str(e)}")
            await interaction.followup.send(embed=embed)
    
    @discord.app_commands.command(name="poll", description="📊 Create a poll")
    @discord.app_commands.describe(
        question="Poll question",
        option1="First option",
        option2="Second option",
        option3="Third option (optional)",
        option4="Fourth option (optional)"
    )
    async def poll(self, interaction: discord.Interaction, question: str, option1: str, option2: str, option3: str = None, option4: str = None):
        """Create a poll"""
        options = [option1, option2]
        if option3:
            options.append(option3)
        if option4:
            options.append(option4)
        
        embed = create_embed(
            title="📊 Poll",
            description=f"**{question}**",
            color=COLORS['info']
        )
        
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
        
        for i, option in enumerate(options):
            embed.add_field(
                name=f"{emojis[i]} Option {i+1}",
                value=option,
                inline=False
            )
        
        embed.set_footer(text=f"Poll created by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        message = await interaction.response.send_message(embed=embed)
        
        # Add reactions
        for i in range(len(options)):
            await message.add_reaction(emojis[i])
    
    @discord.app_commands.command(name="avatar", description="🖼️ View user's avatar")
    @discord.app_commands.describe(user="User to view avatar of")
    async def avatar(self, interaction: discord.Interaction, user: discord.Member = None):
        """Show user avatar"""
        target_user = user or interaction.user
        
        embed = create_embed(
            title=f"🖼️ {target_user.display_name}'s Avatar",
            description="",
            color=COLORS['info']
        )
        
        embed.set_image(url=target_user.display_avatar.url)
        embed.add_field(
            name="🔗 Avatar URL",
            value=f"[Click here to download]({target_user.display_avatar.url})",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="userinfo", description="ℹ️ Get information about a user")
    @discord.app_commands.describe(user="User to get information about")
    async def userinfo(self, interaction: discord.Interaction, user: discord.Member = None):
        """Get user information"""
        target_user = user or interaction.user
        
        embed = create_embed(
            title=f"ℹ️ {target_user.display_name}",
            description="**User Information**",
            color=COLORS['info']
        )
        
        embed.set_thumbnail(url=target_user.display_avatar.url)
        
        embed.add_field(
            name="👤 Basic Info",
            value=f"**Username:** {target_user.name}\n**Display Name:** {target_user.display_name}\n**ID:** {target_user.id}",
            inline=True
        )
        
        embed.add_field(
            name="📅 Dates",
            value=f"**Created:** <t:{int(target_user.created_at.timestamp())}:F>\n**Joined:** <t:{int(target_user.joined_at.timestamp())}:F>",
            inline=True
        )
        
        embed.add_field(
            name="🎭 Roles",
            value=f"**Count:** {len(target_user.roles)-1}\n**Highest:** {target_user.top_role.mention}",
            inline=True
        )
        
        # Show some roles
        if len(target_user.roles) > 1:
            roles_list = [role.mention for role in sorted(target_user.roles[1:], key=lambda r: r.position, reverse=True)[:10]]
            embed.add_field(
                name="🏷️ Role List",
                value=" ".join(roles_list) if roles_list else "No roles",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="serverinfo", description="🏰 Get server information")
    async def serverinfo(self, interaction: discord.Interaction):
        """Get server information"""
        guild = interaction.guild
        
        embed = create_embed(
            title=f"🏰 {guild.name}",
            description="**Server Information**",
            color=COLORS['info']
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(
            name="📊 Statistics",
            value=f"**Members:** {guild.member_count:,}\n**Channels:** {len(guild.channels)}\n**Roles:** {len(guild.roles)}",
            inline=True
        )
        
        embed.add_field(
            name="📅 Created",
            value=f"<t:{int(guild.created_at.timestamp())}:F>\n({(datetime.now() - guild.created_at).days} days ago)",
            inline=True
        )
        
        embed.add_field(
            name="👑 Owner",
            value=f"{guild.owner.mention}" if guild.owner else "Unknown",
            inline=True
        )
        
        embed.add_field(
            name="🌟 Features",
            value=f"**Boost Level:** {guild.premium_tier}\n**Boosts:** {guild.premium_subscription_count}\n**Verification:** {guild.verification_level.name.title()}",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="calculator", description="🧮 Simple calculator")
    @discord.app_commands.describe(expression="Math expression to calculate")
    async def calculator(self, interaction: discord.Interaction, expression: str):
        """Simple calculator"""
        try:
            # Safety check - only allow basic math operations
            allowed_chars = set('0123456789+-*/.() ')
            if not all(c in allowed_chars for c in expression):
                embed = create_error_embed("Invalid Expression", "Only basic math operations are allowed (+, -, *, /, parentheses)")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Evaluate expression safely
            result = eval(expression.replace(" ", ""))
            
            embed = create_embed(
                title="🧮 Calculator",
                description=f"**Expression:** `{expression}`\n**Result:** `{result}`",
                color=COLORS['success']
            )
            
            embed.set_footer(text=f"Calculated by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
            
            await interaction.response.send_message(embed=embed)
            
        except ZeroDivisionError:
            embed = create_error_embed("Math Error", "Cannot divide by zero!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception:
            embed = create_error_embed("Invalid Expression", "Please enter a valid math expression!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @discord.app_commands.command(name="pick", description="🎯 Pick random option from list")
    @discord.app_commands.describe(options="Options separated by commas")
    async def pick(self, interaction: discord.Interaction, options: str):
        """Pick random option"""
        option_list = [opt.strip() for opt in options.split(',') if opt.strip()]
        
        if len(option_list) < 2:
            embed = create_error_embed("Not Enough Options", "Please provide at least 2 options separated by commas!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        if len(option_list) > 20:
            embed = create_error_embed("Too Many Options", "Please provide maximum 20 options!")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        chosen = random.choice(option_list)
        
        embed = create_embed(
            title="🎯 Random Pick",
            description=f"**I choose:** {chosen}",
            color=COLORS['fun']
        )
        
        embed.add_field(
            name="📋 Options",
            value="\n".join([f"• {opt}" for opt in option_list[:10]]),
            inline=False
        )
        
        embed.set_footer(text=f"Picked for {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)
    
    @discord.app_commands.command(name="remind", description="⏰ Set a reminder")
    @discord.app_commands.describe(
        time="When to remind you (e.g., 10m, 1h, 2d)",
        reminder="What to remind you about"
    )
    async def remind(self, interaction: discord.Interaction, time: str, reminder: str):
        """Set a reminder"""
        try:
            # Parse duration
            total_seconds = 0
            time_parts = time.lower().split()
            
            for part in time_parts:
                if part.endswith('d'):
                    total_seconds += int(part[:-1]) * 86400
                elif part.endswith('h'):
                    total_seconds += int(part[:-1]) * 3600
                elif part.endswith('m'):
                    total_seconds += int(part[:-1]) * 60
                elif part.endswith('s'):
                    total_seconds += int(part[:-1])
            
            if total_seconds <= 0 or total_seconds > 2592000:  # Max 30 days
                embed = create_error_embed("Invalid Duration", "Duration must be between 1 second and 30 days!")
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            
            # Schedule reminder
            asyncio.create_task(self.send_reminder(interaction.user, interaction.channel, reminder, total_seconds))
            
            remind_time = datetime.now() + timedelta(seconds=total_seconds)
            
            embed = create_success_embed(
                "⏰ Reminder Set",
                f"I'll remind you about: **{reminder}**",
                interaction.user
            )
            
            embed.add_field(
                name="🕐 Reminder Time",
                value=f"<t:{int(remind_time.timestamp())}:F>",
                inline=False
            )
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            embed = create_error_embed("Invalid Time", "Please use format like: 10m, 1h, 2d")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = create_error_embed("Reminder Failed", f"Could not set reminder: {str(e)}")
            await interaction.response.send_message(embed=embed, ephemeral=True)
    
    async def send_reminder(self, user: discord.User, channel: discord.TextChannel, reminder: str, delay: int):
        """Send reminder after delay"""
        await asyncio.sleep(delay)
        
        try:
            embed = create_embed(
                title="⏰ Reminder",
                description=f"**{user.mention}**, you asked me to remind you:\n\n{reminder}",
                color=COLORS['warning']
            )
            
            embed.set_footer(text="Reminder delivered", icon_url=user.display_avatar.url)
            
            await channel.send(embed=embed)
            
        except Exception as e:
            print(f"Error sending reminder: {e}")
    
    @discord.app_commands.command(name="rps", description="🪨 Play Rock Paper Scissors")
    @discord.app_commands.describe(choice="Your choice")
    @discord.app_commands.choices(choice=[
        discord.app_commands.Choice(name="🪨 Rock", value="rock"),
        discord.app_commands.Choice(name="📄 Paper", value="paper"),
        discord.app_commands.Choice(name="✂️ Scissors", value="scissors")
    ])
    async def rps(self, interaction: discord.Interaction, choice: discord.app_commands.Choice[str]):
        """Rock Paper Scissors game"""
        bot_choice = random.choice(["rock", "paper", "scissors"])
        
        emojis = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
        
        # Determine winner
        if choice.value == bot_choice:
            result = "🤝 **It's a tie!**"
            color = COLORS['warning']
        elif (choice.value == "rock" and bot_choice == "scissors") or \
             (choice.value == "paper" and bot_choice == "rock") or \
             (choice.value == "scissors" and bot_choice == "paper"):
            result = "🎉 **You win!**"
            color = COLORS['success']
        else:
            result = "💸 **I win!**"
            color = COLORS['error']
        
        embed = create_embed(
            title="🪨📄✂️ Rock Paper Scissors",
            description=f"**You:** {emojis[choice.value]} {choice.value.title()}\n**Bot:** {emojis[bot_choice]} {bot_choice.title()}\n\n{result}",
            color=color
        )
        
        embed.set_footer(text=f"Played by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(FunCommands(bot))