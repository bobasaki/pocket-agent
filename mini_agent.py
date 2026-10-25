from typing import Any


import anthropic
import sys
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
MAX_TOOL_CALLS = 10
PROJECT_ROOT = Path(".").resolve()
RESTRICTED = {"uv.lock", "pyproject.toml", "__pycache__"}
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
    },
    {
        "name": "write_file",
        "description": (
            "Create a new file in the project with the given content. "
            "Only works for files that do not exist yet; to change an existing "
            "file, use edit_file. Cannot create folders: the parent folder must "
            "already exist. Test files (test_*.py) and mini_agent.py are read-only."
        ),
        "input_schema":{
            "type": "object",
            "properties":{
                "path": {
                    "type": "string",
                    "description": "path to a file, relative to the project root, ex. src/main.py"
                },
                "content": {
                    "type": "string",
                    "description": "complete contents of the new file"
                }
            },
            "required": ["path", "content"]
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Edit existing files in the project. Only works for files that already exist; "
            "Always read the whole file before editing with read_file. "
            "To create new files use write_file. "
            "Test files (test_*.py) and mini_agent.py are read-only. old_text is replaced with new_text. "
            "Everything else stays untouched"
        ),
        "input_schema": {
            "type": "object",
            "properties":{
                "path": {
                    "type": "string",
                    "description": "path to a file, relative to the project root, ex. src/main.py"                  
                },
                "old_text": {
                    "type": "string",
                    "description": (
                        "Exact copy of the part of the file that needs editing, character for character, "
                        "including indentations and line break.  "
                        "This is the only part of the file that can be changed. "
                        "old_text must appear in the file exactly once, if it appears more then once, "
                        "include more surrounding lines to make it unique"
                    )
                },
                "new_text": {
                    "type": "string",
                    "description": (
                        "Contents of the part of the file that will be replacing old_text. "
                        "new_text can be an empty string, and empty string deletes old_text"
                    ),
                }
            },
            "required": ["path", "old_text", "new_text"]

        }

    }
]

def _is_allowed(path):
    real = Path(path).resolve()
    if not real.is_relative_to(PROJECT_ROOT):
        return False
    relative = real.relative_to(PROJECT_ROOT)
    return (
        not any(part.startswith(".") for part in relative.parts) 
        and not any(part in RESTRICTED for part in relative.parts)
    )    

def _is_writable(path):
    real = Path(path).resolve()
    return (
        _is_allowed(real) 
        and real.parent.exists() 
        and real.name != "mini_agent.py" 
        and not real.name.startswith("test_")
    )

def write_file(path, content):
    real = Path(path).resolve()
    if not _is_writable(real):
        raise PermissionError(f"Access denied to {path}")
    if real.exists():
        raise FileExistsError(f"{path} already exists, to edit existing files use edit_file")
    with open(real, "w", encoding="utf-8") as file:
        file.write(content)
    return f"Created {path} ({len(content)} characters)"

def edit_file(path, old_text, new_text):
    real = Path(path).resolve()
    if not _is_writable(real):
        raise PermissionError(f"Access denied to {path}")
    if not real.exists():
        raise FileNotFoundError(f"{path} doesn't exist, to create new files use write_file")
    text = read_file(real)
    count = text.count(old_text)
    if count < 1:
        raise ValueError(f"{old_text} not found in {path}, read {path} again and copy EXACT text")
    if count > 1:
        raise ValueError(f"{old_text} found {count} times in {path}, include more surrounding lines to make it unique")
    text_edited = text.replace(old_text, new_text, 1)
    with open(real, "w", encoding="utf-8") as file:
        file.write(text_edited)
    return (
        f"File: {path} edited, replaced {len(old_text)} characters with {len(new_text)} characters. "
    )

def read_file(path):
    real = Path(path).resolve()
    if not _is_allowed(real):
        raise PermissionError(f"Access denied to {path}")
    if not real.exists():
        raise FileNotFoundError(f"{path} not found, use list_files to see available files")
    with open(real, encoding="utf-8") as file:
        return file.read()

def list_files():
    return "\n".join(
        [str(path) for path in Path(".").rglob("*")
        if _is_allowed(path) and path.is_file()]
    )

def run_tool(name, tool_input):
    try:
        if name == "read_file":
            return read_file(tool_input["path"]), False
        if name == "list_files":
            return list_files(), False
        if name == "write_file":
            return write_file(tool_input["path"],tool_input["content"]), False
        if name == "edit_file":
            return edit_file(tool_input["path"], tool_input["old_text"], tool_input["new_text"]), False
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
    return message

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
    while True:
        try:
            question = input("Ask Claude: ")
            turn = messages + [{"role": "user", "content": question}]

            for _ in range(MAX_TOOL_CALLS):
                answer = chat(turn)
                turn.append({"role": "assistant", "content": answer.content})

                if answer.stop_reason != "tool_use":
                    break

                results = []
                for block in answer.content:
                    if block.type == "tool_use":
                        print(f": {block.name} {block.input}")
                        content, is_error = run_tool(block.name, block.input)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                            "is_error": is_error,
                        })
                turn.append({"role": "user", "content": results})
            if answer.stop_reason == "tool_use":
                print(f"Stopped after {MAX_TOOL_CALLS} API calls without a final answer")
            else:
                messages = turn 
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

