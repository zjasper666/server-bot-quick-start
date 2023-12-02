"""

BOT_NAME="AllCapsBotDemo"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY


"""
from __future__ import annotations

from typing import AsyncIterable

from fastapi_poe import PoeBot, make_app
from fastapi_poe.client import stream_request
from fastapi_poe.types import (
    PartialResponse,
    QueryRequest,
    SettingsRequest,
    SettingsResponse,
)
from modal import Image, Stub, asgi_app


class GPT35TurboAllCapsBot(PoeBot):
    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[PartialResponse]:
        async for msg in stream_request(request, "GPT-4", request.access_key):
            yield msg.model_copy(update={"text": msg.text.upper()})

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(server_bot_dependencies={"GPT-4": 1})


image = Image.debian_slim().pip_install("fastapi-poe==0.0.23")

stub = Stub("poe-bot-quickstart")

bot = GPT35TurboAllCapsBot()


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    app = make_app(bot, allow_without_key=True)
    return app
