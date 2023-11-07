"""

BOT_NAME="dalle3-mirror"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

Test message:
ChatGPT

"""
from __future__ import annotations

from typing import AsyncIterable

import os
import fastapi_poe.client

from fastapi_poe import PoeBot, make_app
from fastapi_poe.types import QueryRequest, SettingsRequest, SettingsResponse
from modal import Image, Stub, asgi_app
from sse_starlette.sse import ServerSentEvent

from fastapi_poe.types import (
    ContentType,
    ErrorResponse,
    MetaResponse,
    PartialResponse,
    QueryRequest,
    ReportFeedbackRequest,
    SettingsRequest,
    SettingsResponse,
)

from openai import OpenAI

fastapi_poe.client.MAX_EVENT_COUNT = 10000


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        client = OpenAI()
        user_statement = query.query[-1].content
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

image = Image.debian_slim().pip_install("fastapi-poe==0.0.23", "openai==1.1.0").env(
    {
        "OPENAI_API_KEY": os.environ["OPENAI_API_KEY"],
        "POE_ACCESS_KEY": os.environ["POE_ACCESS_KEY"],
    }
)

stub = Stub("poe-bot-quickstart")


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    app = make_app(bot, api_key=os.environ["POE_ACCESS_KEY"])
    return app
