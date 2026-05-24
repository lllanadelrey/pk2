import asyncio
import random
import re
import os
import io
import json
import gc
import warnings
import aiohttp
import torch
import torch.nn as nn
import discord
import pokebase as pb
from torchvision import models, transforms
from PIL import Image
from dotenv import load_dotenv


warnings.filterwarnings("ignore")
os.environ["NNPACK_INITIALIZED"] = "1"

load_dotenv()

torch.set_num_threads(1)

PREFIX = os.getenv("PREFIX", "!")
token_string = os.getenv("TOKEN", "")

TOKENS = [t.strip() for t in token_string.split(",") if t.strip()]

if not TOKENS:
    print("Erro: Nenhum token encontrado no .env.")
    exit()

claimed_channels = set()
pokemon_list = []

print("Baixando lista de pokemon...")
try:
    recursos_pokemon = pb.APIResourceList('pokemon')
    for p in recursos_pokemon:
        nome = p['name'].lower().replace('-', ' ')
        pokemon_list.append(nome)
    print(f"{len(pokemon_list)} pokemon baixados.")
except Exception as e:
    print(f"Erro ao baixar pokemon: {e}")

print("Carregando modelo de IA...")
try:
    with open('class_names.json', 'r', encoding='utf-8') as f:
        class_names = json.load(f)
    print(f"{len(class_names)} nomes carregados.")

    model = models.mobilenet_v3_small(weights=None)
    num_ftrs = model.classifier[3].in_features
    model.classifier[3] = nn.Linear(num_ftrs, len(class_names))

    state_dict = torch.load('pokemon_model_lite.pth', map_location='cpu')
    model.load_state_dict(state_dict)
    model.eval()
    print("Modelo montado e carregado na CPU com sucesso.")

except Exception as e:
    print(f"Falha ao montar/carregar modelo: {e}")
    model = None
    class_names = {}
    
print("-" * 50)

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
            
        idx = class_idx.item()
        if isinstance(class_names, list):
            predicted_class = class_names[idx] if idx < len(class_names) else None
        else:
            predicted_class = class_names.get(str(idx), None)
            
        conf_value = confidence.item()
        
        del image, tensor, outputs, probabilities
        gc.collect() 
        
        return predicted_class, conf_value

    except Exception as e:
        print(f"Erro na predicao: {e}")
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
        print(f'Logado: {self.user.name} | Aguardando .ac')

    async def on_message(self, message):
        if message.content == ".ac":
            if self.target_channel_id is None and message.channel.id not in claimed_channels:
                self.target_channel_id = message.channel.id
                claimed_channels.add(message.channel.id)
                await message.channel.send(f"Conta {self.user.name} vinculada.")
            return

        if self.target_channel_id is None or message.channel.id != self.target_channel_id:
            return

        if message.author == self.user:
            return

        if message.content == f"{PREFIX}iniciar":
            self.captcha = True
            await message.channel.send(f"Auto catcher retomado: {self.user.name}.")
            return

        if message.content == f"{PREFIX}parar":
            self.captcha = False
            await message.channel.send(f"Auto catcher pausado: {self.user.name}.")
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
                        print(f"[{self.user.name}] Spawn detectado. Usando IA...")
                        try:
                            async with aiohttp.ClientSession() as session:
                                async with session.get(image_url) as resp:
                                    if resp.status == 200:
                                        image_bytes = await resp.read()
                                        
                                        pokemon_pred, conf = await predict_pokemon_lite(image_bytes)
                                        
                                        if pokemon_pred and conf >= 0.78:
                                            print(f"[{self.user.name}] IA: {pokemon_pred} ({conf*100:.1f}%). Capturando.")
                                            await asyncio.sleep(random.uniform(1.5, 3.0))
                                            await message.channel.send(f'<@716390085896962058> c {pokemon_pred.lower()}')
                                            catch_success = True
                                        else:
                                            palpite = pokemon_pred if pokemon_pred else "Nenhum"
                                            print(f"[{self.user.name}] IA insegura: {palpite} ({conf*100:.1f}%). Usando hint.")
                        except Exception as e:
                            print(f"[{self.user.name}] Erro na IA: {e}")
                    
                    if not catch_success:
                        await asyncio.sleep(1)
                        await message.channel.send('<@716390085896962058> hint')

            content = message.content
            
            if 'The pokémon is ' in content:
                solucoes = solve(content)
                if solucoes:
                    print(f"[{self.user.name}] Hint: {solucoes}")
                    for i in solucoes:
                        await asyncio.sleep(random.randint(3, 4))
                        await message.channel.send(f'<@716390085896962058> c {i.lower()}')
                else:
                    print(f"[{self.user.name}] Hint nao encontrado.")

            elif 'human' in content.lower():
                self.captcha = False
                print(f"[{self.user.name}] Captcha detectado. Pausado.")
                await message.channel.send(f"Captcha na conta {self.user.name}. Bot pausado.\nApós resolver, use {PREFIX}iniciar.\nLink: https://verify.poketwo.net/captcha/{self.user.id}")

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
        print("\nDesligando...")
