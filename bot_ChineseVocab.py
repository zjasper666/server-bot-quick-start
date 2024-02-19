"""

BOT_NAME="ChineseVocab"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

There are three states in the conversation
- Before getting the problem
- After getting the problem, before making a submission
- After making a submission
"""

from __future__ import annotations

from typing import AsyncIterable

import fastapi_poe as fp
import pandas as pd
from fastapi_poe.types import PartialResponse
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
""".strip()

JUDGE_SYSTEM_PROMPT = """
You will judge the whether the user (in the row "your answer") has provided the correct pinyin, tone and meaning for the word {word}.

{reply}

You will start your reply with exactly one of, only based on the alphabets provided, ignoring the numerical tones

- The pinyin is correct.
- The pinyin is incorrect.
- The pinyin is missing.

You will exactly reply with one of, based on the numerical tone provided

- The numerical tone is correct.
- The numerical tone is incorrect
- The numerical tone is missing.

You will exactly reply with one of

- The meaning is correct.
- The meaning is missing.
- The meaning is incorrect.

REMINDER
- Follow the reply template.
- Do not add anything else in your reply.
- We consider the meaning correct if it matches any of the reference meanings.
- The reference meaning is not exhaustive. Accept the user's answer if it is correct, even it is not in the reference meaning
"""

FREEFORM_SYSTEM_PROMPT = """
You are a patient Chinese language teacher.

You will guide the conversation in ways that maximizes the learning of the Chinese language.

The examples you provide will be as diverse as possible.
"""

PASS_STATEMENT = "I will pass this word."

NEXT_STATEMENT = "I want another word."


def get_user_level_key(user_id):
    return f"ChineseVocab-level-{user_id}"


def get_conversation_word_key(conversation_id):
    return f"ChineseVocab-word-{conversation_id}"


def get_conversation_submitted_key(conversation_id):
    return f"ChineseVocab-submitted-{conversation_id}"


class GPT35TurboAllCapsBot(fp.PoeBot):
    async def get_response(
        self, request: fp.QueryRequest
    ) -> AsyncIterable[fp.PartialResponse]:
        user_level_key = get_user_level_key(request.user_id)
        conversation_word_key = get_conversation_word_key(request.conversation_id)
        conversation_submitted_key = get_conversation_submitted_key(
            request.conversation_id
        )
        last_user_reply = request.query[-1].content
        print(last_user_reply)

        # reset if the user passes or asks for the next statement
        if last_user_reply in (NEXT_STATEMENT, PASS_STATEMENT):
            if conversation_word_key in stub.my_dict:
                stub.my_dict.pop(conversation_word_key)
            if conversation_submitted_key in stub.my_dict:
                stub.my_dict.pop(conversation_submitted_key)

        # retrieve the level of the user
        # TODO(when conversation starter is ready): jump to a specific level
        if user_level_key in stub.my_dict:
            level = stub.my_dict[user_level_key]
            level = max(1, level)
            level = min(7, level)
        else:
            level = 1
            stub.my_dict[user_level_key] = level

        # for new conversations, sample a problem
        if conversation_word_key not in stub.my_dict:
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
            yield PartialResponse(text=PASS_STATEMENT, is_suggested_reply=True)
            return

        # if the submission is already made, continue as per normal
        if conversation_submitted_key in stub.my_dict:
            request.query = [
                {"role": "system", "content": FREEFORM_SYSTEM_PROMPT}
            ] + request.query
            bot_reply = ""
            async for msg in fp.stream_request(request, "ChatGPT", request.access_key):
                bot_reply += msg.text
                yield msg.model_copy()
            print(bot_reply)
            return

        # otherwise, disable suggested replies
        yield fp.MetaResponse(
            text="",
            content_type="text/markdown",
            linkify=True,
            refetch_settings=False,
            suggested_replies=False,
        )

        # retrieve the previously cached word
        word_info = stub.my_dict[conversation_word_key]
        word = word_info["simplified"]  # so that this can be used in f-string

        # tabluate the user's submission
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
        request.temperature = 0
        request.logit_bias = {"2746": -5, "36821": -10}  # "If"  # " |\n\n"

        bot_reply = ""
        async for msg in fp.stream_request(request, "ChatGPT", request.access_key):
            bot_reply += msg.text
            yield msg.model_copy()

        yield self.text_event("\n\n")

        # make a judgement on correctness
        if "-----" in bot_reply:
            stub.my_dict[conversation_submitted_key] = True
            request.query = [
                {
                    "role": "user",
                    "content": JUDGE_SYSTEM_PROMPT.format(reply=bot_reply, word=word),
                }
            ]
            request.temperature = 0
            judge_reply = ""
            async for msg in fp.stream_request(
                request, "GPT-3.5-Turbo", request.access_key
            ):
                judge_reply += msg.text
                # yield self.text_event(msg.text)

            yield self.text_event("\n\n")
            yield self.text_event(
                "You can reset the context (brush icon on bottom left) if you want a new word.\nYou can also follow up with asking more about the word."
            )

            print(judge_reply, judge_reply.count(" correct"))
            if (
                "pinyin is correct" in judge_reply
                and "tone is correct" in judge_reply
                and "meaning is correct" in judge_reply
                and word_info["numerical_pinyin"] in last_user_reply
            ):
                stub.my_dict[user_level_key] = level + 1
            elif (
                judge_reply.count(" correct") == 0
            ):  # NB: note the space otherwise it matches incorrect
                stub.my_dict[user_level_key] = level - 1

            # deliver suggested replies
            yield PartialResponse(
                text=f"What are some ways to use {word} in a sentence?",
                is_suggested_reply=True,
            )
            yield PartialResponse(
                text=f"What are some words related to {word}?", is_suggested_reply=True
            )
            yield PartialResponse(text=NEXT_STATEMENT, is_suggested_reply=True)
        else:
            yield PartialResponse(text=NEXT_STATEMENT, is_suggested_reply=True)

    async def get_settings(self, setting: fp.SettingsRequest) -> fp.SettingsResponse:
        return fp.SettingsResponse(
            server_bot_dependencies={"ChatGPT": 1, "GPT-3.5-Turbo": 1},
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
