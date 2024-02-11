"""

BOT_NAME="ChineseVocab"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

"""
from __future__ import annotations

from typing import AsyncIterable

import fastapi_poe as fp
import pandas as pd
from modal import Dict, Image, Stub, asgi_app

stub = Stub("poe-bot-ChineseVocab")
stub.my_dict = Dict.new()

df = pd.read_csv("chinese_words.csv")  # downloaded from wikipedia
# see also https://www.mdbg.net/chinese/dictionary?page=cedict

df = df[df["simplified"].str.len() > 1]

TEMPLATE_STARTING_REPLY = """
Your word is {word}

Please provide the pinyin pronounication and meaning of the word.
Format your pinyin in this way: ni2 hao3
""".strip()

SYSTEM_PROMPT = """
You will test the user on the definition of a Chinese word.

The user will need to provide the pinyin pronounication and meaning of the word.
The pinyin provided needs to have the tones annotated.
The meaning provided should be unambiguous.

The word is {word}
The correct pronounication is {pinyin}
The meaning is {meaning}

Rules
- If the pronounciation is not provided, ask for the pronounciation from the user.
- If the the user provides the pinyin without the tune (e.g. ni hao), ask the user for the tones. DO NOT PROVIDE THE TONES.
    - An example follow-up would be "Please provide the tones for <user input>. "
- If the meaning is not provided, ask for the meaning from the user. DO NOT PROVIDE THE MEANING.
- If the meaning is wrong or ambiguous, ask the user to try again. DO NOT PROVIDE THE MEANING.
- ONLY after both the correct pinyin with tones and meaning is provided, reveal the correct pinyin and pronounciation.

REMINDER
- DO NOT GIVE THE ANSWER UNLESS EXPLICTLY ASKED BY THE USER
- CHECK WHETHER THE USER HAS PROVIDED THE TONES FOR THE PHRASE
"""


def get_conversation_word_key(conversation_id):
    return f"ChineseVocab-word-{conversation_id}"


class GPT35TurboAllCapsBot(fp.PoeBot):
    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:
        response_content_type = "text/plain"
        yield fp.MetaResponse(
            text="",
            content_type=response_content_type,
            linkify=True,
            refetch_settings=False,
            suggested_replies=False,
        )
        conversation_word_key = get_conversation_word_key(request.conversation_id)
        if conversation_word_key in stub.my_dict:
            word_info = stub.my_dict[conversation_word_key]
        else:
            word_info = df.sample(n=1).to_dict(orient="records")[0]
            stub.my_dict[conversation_word_key] = word_info
            yield self.text_event(
                TEMPLATE_STARTING_REPLY.format(word=word_info["simplified"])
            )
            return

        request.query = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT.format(
                    word=word_info["simplified"],
                    pinyin=word_info["pinyin"],
                    meaning=word_info["translation"],
                ),
            }
        ] + request.query
        request.logit_bias = {"13080": 10, "308": 5, "2483": 5}  # " ni"  # " n"  # "i2"
        async for msg in fp.stream_request(
            request, "GPT-3.5-Turbo", request.access_key
        ):
            yield msg.model_copy()

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(server_bot_dependencies={"GPT-3.5-Turbo": 1})


REQUIREMENTS = ["fastapi-poe==0.0.24", "pandas"]
image = (
    Image.debian_slim()
    .pip_install(*REQUIREMENTS)
    .copy_local_file("chinese_words.csv", "/root/chinese_words.csv")
)


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
