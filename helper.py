"""

Sample bot executes your Python code.

modal deploy helper.py
"""

import sys
from io import StringIO

from modal import Image, Stub

image = Image.debian_slim().pip_install_from_requirements("requirements_exec.txt")
stub = Stub("run-python-code-shared")


@stub.function(image=image, timeout=30)
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
