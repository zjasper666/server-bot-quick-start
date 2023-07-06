"""

Sample bot executes your Python code.

python3 echobot.py
(assumes you already have modal set up)
"""

import sys
from io import StringIO
from typing import AsyncIterable

import modal
from fastapi_poe import PoeBot, run
from fastapi_poe.types import QueryRequest
from modal import Image, Stub
from sse_starlette.sse import ServerSentEvent

image = Image.debian_slim().pip_install_from_requirements("requirements_exec.txt")
stub = Stub("run-python-code")


@stub.function(image=image, timeout=30, keep_warm=1)
def execute_code(code):
    import traitlets.config
    from IPython.terminal.embed import InteractiveShellEmbed

    config = traitlets.config.Config()
    config.InteractiveShell.colors = "NoColor"
    # config.PlainTextFormatter.max_width = 40  # not working
    # config.InteractiveShell.width = 40  # not working
    ipython = InteractiveShellEmbed(config=config)

    # Redirect stdout temporarily to capture the output of the code snippet
    old_stdout = sys.stdout
    sys.stdout = StringIO()

    # Execute the code with the silent parameter set to True
    _ = ipython.run_cell(code, silent=True, store_history=False, shell_futures=False)

    # Restore the original stdout and retrieve the captured output
    captured_output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    return captured_output


def format_output(captured_output, captured_error="") -> str:
    lines = []

    if captured_output:
        line = f"\n```output\n{captured_output}\n```"
        lines.append(line)

    if captured_error:
        line = f"\n```error\n{captured_error}\n```"
        lines.append(line)

    return "\n".join(lines)


def strip_code(code):
    if len(code.strip()) < 6:
        return code
    code = code.strip()
    if code.startswith("```") and code.endswith("```"):
        code = code[3:-3]
    return code


class EchoBot(PoeBot):
    async def get_response(self, query: QueryRequest) -> AsyncIterable[ServerSentEvent]:
        print("user_statement", query.query[-1].content)
        code = query.query[-1].content
        code = strip_code(code)
        with stub.run():
            try:
                captured_output = execute_code.call(code)  # need async await?
            except modal.exception.TimeoutError:
                yield self.text_event("Time limit exceeded.")
                return
        if len(captured_output) > 5000:
            yield self.text_event(
                "There is too much output, this is the partial output."
            )
            captured_output = captured_output[:5000]
        reply_string = format_output(captured_output)
        if not reply_string:
            yield self.text_event("No output or error recorded.")
            return
        yield self.text_event(reply_string)


if __name__ == "__main__":
    run(EchoBot())
