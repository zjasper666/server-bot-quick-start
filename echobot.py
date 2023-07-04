"""

Sample bot executes your Python code.

Main reference
https://til.simonwillison.net/webassembly/python-in-a-wasm-sandbox

Guide
https://bytecodealliance.github.io/wasmtime-py/

Documentation
https://wasmlabs.dev/articles/python-wasm32-wasi/

"""

import linecache
import sys
import traceback
from io import StringIO
from typing import AsyncIterable

import traitlets.config
from fastapi_poe import PoeBot, run
from fastapi_poe.types import QueryRequest
from modal import Image, Stub
from sse_starlette.sse import ServerSentEvent

image = Image.debian_slim().pip_install_from_requirements("requirements_exec.txt")
stub = Stub("example-get-started")


@stub.function(image=image)
def execute_code(code):
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
    result = ipython.run_cell(
        code, silent=True, store_history=False, shell_futures=False
    )

    # Restore the original stdout and retrieve the captured output
    captured_output = sys.stdout.getvalue()
    sys.stdout = old_stdout

    # Check if there is an error and capture the error message
    captured_error = ""
    result_error = result.error_before_exec or result.error_in_exec
    if result_error is not None:
        etype, evalue, tb = type(result_error), result_error, result_error.__traceback__
        captured_error = "".join(traceback.format_exception(etype, evalue, tb))

        # Add additional lines of context for each traceback level
        tb_info = traceback.extract_tb(tb)
        if result.error_in_exec:
            captured_error += "\n\nAdditional context for each traceback level:\n"
            for level, (filename, lineno, func, _) in enumerate(tb_info[1:], start=1):
                context_before = max(1, lineno - 3)
                context_after = lineno + 3
                lines = [
                    linecache.getline(filename, i).rstrip()
                    for i in range(context_before, context_after + 1)
                ]
                formatted_lines = [
                    f"{i}: {line}" for i, line in enumerate(lines, start=context_before)
                ]
                captured_error += (
                    f"\nLevel {level} ({filename}, line {lineno}, in {func}):\n"
                    + "\n".join(formatted_lines)
                    + "\n"
                )

    return captured_output, captured_error


def format_output(captured_output, captured_error) -> str:
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
        captured_output, captured_error = execute_code(code)  # need async await?
        print(captured_output)
        print(captured_error)
        reply_string = format_output(captured_output, captured_error)
        if not reply_string:
            yield self.text_event("No output or error recorded.")
            return
        yield self.text_event(reply_string)


if __name__ == "__main__":
    run(EchoBot())
