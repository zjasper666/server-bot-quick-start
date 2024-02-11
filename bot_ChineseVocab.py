"""

BOT_NAME="ChineseVocab"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

"""
from __future__ import annotations

from typing import AsyncIterable

import fastapi_poe as fp
from modal import Image, Stub, asgi_app
from modal import Dict, Image, Stub, asgi_app
import pandas as pd

stub = Stub("poe-bot-ChineseVocab")
stub.my_dict = Dict.new()

df = pd.read_csv("chinese_words.csv")

def get_conversation_key(conversation_id):
    return f"ChineseVocab-cid-to-word-{conversation_id}"

class GPT35TurboAllCapsBot(fp.PoeBot):
    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:
        conversation_key = get_conversation_key(request.conversation_id)
        if conversation_key in stub.my_dict:
            word = stub.my_dict[conversation_key]
        else:
            word = list(df.sample(n=1)["simplified"])[0]
            stub.my_dict[conversation_key] = word
            
        yield self.text_event(word)

        # async for msg in fp.stream_request(
        #     request, "GPT-3.5-Turbo", request.access_key
        # ):
        #     yield msg.model_copy(update={"text": msg.text.upper()})

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(server_bot_dependencies={"GPT-3.5-Turbo": 1})


REQUIREMENTS = ["fastapi-poe==0.0.24", "pandas"]
image = Image.debian_slim().pip_install(*REQUIREMENTS).copy_local_file("chinese_words.csv", "/root/chinese_words.csv")


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    bot = GPT35TurboAllCapsBot()
    # Optionally, provide your Poe access key here:
    # 1. You can go to https://poe.com/create_bot?server=1 to generate an access key.
    # 2. We strongly recommend using a key for a production bot to prevent abuse,
    # but the starter examples disable the key check for convenience.
    # 3. You can also store your access key on modal.com and retrieve it in this function
    # by following the instructions at: https://modal.com/docs/guide/secrets
    # POE_ACCESS_KEY = ""
    # app = make_app(bot, access_key=POE_ACCESS_KEY)
    app = fp.make_app(bot, allow_without_key=True)
    return app
