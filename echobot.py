"""

Sample bot that echoes back messages.

This is the simplest possible bot and a great place to start if you want to build your own bot.

"""
from __future__ import annotations

from typing import AsyncIterable

from fastapi_poe import PoeBot
from fastapi_poe.types import QueryRequest
from sse_starlette.sse import ServerSentEvent

import tiktoken

encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        last_message = query.query[-1].content
        tokens = encoding.encode(last_message)
        last_message = " | ".join([str((encoding.decode_single_token_bytes(token), token))[2:-1] for token in tokens]) 
        yield self.text_event(last_message)
