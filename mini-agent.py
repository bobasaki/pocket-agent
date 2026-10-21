from typing import Any


import anthropic
import sys
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic()


def add_user_message(messages, text):
    user_message = {"role": "user", "content": text}
    messages.append(user_message)

def add_assistant_message(messages, text):
    assistant_message = {"role": "assistant", "content": text}
    messages.append(assistant_message)

def chat(messages):
    message = client.messages.create(
        model="claude-haiku-5-5",
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
    messages: list[Any] = list()
    while True:
        try:
            question = input("Ask Claude: ")
            answer = chat(messages + [{"role": "user", "content": question}])
            print(text_output(answer))
            print(f"Input tokens: {input_tokens(answer)}")
            if answer.stop_reason == "max_tokens":
                print("Token limit has been reached")
            add_user_message(messages, question)
            add_assistant_message(messages, answer.content)
        except KeyboardInterrupt:
            sys.exit("\nWe are done")
        except anthropic.APIError as e:
            print(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()