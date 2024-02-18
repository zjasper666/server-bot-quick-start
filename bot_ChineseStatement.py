"""

BOT_NAME="ChineseStatement"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

"""

from __future__ import annotations

import random
import re
import unicodedata
from typing import AsyncIterable

import fastapi_poe as fp
from fastapi_poe.types import PartialResponse
from modal import Dict, Image, Stub, asgi_app

stub = Stub("poe-bot-ChineseStatement")
stub.my_dict = Dict.new()

with open("chinese_sentences.txt") as f:
    srr = f.readlines()

pattern = r"A\.\d\s"  # e.g. "A.1 "

level_to_statements = []

for line in srr:
    if re.match(pattern, line):
        level_to_statements.append([])
    if "/" in line:
        continue
    if line == "\n":
        continue
    if "【" in line:
        continue
    if "（" in line:
        continue
    if "A." in line:
        continue
    if "。" not in line and "？" not in line:
        continue
    if "甲" in line or "乙" in line:
        continue
    if len(line) > 50:
        continue
    level_to_statements[-1].append(line.strip())


TEMPLATE_STARTING_REPLY = """
The statement sampled from HSK level {level} is

# {statement}

Please translate the sentence.
""".strip()

SYSTEM_TABULATION_PROMPT = """
You will test the user on the translation of a Chinese sentence.

The statement is {statement}

You will whether the user's translation captures the full meaning of the sentence.

If the user has  user's translation captures the full meaning of the sentence, end you reply with
- Your translation has captured the full meaning of the sentence.
""".strip()


def get_user_level_key(user_id):
    return f"ChineseVocab-level-{user_id}"


def get_conversation_statement_key(conversation_id):
    return f"ChineseVocab-statement-{conversation_id}"


def get_conversation_submitted_key(conversation_id):
    return f"ChineseVocab-submitted-{conversation_id}"


def to_tone_number(s):
    table = {0x304: ord("1"), 0x301: ord("2"), 0x30C: ord("3"), 0x300: ord("4")}
    return unicodedata.normalize("NFD", s).translate(table)


class GPT35TurboAllCapsBot(fp.PoeBot):
    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:
        user_level_key = get_user_level_key(request.user_id)
        conversation_statement_key = get_conversation_statement_key(
            request.conversation_id
        )
        conversation_submitted_key = get_conversation_submitted_key(
            request.conversation_id
        )
        last_user_reply = request.query[-1].content
        print(last_user_reply)

        if conversation_submitted_key not in stub.my_dict:
            yield fp.MetaResponse(
                text="",
                content_type="text/markdown",
                linkify=True,
                refetch_settings=False,
                suggested_replies=False,
            )

        if user_level_key in stub.my_dict:
            level = stub.my_dict[user_level_key]
            level = max(1, level)
            level = min(7, level)
        else:
            level = 1
            stub.my_dict[user_level_key] = level

        if conversation_statement_key in stub.my_dict:
            statement_info = stub.my_dict[conversation_statement_key]
            statement = statement_info[
                "statement"
            ]  # so that this can be used in f-string
        else:

            statement = random.choice(level_to_statements[level])
            statement_info = {"statement": statement}
            stub.my_dict[conversation_statement_key] = statement_info
            yield self.text_event(
                TEMPLATE_STARTING_REPLY.format(
                    statement=statement_info["statement"], level=level
                )
            )
            return

        request.query = [
            {
                "role": "system",
                "content": SYSTEM_TABULATION_PROMPT.format(statement=statement),
            }
        ] + request.query
        request.temperature = 0
        request.logit_bias = {"2746": -5, "36821": -10}  # "If"  # " |\n\n"

        bot_reply = ""
        async for msg in fp.stream_request(request, "ChatGPT", request.access_key):
            bot_reply += msg.text
            yield msg.model_copy()

        if conversation_submitted_key not in stub.my_dict:
            stub.my_dict[conversation_submitted_key] = True
            if "has captured the full meaning" in bot_reply:
                stub.my_dict[user_level_key] = level + 1
            else:
                stub.my_dict[user_level_key] = level - 1

            yield PartialResponse(
                text=f"What are some other sentences of a similar structure?",
                is_suggested_reply=True,
            )

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(
            server_bot_dependencies={"ChatGPT": 1, "GPT-3.5-Turbo": 1},
            introduction_message="Say 'start' to get the sentence to translate.",
        )


REQUIREMENTS = ["fastapi-poe==0.0.24", "pandas"]
image = (
    Image.debian_slim()
    .pip_install(*REQUIREMENTS)
    .copy_local_file("chinese_sentences.txt", "/root/chinese_sentences.txt")
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
