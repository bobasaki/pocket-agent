from typing import Any


import anthropic
import sys
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
MAX_TOOL_CALLS = 10
RESTRICTED = {"uv.lock", "pyproject.toml"}

client = anthropic.Anthropic()

tools = [
    {
        "name": "read_file",
        "description": (
            "Read a text file from the project and return its full contents "
            "as a string. Use this to inspect a file before answering "
            "questions about it or before changing it."
        ),
        "input_schema":{
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "path to a file, relative to the project root, ex. src/main.py"
                }
            },
            "required": ["path"]
        },
    },
    {
        "name": "list_files",
        "description": (
            "List all non-confidential files from the project directory as a string. "
            "Use this to find relevant files that are not strictly mentioned in "
            "the chat"
        ),
        "input_schema":{
            "type": "object",
            "properties": {},
        },
    }
]

def _is_allowed(path):
    return (
        not any(part.startswith(".") for part in path.parts)
        and path.name not in RESTRICTED
    )    

def read_file(path):
    path = Path(path)
    if not _is_allowed(path):
        raise PermissionError (f"Access denied to {path}")
    if not path.exists():
        raise FileNotFoundError ()
    with open(path, encoding="utf-8") as file:
        return file.read()

def list_files():
    return "\n".join(
        [str(path) for path in Path(".").rglob("*")
        if _is_allowed(path) and not path.is_file()]
    )

def run_tool(name, tool_input):
    try:
        if name == "read_file":
            return read_file(tool_input["path"]), False
        if name == "list_files":
            return list_files(), False
        return f"Unknown tool: {name}", True
    except Exception as e:
        return f"{type(e).__name__}: {e}", True

def chat(messages):
    message = client.messages.create(
        model="claude-haiku-5-5",
        tools=tools,
        max_tokens=1024,
        messages=messages,
    )
    return(message)

def text_output(message):
    result = ""
    for block in message.content:
        if block.type == "text":
            result += block.text
    return result

def input_tokens(message):
    return message.usage.input_tokens

def main():
    messages: list[Any] = []
    while True:  # outer loop: one iteration per question
        try:
            question = input("Ask Claude: ")
            turn = messages + [{"role": "user", "content": question}]

            for _ in range(MAX_TOOL_CALLS):  # inner loop: one iteration per API call
                answer = chat(turn)
                turn.append({"role": "assistant", "content": answer.content})

                if answer.stop_reason != "tool_use":
                    break

                results = []
                for block in answer.content:
                    if block.type == "tool_use":
                        content, is_error = run_tool(block.name, block.input)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                            "is_error": is_error,
                        })
                turn.append({"role": "user", "content": results})
            if answer.stop_reason == "tool_use":
                print (f"Stopped after {MAX_TOOL_CALLS} API calls without a final answer")
            else:
                messages = turn  # commit: only reached when the whole turn finished
            print(text_output(answer))
            print(f"Input tokens: {input_tokens(answer)}")
            if answer.stop_reason == "max_tokens":
                print("Token limit has been reached")

        except KeyboardInterrupt:
            sys.exit("\nWe are done")
        except anthropic.APIError as e:
            print(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
   