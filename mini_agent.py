from socket import timeout

import anthropic
import sys
from dotenv import load_dotenv
from pathlib import Path
import subprocess

load_dotenv()
PROJECT_ROOT = Path(__file__).resolve().parent
RESTRICTED = {"uv.lock", "__pycache__"}
READ_ONLY = {"mini_agent.py", "conftest.py", "pytest.ini", "pyproject.toml"}
READ_ONLY_NOTE = f"Test files (test_*.py) and {', '.join(sorted(READ_ONLY))} are read-only."
CLEAN_STOP ={"end_turn"}
client = anthropic.Anthropic()
SYSTEM_PROMPT = (
    "You are a coding agent working inside a Python project. You can read, list, "
    "create and edit files in the project, and run its test suite.\n"
    "\n"
    "How to work:\n"
    "- Read a file with read_file before editing it. Never edit from memory.\n"
    "- Prefer edit_file over rewriting a whole file with write_file.\n"
    "- Use list_files when you are not sure what exists.\n"
    "\n"
    "Finishing a task:\n"
    "- After creating or editing any file, call run_tests.\n"
    "- Do not report a task as finished until the tests pass.\n"
    "- If a test fails, fix the code. Never change or disable a test to make it pass.\n"
    "\n"
    "Limits:\n"
    f"- {READ_ONLY_NOTE}\n"
    "- Hidden files and lockfiles are not visible to you at all.\n"
    "- If a tool returns an error, read the message: it can help"
)

2
def _resolve(path):
    return (PROJECT_ROOT / path).resolve()

READ_FILE_SCHEMA = {
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
}

LIST_FILES_SCHEMA = {
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

WRITE_FILE_SCHEMA = {
    "name": "write_file",
    "description": (
        "Create a new file in the project with the given content. "
        "Only works for files that do not exist yet; to change an existing "
        "file, use edit_file. Cannot create folders: the parent folder must "
        f"already exist. {READ_ONLY_NOTE}"
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
}

EDIT_FILE_SCHEMA = {
    "name": "edit_file",
    "description": (
        "Edit existing files in the project. Only works for files that already exist; "
        "Always read the whole file before editing with read_file. "
        "To create new files use write_file. "
        f"{READ_ONLY_NOTE} "
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
                    "old_text must appear in the file exactly once, if it appears more than once, "
                    "include more surrounding lines to make it unique"
                )
            },
            "new_text": {
                "type": "string",
                "description": (
                    "Contents of the part of the file that will be replacing old_text. "
                    "new_text can be an empty string, an empty string deletes old_text"
                ),
            }
        },
        "required": ["path", "old_text", "new_text"]

    }
}

RUN_TESTS_SCHEMA = {
    "name": "run_tests",
    "description": (
        "Run the projects full test suite with pytest and return the results. "
        "Take no arguments and always run every test. Use this after creating or editing any file. "
        "Do not report task as finished until all checks pass. "
        "Return pytest summary and failure output for any test "
        "that didnt pass"
    ),
    "input_schema":{
        "type": "object",
        "properties": {},
    },
}
class Agent:
    def __init__(self, client, max_tool_calls=10):
        if max_tool_calls < 1:
            raise ValueError(f"Max tool call cannot be less than 1, Current: {max_tool_calls}")
        self.client = client
        self.max_tool_calls = max_tool_calls
        self.messages = []
    
    def chat(self, turn):
        return self.client.messages.create(
            model="claude-haiku-5-5",
            tools=[tool["schema"] for tool in TOOLS.values()],
            max_tokens=4000,
            messages=turn,        
            system = SYSTEM_PROMPT,
        )
    
    def ask(self, question):
        turn = self.messages + [{"role": "user", "content": question}]
        for _ in range(self.max_tool_calls):
            answer = self.chat(turn)
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
            if not results:
                break
            turn.append({"role": "user", "content": results})
        if answer.stop_reason in CLEAN_STOP:
            self.messages = turn   
        return answer    

def _is_allowed(path):
    real = _resolve(path)
    if not real.is_relative_to(PROJECT_ROOT):
        return False
    relative = real.relative_to(PROJECT_ROOT)
    return (
        not any(part.startswith(".") for part in relative.parts) 
        and not any(part in RESTRICTED for part in relative.parts)
    )    

def _is_writable(path):
    real = _resolve(path)
    return (
        _is_allowed(real) 
        and real.parent.exists() 
        and real.name not in READ_ONLY
        and not real.name.startswith("test_")
    )

def _trim(text, output_limit=4000):
    if len(text) < output_limit:
        return text
    return f"[earlier output cut, showing last {output_limit} characters]\n{text[-output_limit:]}"

def write_file(path, content):
    real = _resolve(path)
    if not _is_writable(real):
        raise PermissionError(f"Access denied to {path}")
    if real.exists():
        raise FileExistsError(f"{path} already exists, to edit existing files use edit_file")
    with open(real, "w", encoding="utf-8") as file:
        file.write(content)
    return f"Created {path} ({len(content)} characters)"

def edit_file(path, old_text, new_text):
    real = _resolve(path)
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
    real = _resolve(path)
    if not _is_allowed(real):
        raise PermissionError(f"Access denied to {path}")
    if not real.exists():
        raise FileNotFoundError(f"{path} not found, use list_files to see available files")
    with open(real, encoding="utf-8") as file:
        return file.read()

def run_tests():
    output_limit = 4080
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=60
        )
    except subprocess.TimeoutExpired:
        return (
            "Test suite did not finish within 60 seconds and was stopped. "
            "This is not a test failure: the suite never completed. Most likely something "
            "is hanging - an infinite loop or a blocking call. Read the code you changed "
            "last and look for a loop that never ends or a call that waits forever. "
            "Do not call run_tests again until you have found and fixed the cause."
        )
    return (
        f"exit code: {result.returncode}\n"
        f"--- stdout ---\n{_trim(result.stdout)}\n"
        f"--- stderr ---\n{_trim(result.stderr)}"
    )


def list_files():
    return "\n".join(
        str(path.relative_to(PROJECT_ROOT))
        for path in PROJECT_ROOT.rglob("*")
        if _is_allowed(path) and path.is_file()
    )

TOOLS = {
    "read_file":  {"schema": READ_FILE_SCHEMA,  "function": read_file},
    "list_files": {"schema": LIST_FILES_SCHEMA, "function": list_files},
    "write_file": {"schema": WRITE_FILE_SCHEMA, "function": write_file},
    "edit_file":  {"schema": EDIT_FILE_SCHEMA,  "function": edit_file},
    "run_tests": {"schema": RUN_TESTS_SCHEMA, "function": run_tests}
}

def run_tool(name, tool_input):
    if name not in TOOLS:
        return f"Unknown tool: {name}", True
    try:
        return TOOLS[name]["function"](**tool_input), False
    except Exception as e:
        return f"{type(e).__name__}: {e}", True

def text_output(message):
    result = ""
    for block in message.content:
        if block.type == "text":
            result += block.text
    return result

def input_tokens(message):
    return message.usage.input_tokens

def main():
    agent = Agent(client)
    while True:
        try:
            question = input("Ask Claude: ")
            answer = agent.ask(question)

            if answer.stop_reason == "tool_use":
                print(f"Stopped after {agent.max_tool_calls} API calls without a final answer, turn has been discarded, context hasn't carried over")        
            elif answer.stop_reason == "max_tokens":
                print("Token limit has been reached, turn has been discarded, context hasn't carried over")
            elif answer.stop_reason in CLEAN_STOP:
                print(text_output(answer))
            print(f"Input tokens: {input_tokens(answer)}")

        except KeyboardInterrupt:
            sys.exit("\nWe are done")
        except anthropic.APIError as e:
            print(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
