"""

BOT_NAME="ChineseVocab"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

"""

from __future__ import annotations

import unicodedata
from typing import AsyncIterable

import fastapi_poe as fp
import pandas as pd
from modal import Dict, Image, Stub, asgi_app

stub = Stub("poe-bot-ChineseVocab")
stub.my_dict = Dict.new()

df = pd.read_csv("chinese_words.csv")
# using https://github.com/krmanik/HSK-3.0-words-list/tree/main/HSK%20List
# see also https://www.mdbg.net/chinese/dictionary?page=cedict

df = df[df["simplified"].str.len() > 1]

TEMPLATE_STARTING_REPLY = """
The word sampled from HSK level {level} is

# {word}

Please provide the **pinyin** and a **meaning** of the word.
""".strip()

SYSTEM_TABULATION_PROMPT = """
You will test the user on the definition of a Chinese word.

The user will need to provide the pinyin pronounication and meaning of the word.
The pinyin provided needs to have the tones annotated.

The word is {word}
The reference pinyin is {pinyin}
The reference meaning is {meaning}

The user is expected to reply the pinyin and meaning.

When you receive the pinyin and meaning, reply with the following table. DO NOT ADD ANYTHING ELSE.

For example, if the user replies "mei2 shou1 confiscate", your reply will be

|             | Pinyin      | Meaning                 |
| ----------- | ----------- | ----------------------- |
| Your answer | mei2 shou1  | confiscate              |
| Reference   | mo4 shou1   | to confiscate, to seize |

REMINDER
- ALWAYS REPLY WITH THE TABLE.
- DO NOT ADD ANYTHING ELSE AFTER THE TABLE.
"""

JUDGE_SYSTEM_PROMPT = """
You will judge the whether the user (in the row "your answer") has provided the correct pinyin, tone and meaning.

{reply}

You will start your reply with exactly one of, only based on the alphabets provided, ignoring the numerical tones

- The pinyin is correct.
- The pinyin is incorrect.
- The pinyin is missing.

You will exactly reply with one of, based on the numerical tone provided

- The numerical tone is correct.
- The numerical tone is incorrect
- The numerical tone is missing.

You will exactly reply with one of, based on the meaning provided

- The meaning is correct.
- The meaning is missing.
- The meaning is incorrect.

REMINDER
- Follow the reply template.
- Do not add anything else in your reply.
- The reference meaning is not exhaustive. Accept the user's answer if it is correct, even it is not in the reference meaning.
"""


def get_user_level_key(user_id):
    return f"ChineseVocab-level-{user_id}"


def get_conversation_word_key(conversation_id):
    return f"ChineseVocab-word-{conversation_id}"


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
        conversation_word_key = get_conversation_word_key(request.conversation_id)
        conversation_submitted_key = get_conversation_submitted_key(
            request.conversation_id
        )

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
            level = 3
            stub.my_dict[user_level_key] = level

        if conversation_word_key in stub.my_dict:
            word_info = stub.my_dict[conversation_word_key]
        else:
            word_info = (
                df[(df["level"] == level) & (df["exclude"] == False)]
                .sample(n=1)
                .to_dict(orient="records")[0]
            )
            stub.my_dict[conversation_word_key] = word_info
            yield self.text_event(
                TEMPLATE_STARTING_REPLY.format(
                    word=word_info["simplified"], level=word_info["level"]
                )
            )
            return

        request.query = [
            {
                "role": "system",
                "content": SYSTEM_TABULATION_PROMPT.format(
                    word=word_info["simplified"],
                    pinyin=word_info["numerical_pinyin"],
                    meaning=word_info["translation"],
                ),
            }
        ] + request.query
        request.logit_bias = {"2746": -5, "36821": -10}  # "If"  # " |\n\n"

        bot_reply = ""
        async for msg in fp.stream_request(request, "ChatGPT", request.access_key):
            bot_reply += msg.text
            yield msg.model_copy()

        yield self.text_event("\n\n")

        if "-----" in bot_reply:
            stub.my_dict[conversation_submitted_key] = True
            request.query = [
                {"role": "user", "content": JUDGE_SYSTEM_PROMPT.format(reply=bot_reply)}
            ]
            judge_reply = ""
            async for msg in fp.stream_request(request, "ChatGPT", request.access_key):
                judge_reply += msg.text
                yield self.text_event(msg.text)

            if (
                "pinyin is correct" in judge_reply
                and "tone is correct" in judge_reply
                and "meaning is correct" in judge_reply
            ):
                stub.my_dict[user_level_key] = stub.my_dict[user_level_key] + 1
            elif judge_reply.count("missing") >= 3:
                stub.my_dict[user_level_key] = stub.my_dict[user_level_key] - 1

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(
            server_bot_dependencies={"ChatGPT": 2},
            introduction_message="Say 'start' to get the Chinese word.",
        )


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
