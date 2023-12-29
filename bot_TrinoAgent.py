"""

BOT_NAME="TrinoAgent"; modal deploy --name $BOT_NAME bot_${BOT_NAME}.py; curl -X POST https://api.poe.com/bot/fetch_settings/$BOT_NAME/$POE_ACCESS_KEY

Test message:
Show the first row of the nation table

"""

import os
import re
import textwrap
from typing import AsyncIterable

import trino
from fastapi_poe import PoeBot, make_app
from fastapi_poe.client import MetaMessage, ProtocolMessage, stream_request
from fastapi_poe.types import QueryRequest, SettingsRequest, SettingsResponse
from modal import Image, Stub, asgi_app
from sse_starlette.sse import ServerSentEvent
from trino.exceptions import TrinoUserError

SYSTEM_PROMPT = """
You are an assistant that helps to write Trino queries.

The user has access to tpch.sf*

Do not use semicolons.

Enclose the Trino queries with ```sql and ```
"""


def format_output(columns, rows) -> str:
    output = " | " + "|".join(column.name for column in columns) + " | "
    output += "\n" + " | " + " | ".join("-" for _ in columns) + " | "
    for row in rows:
        output += "\n" + " | " + " | ".join(str(value) for value in row) + " | "
    return output


def extract_code(reply):
    pattern = r"```sql([\s\S]*?)```"
    matches = re.findall(pattern, reply)
    return "\n\n".join(matches)


conn = trino.dbapi.connect(
    host=os.environ["TRINO_HOST_URL"],
    port=443,
    http_scheme="https",
    auth=trino.auth.BasicAuthentication(
        os.environ["TRINO_USERNAME"], os.environ["TRINO_PASSWORD"]
    ),
)
cur = conn.cursor()


def make_query(query):
    try:
        cur.execute(query)
    except TrinoUserError as e:
        return "```python\n" + str(e) + "\n```"
    rows = cur.fetchall()
    columns = cur.description
    output = format_output(columns, rows)
    return output


class EchoBot(PoeBot):
    prompt_bot = "GPT-4"

    async def get_response(
        self, request: QueryRequest
    ) -> AsyncIterable[ServerSentEvent]:
        request.query = [
            ProtocolMessage(role="system", content=SYSTEM_PROMPT)
        ] + request.query

        user_statement = request.query[-1].content
        print("user_statement")
        print(user_statement)

        for _ in range(5):
            current_bot_reply = ""
            async for msg in stream_request(request, self.prompt_bot, request.api_key):
                if isinstance(msg, MetaMessage):
                    continue
                elif msg.is_suggested_reply:
                    yield self.suggested_reply_event(msg.text)
                elif msg.is_replace_response:
                    yield self.replace_response_event(msg.text)
                else:
                    current_bot_reply += msg.text
                    yield self.text_event(msg.text)
                    if extract_code(current_bot_reply):
                        # break when a Python code block is detected
                        break

            query = extract_code(current_bot_reply)
            print("query")
            print(query)
            if not query:
                return

            yield self.text_event("\n\n\n")

            output = make_query(query)
            print("output")
            print(output)
            yield self.text_event(output)

            return

    async def get_settings(self, setting: SettingsRequest) -> SettingsResponse:
        return SettingsResponse(
            server_bot_dependencies={self.prompt_bot: 10},
            allow_attachments=False,
            introduction_message=textwrap.dedent(
                """What do you want to query?"""
            ).strip(),
        )


bot = EchoBot()

image = (
    Image.debian_slim()
    .pip_install("fastapi-poe==0.0.23", "trino")
    .env(
        {
            "POE_ACCESS_KEY": os.environ["POE_ACCESS_KEY"],
            "TRINO_HOST_URL": os.environ["TRINO_HOST_URL"],
            "TRINO_USERNAME": os.environ["TRINO_USERNAME"],
            "TRINO_PASSWORD": os.environ["TRINO_PASSWORD"],
        }
    )
)

stub = Stub("poe-bot-quickstart")


@stub.function(image=image)
@asgi_app()
def fastapi_app():
    app = make_app(bot, api_key=os.environ["POE_ACCESS_KEY"])
    return app
