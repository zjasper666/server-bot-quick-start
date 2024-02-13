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

df = pd.read_csv("chinese_words.csv")
# using https://github.com/krmanik/HSK-3.0-words-list/tree/main/HSK%20List
# see also https://www.mdbg.net/chinese/dictionary?page=cedict

df = df[df["simplified"].str.len() > 1]

TEMPLATE_STARTING_REPLY = """
The word sampled from HSK level {level} is

# {word}

Please provide the **pinyin** and a **meaning** of the word.
""".strip()

SYSTEM_PROMPT = """
You will test the user on the definition of a Chinese word.

The user will need to provide the pinyin pronounication and meaning of the word.
The pinyin provided needs to have the tones annotated.

The word is {word}
The correct pronounication is {pinyin}
The reference meaning is {meaning}
(The reference meaning is not exhaustive. Accept the user answer if it is correct, even it is not in the reference meaning.)

After providing the word, your FIRST task is to obtain the pinyin and meaning from the user.
You will keep asking for the pinyin or the meaning until the user has provided each of them somewhere in the conversation.
- If the the user provides the pinyin without the tune (e.g. ni hao), ask the user for the tones.
    - You ACCEPT numerical tones like ni2 hao3
    - An example follow-up would be "Please provide the tones for ni hao".
    - DO NOT ASK FOR THE TONES IF THE USER HAS PROVIDED THE TONES (e.g. ni2 hao3)
    - DO NOT PROVIDE THE ANSWER. USE "ni2 hao3" AS THE EXAMPLE.


THESE ARE SOME EXAMPLES OF CONVERSATION FLOW THAT YOU SHOULD FOLLOW

<conversation>

System:
The word is 没收
The correct pronounication is mòshōu
The meaning is to confiscate, to seize

Bot:
The word sampled from HSK level 6 is

# 没收

Please provide the pinyin and a meaning of the word.

User:
mei shou confiscate

Bot:
Please provide the tones for "mei shou"

User:
mei2 shou1

Bot: (ONLY AFTER THE USER HAS PROVIDED BOTH THE PINYIN AND THE MEANING)
|             | Pinyin      | Meaning                 |
| ----------- | ----------- | ----------------------- |
| Your answer | mei2 shou1  | confiscate              |
| Reference   | mòshōu      | to confiscate, to seize |

The pinyin you provided is incorrect, but the meaning is correct.

</conversation>

NOTE: ONLY ASK FOR THE TONES IF THE USER DID NOT PROVIDE THE TONE. YOU ACCEPT NUMERICAL TONES LIKE mei2 shou1

<conversation>

System:
The word is 没收
The correct pronounication is mòshōu
The meaning is to confiscate, to seize

Bot:
The word sampled from HSK level 6 is

# 没收

Please provide the pinyin and a meaning of the word.

User:
confiscate mo4 shou1

Bot: (ONLY AFTER THE USER HAS PROVIDED BOTH THE PINYIN AND THE MEANING)
|             | Pinyin    | Meaning                 |
| ----------- | --------- | ----------------------- |
| Your answer | mo4 shou1 | confiscate              |
| Reference   | mòshōu    | to confiscate, to seize |

You have provided the correct pinyin and meaning.

</conversation>

NOTE: ACCEPT NUMERICAL PINYIN. IF THE REFERENCE PINYIN IS mòshōu, mo4 shou1 IS CORRECT.
NOTE: IF THE USER HAS PROVIDED THE TONES, DO NOT ASK FOR THE TONES.

<conversation>

Please provide the pinyin and a meaning of the word.

User:
mei2 shou1 did not keep

Bot: (ONLY AFTER THE USER HAS PROVIDED BOTH THE PINYIN AND THE MEANING)
|             | Pinyin      | Meaning                 |
| ----------- | ----------- | ----------------------- |
| Your answer | mei2 shou1  | did not keep            |
| Reference   | mòshōu      | to confiscate, to seize |

The pinyin and meaning you provided are incorrect.

</conversation>

NOTE: IF THE USER HAS PROVIDED THE TONES, DO NOT ASK FOR THE TONES.

REMINDER
- DO NOT GIVE THE ANSWER UNLESS EXPLICTLY ASKED BY THE USER.
- IF THE USER HAS PROVIDED THE TONES, DO NOT ASK FOR THE TONES.
- The reference meaning is not exhaustive. Accept the user answer if it is correct, even it is not in the reference meaning.
- ACCEPT NUMERICAL PINYIN. IF THE REFERENCE PINYIN IS mòshōu, mo4 shou1 IS CORRECT.
"""

JUDGE_SYSTEM_PROMPT = """
Read the following reply.

{reply}

Reply with exactly one of the following
- The pinyin is correct. The meaning is correct.
- The pinyin is incorrect. The meaning is correct.
- The meaning is correct. The pinyin is incorrect. 
- The meaning is incorrect. The pinyin is incorrect. 
"""


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
        user_level_key = get_user_level_key(request.conversation_id)
        conversation_word_key = get_conversation_word_key(request.conversation_id)
        conversation_submitted_key = get_conversation_submitted_key(request.conversation_id)

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
        else:
            level = 3
            stub.my_dict[user_level_key] = level

        if conversation_word_key in stub.my_dict:
            word_info = stub.my_dict[conversation_word_key]
        else:
            word_info = df[df["level"] == level].sample(n=1).to_dict(orient="records")[0]
            stub.my_dict[conversation_word_key] = word_info
            yield self.text_event(
                TEMPLATE_STARTING_REPLY.format(word=word_info["simplified"], level=word_info["level"])
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
        request.logit_bias = {"13080": 2, "308": 1, "2483": 1}  # " ni"  # " n"  # "i2"

        bot_reply = ""
        async for msg in fp.stream_request(
            request, "ChatGPT", request.access_key
        ):
            bot_reply += msg.text
            yield msg.model_copy()

        if "-----" in bot_reply:
            stub.my_dict[conversation_submitted_key] = True
            request.query = [
                {
                    "role": "user",
                    "content": JUDGE_SYSTEM_PROMPT.format(
                        reply=bot_reply
                    ),
                }
            ]
            judge_reply = ""
            async for msg in fp.stream_request(
                request, "ChatGPT", request.access_key
            ):
                judge_reply += msg.text
            if "The pinyin is correct. The meaning is correct." in judge_reply:
                stub.my_dict[user_level_key] += 1
            elif "The pinyin is incorrect. The meaning is incorrect." in judge_reply:
                stub.my_dict[user_level_key] -= 1
            else:
                pass        


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
