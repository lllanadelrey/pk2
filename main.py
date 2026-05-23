import asyncio
import random
import re
import os
import discord
import pokebase as pb
from dotenv import load_dotenv

load_dotenv()

PREFIX = os.getenv("PREFIX", "!")
token_string = os.getenv("TOKEN", "")

TOKENS = [t.strip() for t in token_string.split(",") if t.strip()]

if not TOKENS:
    print("Erro: Nenhum token encontrado. Verifique seu arquivo .env!")
    exit()

claimed_channels = set()
pokemon_list = []

try:
    recursos_pokemon = pb.APIResourceList('pokemon')
    for p in recursos_pokemon:
        nome = p['name'].lower().replace('-', ' ')
        pokemon_list.append(nome)
except Exception as e:
    print(f"Erro ao baixar a lista de Pokémon: {e}")

def solve(message):
    hint = []
    for i in range(15, len(message) - 1):
        if message[i] != "\\":
            hint.append(message[i])
            
    hint_string = "".join(hint)
    hint_replaced = hint_string.replace("_", ".")
    
    pattern = re.compile(f"^{hint_replaced}$", re.IGNORECASE)
    solution = [pokemon for pokemon in pokemon_list if pattern.match(pokemon)]
    
    return solution

class AutoCatcher(discord.Client):
    def __init__(self):
        super().__init__()
        self.target_channel_id = None
        self.captcha = True

    async def on_ready(self):
        print(f'[+] Logado na conta: {self.user.name} | Aguardando comando .ac em um canal')

    async def on_message(self, message):
        if message.content == ".ac":
            if self.target_channel_id is None and message.channel.id not in claimed_channels:
                self.target_channel_id = message.channel.id
                claimed_channels.add(message.channel.id)
                await message.channel.send(f"Conta {self.user.name} vinculada a este canal.")
            return

        if self.target_channel_id is None or message.channel.id != self.target_channel_id:
            return

        if message.author == self.user:
            return

        if message.content == f"{PREFIX}iniciar":
            self.captcha = True
            await message.channel.send(f"Auto catcher da conta {self.user.name} retomado.")
            return

        if message.content == f"{PREFIX}parar":
            self.captcha = False
            await message.channel.send(f"Auto catcher da conta {self.user.name} pausado.")
            return

        if message.author.id == 854233015475109888 and self.captcha:
            if message.content.startswith("@Pokétwo#8236 ev m shoot"):
                resultado = message.content[len("@Pokétwo#8236 ev m shoot"):]
                await asyncio.sleep(5)
                await message.channel.send(f"<@716390085896962058> ev m shoot{resultado}")

        if message.author.id == 716390085896962058 and self.captcha:
            if message.embeds:
                embed_title = message.embeds[0].title
                if embed_title and 'wild pokémon has appeared!' in embed_title.lower():
                    await asyncio.sleep(1)
                    await message.channel.send('<@716390085896962058> hint')

            content = message.content
            
            if 'The pokémon is ' in content:
                solucoes = solve(content)
                if solucoes:
                    for i in solucoes:
                        await asyncio.sleep(random.randint(3, 4))
                        await message.channel.send(f'<@716390085896962058> c {i.lower()}')

            elif 'human' in content.lower():
                self.captcha = False
                await message.channel.send(f"Captcha detectado na conta {self.user.name}. O bot foi pausado.\nApós resolver, utilize o comando `{PREFIX}iniciar` para retornar.\nLink: https://verify.poketwo.net/captcha/{self.user.id}")

async def main():
    bots = [AutoCatcher() for _ in TOKENS]
    
    tasks = []
    for bot, token in zip(bots, TOKENS):
        tasks.append(bot.start(token))
        
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDesligando bots...")
