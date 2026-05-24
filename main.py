import asyncio
import random
import re
import os
import io
import json
import gc
import aiohttp
import torch
import discord
import pokebase as pb
from torchvision import transforms
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

torch.set_num_threads(1)

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

try:
    with open('class_names.json', 'r', encoding='utf-8') as f:
        class_names = json.load(f)
except Exception:
    class_names = {}

try:
    model = torch.jit.load('pokemon_model_lite.pth', map_location='cpu')
    model.eval()
except Exception:
    model = None

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
])

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

def _predict_sync(image_bytes):
    if model is None or not class_names:
        return None, 0.0

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert('RGB')
        tensor = transform(image).unsqueeze(0)
        
        with torch.no_grad():
            outputs = model(tensor)
            probabilities = torch.nn.functional.softmax(outputs[0], dim=0)
            confidence, class_idx = torch.max(probabilities, dim=0)
            
        predicted_class = class_names.get(str(class_idx.item()), None)
        conf_value = confidence.item()
        
        del image, tensor, outputs, probabilities
        gc.collect() 
        
        return predicted_class, conf_value

    except Exception:
        gc.collect()
        return None, 0.0

async def predict_pokemon_lite(image_bytes):
    return await asyncio.to_thread(_predict_sync, image_bytes)

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
                    image_url = message.embeds[0].image.url
                    catch_success = False

                    if model is not None and image_url:
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(image_url) as resp:
                                    if resp.status == 200:
                                        image_bytes = await resp.read()
                                        
                                        pokemon_pred, conf = await predict_pokemon_lite(image_bytes)
                                        
                                        if pokemon_pred and conf >= 0.78:
                                            await asyncio.sleep(random.uniform(1.5, 3.0))
                                            await message.channel.send(f'<@716390085896962058> c {pokemon_pred.lower()}')
                                            catch_success = True
                        except Exception:
                            pass
                    
                    if not catch_success:
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
