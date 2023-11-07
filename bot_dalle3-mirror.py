"""

BOT_NAME="dalle3-mirror"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

Test message:
ChatGPT

"""
from __future__ import annotations

import os
import time
from typing import AsyncIterable

import fastapi_poe.client
from fastapi_poe import PoeBot, make_app
from fastapi_poe.types import (
    PartialResponse,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)
from modal import Dict, Image, Stub, asgi_app
from openai import OpenAI
from sse_starlette.sse import ServerSentEvent

fastapi_poe.client.MAX_EVENT_COUNT = 10000

DAY_IN_SECS = 24 * 60 * 60

DAILY_MESSAGE_LIMIT = 3


stub = Stub("poe-bot-quickstart")
stub.my_dict = Dict.new()


def prettify_time_string(second) -> str:
    second = int(second)
    hour, second = divmod(second, 60 * 60)
    minute, second = divmod(second, 60)

    string = "You can send the next message in"
    if hour == 1:
        string += f" {hour} hour"
    elif hour > 1:
        string += f" {hour} hours"

    if minute == 1:
        string += f" {minute} minute"
    elif minute > 1:
        string += f" {minute} minutes"

    if second == 1:
        string += f" {second} second"
    elif second > 1:
        string += f" {second} seconds"

    return string


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        client = OpenAI()

        dict_key = f"dalle3-mirror-limit-{query.user_id}"

        if dict_key not in stub.my_dict:
            stub.my_dict[dict_key] = []

        # thread safe?
        calls = stub.my_dict[dict_key]

        while calls and calls[0] <= time.time() - DAY_IN_SECS:
            del calls[0]

        if len(calls) >= DAILY_MESSAGE_LIMIT:
            time_remaining = calls[0] + DAY_IN_SECS - time.time()
            yield PartialResponse(text=prettify_time_string(time_remaining))
            return

        calls.append(time.time())
        stub.my_dict[dict_key] = calls

        user_statement = query.query[-1].content

        print(user_statement)
        print(stub.my_dict[dict_key])
        # TODO - get ChatGPT to rewrite the prompt

        response = client.images.generate(
            model="dall-e-3",
            prompt=user_statement,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        revised_prompt = response.data[0].revised_prompt
        image_url = response.data[0].url

        yield PartialResponse(text=f"```prompt\n{revised_prompt}\n```\n\n")
        yield PartialResponse(text=f"![image]({image_url})")

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={},
            allow_attachments=False,  # to update when ready
            introduction_message="What do you want to generate with DALL·E 3?",
        )


bot = EchoBot()

image = (
    Image.debian_slim()
    .pip_install("fastapi-poe==0.0.23", "openai==1.1.0")
    .env(
        {
            "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
            "POE_ACCESS_KEY": os.environ["POE_ACCESS_KEY"],
        }
    )
)


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    app = make_app(bot, api_key=os.environ["POE_ACCESS_KEY"])
    return app
