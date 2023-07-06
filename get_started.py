import modal

stub = modal.Stub("example-get-started")

code = """
import os
os._exit(00)
"""


@stub.function()
def square(x):
    exec(code)
    print("This code is running on a remote worker!")
    return x**2


@stub.local_entrypoint()
def main():
    print("the square is", square.call(42))
