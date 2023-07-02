"""

Sample bot executes your Python code.

Main reference
https://til.simonwillison.net/webassembly/python-in-a-wasm-sandbox

Guide
https://bytecodealliance.github.io/wasmtime-py/

"""
from __future__ import annotations

import os
import tempfile
import uuid
from typing import AsyncIterable

from fastapi_poe import PoeBot, run
from fastapi_poe.types import QueryRequest
from sse_starlette.sse import ServerSentEvent
from wasmtime import Config, Engine, Linker, Module, Store, WasiConfig

TOTAL_FUEL = 10_000_000_000


async def run_code(code, stdin_file=None):
    # Note: not really async, nice to fix
    # Note: not able to import numpy, pandas etc, nice to fix

    # shutil.copytree("../tmp", ".", dirs_exist_ok=True)
    fuel = TOTAL_FUEL

    engine_cfg = Config()
    engine_cfg.consume_fuel = True
    engine_cfg.cache = True

    linker = Linker(Engine(engine_cfg))
    linker.define_wasi()

    python_module = Module.from_file(linker.engine, "bin/python-3.11.1.wasm")

    config = WasiConfig()

    config.env = [("PYTHONHOME", "/usr/local")]
    config.argv = ("python", "-c", code)

    # I want to disable this, instead of rsync every time
    config.preopen_dir(".", "/")

    random_uuid = uuid.uuid4()

    with tempfile.TemporaryDirectory() as chroot:
        out_log = os.path.join(chroot, f"out-{random_uuid}.log")
        err_log = os.path.join(chroot, f"err-{random_uuid}.log")
        if stdin_file:
            config.stdin_file = stdin_file
        config.stdout_file = out_log
        config.stderr_file = err_log

        store = Store(linker.engine)

        # Limits how many instructions can be executed:
        store.add_fuel(fuel)
        store.set_wasi(config)
        instance = linker.instantiate(store, python_module)

        # _start is the default wasi main function
        start = instance.exports(store)["_start"]

        mem = instance.exports(store)["memory"]

        error = None
        try:
            start(store)
        except Exception:
            with open(err_log) as f:
                error = f.read()

        # Note: there is no error if the code times out, nice to fix
        with open(out_log) as f:
            result = f.read()

        return (
            result,
            error,
            mem.size(store),
            mem.data_len(store),
            store.fuel_consumed(),
        )


def format_output(captured_output, captured_error, fuel_consumed) -> str:
    lines = []

    if fuel_consumed >= TOTAL_FUEL:
        lines.append("Time limit exceeded.")

    if captured_output:
        line = f"\n```output\n{captured_output}\n```"
        lines.append(line)

    if captured_error:
        line = f"\n```error\n{captured_error}\n```"
        lines.append(line)

    line = f"Fuel consumed: {fuel_consumed:_}"
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
        code = query.query[-1].content
        code = strip_code(code)
        captured_output, captured_error, size, data_len, fuel_consumed = await run_code(
            code
        )
        reply_string = format_output(captured_output, captured_error, fuel_consumed)
        yield self.text_event(reply_string)


if __name__ == "__main__":
    run(EchoBot())
