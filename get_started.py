import linecache
import sys
import traceback
from io import StringIO
from typing import AsyncIterable

from modal import Image, Stub
from IPython import get_ipython

image = (
    Image.debian_slim()
    .pip_install_from_requirements("requirements_exec.txt")
)
stub = Stub("example-get-started")


ipython = get_ipython()

@stub.function(image=image)
def execute_code(code):
    ipython = get_ipython()

    if ipython is None:
        # This means the script is being run outside an IPython environment
        from IPython.terminal.embed import InteractiveShellEmbed
        ipython = InteractiveShellEmbed()

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


# Example usage:
code = """
import sys
import numpy as np
arr = np.array([[1,2], [2,3]])
print(arr[1,0])
print("This is standard output")
print("This is an error message", file=sys.stderr)
assert False
print("This should not happen")
"""


@stub.local_entrypoint()
def main():
    stdout_output, stderr_output = execute_code.call(code)
    print("Captured stdout:", stdout_output)
    print("Captured stderr:", stderr_output)
