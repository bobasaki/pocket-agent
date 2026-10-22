from typing import Any


import anthropic
import sys
from anthropic.types import content_block, tool_result_block_param
from dotenv import load_dotenv

load_dotenv()

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
                    "description": "path to a file, relative the the project root, ex. src/main.py"
                }
            },
            "required": ["path"]
        },
    }
]

def read_file(path):
    with open(path, encoding="utf-8") as file:
        return file.read()

def run_tool(name, tool_input):
    try:
        if name == "read_file":
            return read_file(tool_input["path"]), False
        return f"Unknown tool: {name}", True
    except Exception as e:
        return f"{type(e).__name__}: {e}", True

def add_user_message(messages, text):
    user_message = {"role": "user", "content": text}
    messages.append(user_message)

def add_assistant_message(messages, content):
    assistant_message = {"role": "assistant", "content": content}
    messages.append(assistant_message)

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

            for _ in range(1):  # inner loop: one iteration per API call
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