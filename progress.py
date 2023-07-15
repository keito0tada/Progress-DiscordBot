import discord
from discord.ext import commands
import os
from typing import final

DISCORD_BOT_TOKEN: final(str) = os.getenv('DISCORD_BOT_TOKEN')
bot = commands.Bot(command_prefix='/', intents=discord.Intents.all())


async def load_extensions():
    await bot.load_extension('source.main', package='.')


@bot.event
async def on_ready():
    await load_extensions()


bot.run(DISCORD_BOT_TOKEN)
