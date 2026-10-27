# mini_agent

This project is a small version of Claude Code with its own harness via the Claude API.
Thanks to OOP you are able to run multiple agents from the `Agent` class (each object of the class is its own agent with its
own list of messages).
The agent is able to read, list, create and edit files inside the project.

## How to run it

- Install [uv](https://docs.astral.sh/uv/) and run `uv sync` from the top-level (root) folder; it creates `.venv` with Python 3.12 and installs every dependency from `uv.lock`
- Save the API key in a `.env` file (`ANTHROPIC_API_KEY=...`), the project imports the API key safely via `load_dotenv()`
- To start the program run `uv run mini_agent.py`
- To exit the program, press Ctrl+C inside the terminal

- During the run you will be able to exchange messages with the AI, along with using tool calls
- Along with the messages from the AI, you will also see which tools are called and the input token count
- If a turn fails (see `ask` below) the program says so and the turn is dropped from the agent's history

## Files

### mini_agent.py

- Main file of the project containing the harness for the AI (instructions and guardrails)

- `PROJECT_ROOT` is based on `__file__`, as to maintain the implemented security features,
regardless of where the file is run from, it keeps the directory of the file as the
directory the agent is allowed to work in
- `RESTRICTED` is a set of names (`uv.lock` and `__pycache__`) the agent can never read or edit, even though they are inside the project
- `READ_ONLY` is a set of names the agent can read but never create or change: `mini_agent.py` (so it cannot rewrite its own harness) and every file pytest reads as configuration (`conftest.py`, `pytest.ini`, `pyproject.toml`, `tox.ini`, `setup.cfg`). Without this the agent could switch its own tests off
- `READ_ONLY_NOTE` builds the sentence describing that rule once, out of `READ_ONLY` itself, so the tool descriptions can never drift from the code
- `CLEAN_STOP` is the set of `stop_reason` values that count as a cleanly finished turn (currently just `end_turn`); only turns ending this way are saved to the agent's history

The `SCHEMA`-s are dictionaries containing the schema for each tool:
 - `READ_FILE_SCHEMA`, `LIST_FILES_SCHEMA`, `WRITE_FILE_SCHEMA`, `EDIT_FILE_SCHEMA`

The `TOOLS` dictionary contains every tool at the agent's disposal
- `schema` contains the schema fed to the AI
- `function` contains the actual Python function
- The `chat` method loads all the tool schemas to send to the AI model
- `run_tool` looks up the tool in `TOOLS` based on the AI's request and calls the appropriate function

`Agent` class
- `__init__`
  - Instantiates an agent with its own list of messages and the number of times an agent can call Claude in one question
  - Rejects a `max_tool_calls` below 1 with a `ValueError`, so a budget that can never run the loop fails at construction instead of crashing later inside `ask`
- `chat`
  - Sends the full list of messages to Claude and returns Claude's reply
- `ask`
  - Contains the loop that asks Claude, runs the tools Claude requests and sends the results back until Claude gives a final answer, with `max_tool_calls` preventing it from running indefinitely
  - A turn is saved to the agent's messages only if it ends with a `stop_reason` in `CLEAN_STOP`. Two cases are discarded instead: the budget running out mid-tool-chain, and a reply cut short by `max_tokens`
  - Discarding a truncated reply is what keeps the history valid. A reply cut off mid-tool-call leaves a `tool_use` block with no matching `tool_result`, and the API rejects every later request that replays it — without this, a single truncation would break the agent permanently
  - If a reply asks for tools but carries no usable tool block, the loop stops rather than sending an empty message back to the API

Functions
- `main`
  - Main function in charge of exchanging input and output with the user, and reporting which of the three outcomes a turn had: finished cleanly, ran out of budget, or was cut short
- `read_file`
  - Returns the contents of the file, if that file is permitted to be read
- `list_files`
  - Lists all allowed files in the project's directory
- `write_file`
  - Creates a new file (if the file is allowed to be created) and returns a useful message back to Claude
- `edit_file`
  - Edits an already existing file, making sure that the text to be changed appears exactly once, and returns a useful message back to Claude
- `_resolve`
  - Joins the path Claude gives with `PROJECT_ROOT` and returns the full, real path of that file
- `_is_allowed`
  - Returns `True` if the file the agent is trying to access is inside the project and isn't restricted or hidden (dot files)
- `_is_writable`
  - Expands the `_is_allowed` function to also check if the file is editable (not in `READ_ONLY` and not a test file)
- `run_tool`
  - Runs the tools Claude requests and returns their output (or an appropriate error message if the tool doesn't exist or an error is raised)
- `text_output`
  - Returns only the text blocks from the AI's response for readability
- `input_tokens`
  - Returns the number of input tokens used by the last reply

### test_mini_agent.py

Tests for the file tools:

- `test_read_file` - checks that `read_file` returns the contents of `mini_agent.py` (containing `def main():`) and that `pyproject.toml` can be read even though it cannot be written
                   - checks that `read_file` raises a `FileNotFoundError` for a missing file and a `PermissionError` for a hidden (`.env`), restricted (`uv.lock`) or outside (`../secret.txt`) file
- `test_list_files` - checks that the string returned by `list_files` contains files like `mini_agent.py` and `README.md` but not forbidden files like `.env`, `.gitignore` or `uv.lock`
- `test_write_file` - creates a new file and uses `read_file` to check if the file is created and has the right content, also deletes the file after the test is completed, and checks that test files can't be created
- `test_edit_file` - creates a new file with `write_file` to keep each test separate, then edits the file, and checks its content with `read_file`, deleting the file at the end of the test, and checks that `mini_agent.py` can't be edited
- `test_pytest_config_files_are_read_only` - checks that every file pytest reads as configuration raises a `PermissionError` on write, so the agent cannot disable its own tests
- `test_run_tool` - checks that the AI asking for a non-existing tool, or for `read_file` on `.env`, returns an error message with appropriate content

Tests for the `Agent` loop. These use `FakeClient`, a stand-in for the Anthropic client that returns
replies chosen by the test and records every call it receives. `Agent` takes its client as an
argument rather than reaching for the global one, which is what makes this possible — the tests run
with no API key, no network and no cost:

- `test_agent_rejects_no_budget` - checks that a `max_tool_calls` below 1 raises a `ValueError` at construction
- `test_agent_saves_turn` - checks that a turn ending in `end_turn` is saved to the agent's messages, and in the right shape
- `test_agent_discards_bad_turn` - checks that a turn cut short by `max_tokens` leaves the history untouched
- `test_agent_discards_exhausted_turn` - checks that running out of budget leaves the history untouched, and that the budget really is what stopped the loop
- `test_bad_turn_not_poison` - checks that after a cut-short turn, the next question is still sent as a valid request. This is the regression test for the bug where one truncated reply would break the agent for the rest of the session

- Run the tests via the terminal with `uv run pytest`

### pyproject.toml and uv.lock

- `pyproject.toml` - lists the libraries the project needs, `uv.lock` pins their exact versions so `uv sync` installs the same setup every time
  - `anthropic` - official library for talking to Claude through the API.
  - `dotenv` - loads the API key from the `.env` file as to not leak your personal API key.
  - `pytest` (dev dependency) - for testing `test_mini_agent.py`.

## Design choices

Moved the agent from the `main` function into its own class, allowing for multiple agents and easier testing.
Instead of an `if` chain in `run_tool`, created a `TOOLS` dictionary with all tools, so `run_tool` can look up any tool by name and pass Claude's inputs to its function as keyword arguments with `**tool_input`.
Instead of resolving the path based on where the program is ran from, it resolves the path based on which directory `mini_agent.py` is in.
Used uv instead of `pip` and `requirements.txt`, so the Python version and every dependency version are locked in `uv.lock`.
Whether a turn is kept is decided by a set of allowed stop reasons rather than by excluding the bad ones, so a `stop_reason` nobody anticipated is dropped instead of silently saved.

## Known limitations

- Discarding a turn rolls back the conversation, not the filesystem. Files written or edited during a discarded turn stay changed on disk, so the agent's memory and the project can fall out of sync. A longer-running agent should keep the turn and send back an error result saying it was cut off, letting the model recover instead of forgetting.
- `READ_ONLY` is a blocklist, which is the weaker shape: anything not named in it is writable, so the protection is only as complete as the list. The stronger version is to run the tests from a clean copy of the test files that the agent cannot reach, so nothing it writes can affect how it is graded.
- Even that would not stop the agent from making a test pass by hardcoding the expected value in the function being tested. Passing tests are a proxy for correctness, and at some point a human has to read the diff.
- Nothing trims the message history, and tool results carry whole files, so a long session grows the context without limit. `input_tokens` is reported but not acted on.