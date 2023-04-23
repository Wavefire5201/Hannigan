import discord
import dotenv
import json, os
import pandas as pd
from googleapiclient import discovery
from discord.ext import commands
from Bard import Chatbot

# Initialize bots & data

if (
    not os.path.exists("data/guild_data.json")
    or os.stat("data/guild_data.json").st_size == 0
):
    with open("data/guild_data.json", "w") as f:
        json.dump({}, f)

with open("data/guild_data.json", "r") as f:
    guild_data = json.load(f)


dotenv.load_dotenv()
bot = discord.Bot(intents=discord.Intents.all())
bard_bot = Chatbot(os.getenv("BARD_TOKEN"))

client = discovery.build(
    "commentanalyzer",
    "v1alpha1",
    developerKey=os.getenv("PERSPECTIVE_KEY"),
    discoveryServiceUrl="https://commentanalyzer.googleapis.com/$discovery/rest?version=v1alpha1",
    static_discovery=False,
)

attributeThresholds = {
    "INSULT": 0.6,
    "TOXICITY": 0.6,
}

attributeThresholdsExtreme = {
    "INSULT": 0.8,
    "TOXICITY": 0.8,
}

requestedAttributes = ["TOXICITY", "INSULT"]
# Functions


async def dump_data():
    with open("data/guild_data.json", "w") as f:
        json.dump(guild_data, f)


async def check_message(message):
    if message.attachments or message.author.bot:
        return

    if not any(
        str(message.author.id) in d for d in guild_data[str(message.guild.id)]["users"]
    ):
        guild_data[str(message.guild.id)]["users"][str(message.author.id)] = {}
        guild_data[str(message.guild.id)]["users"][str(message.author.id)][
            "score"
        ] = 100
        await dump_data()

    if (
        guild_data[str(message.guild.id)]["users"][str(message.author.id)]["score"] % 10
        == 0
        and guild_data[str(message.guild.id)]["users"][str(message.author.id)]["score"]
        != 100
    ):
        # await bot.get_user(message.author.id).timeout()
        await message.channel.send(
            f"{bot.get_user(message.author.id)} has been timeouted for being vile."
        )

    body = {
        "comment": {"text": message.content},
        "requestedAttributes": {key: {} for key in requestedAttributes},
        "languages": ["en"],
    }

    response = client.comments().analyze(body=body).execute()["attributeScores"]
    # print(response)
    scores = {}
    for k, v in response.items():
        scores[k] = v["summaryScore"]["value"]
    print(f"{message.content}: {scores}")

    user_score = guild_data[str(message.guild.id)]["users"][str(message.author.id)][
        "score"
    ]
    # guild_data[str(ctx.guild.id)]["users"][str(ctx.author.id)]["score"]
    for k, v in scores.items():
        if v >= attributeThresholdsExtreme[k]:
            guild_data[str(message.guild.id)]["users"][str(message.author.id)][
                "score"
            ] = (user_score - 2)
            await message.delete()
            await message.channel.send("That's a bit too far.")
            await dump_data()
        elif v >= attributeThresholds[k]:
            guild_data[str(message.guild.id)]["users"][str(message.author.id)][
                "score"
            ] = (user_score - 1)
            await dump_data()
    # await message.reply(f"{scores}")


async def chat_bot(message):
    if message.attachments or message.author.bot:
        return
    if message.channel.id == guild_data[str(message.guild.id)]["chat_channel"]:
        msg = await message.channel.send("Hannigan is thinking...")
        bard_response = bard_bot.ask(message.content)
        await msg.edit(content=bard_response["content"])


# Buttons


class Choices(discord.ui.View):
    def __init__(self, bard_response):
        super().__init__()
        self.bard_response = bard_response

    @discord.ui.button(label="Response ")
    async def response(
        self, button: discord.ui.Button, interaction: discord.Interaction
    ):
        for choice in self.bard_response["choices"]:
            if choice["label"] == button.label:
                await interaction.response.edit_message(choice["content"])


# Events


@bot.event
async def on_ready():
    for guild in bot.guilds:
        if not any(str(guild.id) in d for d in guild_data):
            # print(guild.id)
            guild_data[str(guild.id)] = {}
            guild_data[str(guild.id)]["users"] = {}
            with open("data/guild_data.json", "w") as f:
                json.dump(guild_data, f)
    print(f"Logged in as {bot.user}!")


@bot.event
async def on_message(message):
    await check_message(message)
    await chat_bot(message)

    # print(message.author + "said: " + message.content)


@bot.event
async def on_slash_command_error(ctx, error):
    await ctx.response.send_message(
        "There was an error with your command. Please try again."
    )
    print(error)


@bot.event
async def on_guild_join(guild):
    for guild in bot.guilds:
        if not any(str(guild.id) in d for d in guild_data):
            # print(guild.id)
            guild_data[str(guild.id)] = {}
            guild_data[str(guild.id)]["users"] = {}
            with open("data/guild_data.json", "w") as f:
                json.dump(guild_data, f)
    guild_data[str(guild.id)] = {}
    channel_list = guild.text_channels
    embed = discord.Embed(
        title=f"Thanks for inviting me to {guild.name}!",
        timestamp=discord.utils.utcnow(),
    )
    await channel_list[0].send(embed=embed)


# Commands


@bot.slash_command(name="bard", description="Chat with Google Bard!")
async def bard(ctx, message: str):
    await ctx.response.defer()
    bard_response = bard_bot.ask(message)
    # if bard_response["choices"] > 1:
    #     await ctx.respond(bard_response["content"], view=Choices(bard_response))
    # else:
    #     await ctx.respond(bard_response["content"])
    await ctx.respond(bard_response["content"])

    with open("logs.txt", "a") as f:
        f.write(str(bard_response) + "\n")


@bot.slash_command(
    name="setup",
    description="Setup a channel for the active chatbot.",
)
async def setup(ctx):
    if "chat_channel" not in guild_data[str(ctx.guild.id)]:
        guild_data[str(ctx.guild.id)]["chat_channel"] = ctx.channel.id
        await dump_data()
        await ctx.respond("Channel setup! You can now chat with Google Bard.")
    else:
        channel = guild_data[str(ctx.guild.id)]["chat_channel"]
        await ctx.respond(f"This server is already setup! The channel is <#{channel}>")


@bot.slash_command(
    name="edit_setup",
    description="Change the chatbot channel.",
)
async def edit_setup(ctx):
    guild_data[str(ctx.guild.id)]["chat_channel"] = ctx.channel.id
    await dump_data()
    await ctx.respond("Channel setup! You can now chat with Google Bard.")


@bot.slash_command(name="check_score", description="Check your social score.")
async def check_score(ctx):
    score = guild_data[str(ctx.guild.id)]["users"][str(ctx.author.id)]["score"]
    await ctx.respond(f"Your score is {score}")


@bot.slash_command(name="help", description="Get help with the bot.")
async def help(ctx):
    await ctx.respond(
        "If you need to setup the chatbot, run `/setup` in the desired channel. If you need to change the chatbot channel, run `/edit_setup` in the desired channel. If you need to check your social score, run `/check_score`. More information coming soon..."
    )


@bot.slash_command(name="leaderboard", description="Get the leaderboard.")
async def leaderboard(ctx):
    data = guild_data[str(ctx.guild.id)]["users"]
    sorted_data = sorted(data.items(), key=lambda x: x[1]["score"], reverse=True)
    embed = discord.Embed(
        title="Leaderboard",
        description="The top 10 users with the highest social credit.",
        timestamp=discord.utils.utcnow(),
    )
    for i in range(10 if len(sorted_data) > 10 else len(sorted_data)):
        if i < len(sorted_data):
            embed.add_field(
                name=f"{i+1}. {bot.get_user(int(sorted_data[i][0]))}",
                value=f"Score: {sorted_data[i][1]['score']}",
            )
    await ctx.respond(embed=embed)


@bot.slash_command(name="ping", description="Get the bot's ping.")
async def ping(ctx):
    await ctx.respond(f"Pong! {round(bot.latency * 1000)}ms")


@bot.slash_command(name="invite", description="Get the bot's invite link.")
async def invite(ctx):
    await ctx.respond(
        "https://discord.com/oauth2/authorize?client_id=1099363267731804202&scope=bot&permissions=8"
    )


# Run bot
bot.run(os.getenv("TOKEN"))
