"""

Sample bot that echoes back messages.

"""
from __future__ import annotations

import difflib
from typing import AsyncIterable

from fastapi_poe import PoeBot, run
from fastapi_poe.client import MetaMessage, stream_request
from fastapi_poe.types import QueryRequest
from sse_starlette.sse import ServerSentEvent

LANGUAGE_PROMPT_TEMPLATE = """
You will follow the instructions from the user and fix the spelling, grammar and improve the style.

Please fix the following statement.

The statement begins.

```
{user_statement}
```

The statement has ended.

Only reply the fixed quoted text. Do not explain.
Do not begin or end your reply with inverted commas.
""".strip()


def markdown_diff(str1, str2):
    diff = difflib.ndiff(str1.split(), str2.split())
    result = []

    for token in diff:
        if token[0] == "-":
            result.append(f"~~{token[2:]}~~")  # strikethrough
        elif token[0] == "+":
            result.append(f"**{token[2:]}**")  # bold
        elif token[0] == " ":
            result.append(token[2:])

    return " ".join(result)


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        user_statement = query.query[-1].content
        print("user_statement", user_statement)

        wrapped_message = LANGUAGE_PROMPT_TEMPLATE.format(user_statement=user_statement)
        query.query[-1].content = wrapped_message
        query.query = [query.query[-1]]

        character_reply = ""
        async for msg in stream_request(query, "EnglishDiffTool", query.api_key):
            # Note: See https://poe.com/MeguminHelper for the system prompt
            if isinstance(msg, MetaMessage):
                continue
            elif msg.is_suggested_reply:
                yield self.suggested_reply_event(msg.text)
            elif msg.is_replace_response:
                yield self.replace_response_event(msg.text)
            else:
                character_reply += msg.text
                rendered_text = markdown_diff(user_statement, character_reply)
                yield self.replace_response_event(rendered_text)
        
        print("character_reply", character_reply)


if __name__ == "__main__":
    run(EchoBot())
