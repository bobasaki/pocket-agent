import os
import pytest
from dataclasses import dataclass, field
from mini_agent import Agent, read_file, list_files, write_file, edit_file, run_tool



def test_read_file():
    assert "def main():" in read_file("mini_agent.py")
    assert read_file("pyproject.toml")
    with pytest.raises(FileNotFoundError):
        read_file("does_not_exist.txt")
    with pytest.raises(PermissionError):
        read_file(".env")
    with pytest.raises(PermissionError):
        read_file("../secret.txt")
    with pytest.raises(PermissionError):
        read_file("uv.lock")


def test_list_files():
    files = list_files()
    assert "mini_agent.py" in files
    assert "README.md" in files
    assert ".gitignore" not in files
    assert ".env" not in files
    assert "uv.lock" not in files


def test_write_file():
    assert write_file("example.txt", "hello") == "Created example.txt (5 characters)"
    assert read_file("example.txt") == "hello"
    with pytest.raises(FileExistsError):
        write_file("example.txt", "again")
    os.remove("example.txt")

    with pytest.raises(PermissionError):
        write_file("test_cheat.py", "")


def test_edit_file():
    write_file("example.txt", "cat dog cat")
    edit_file("example.txt", "dog", "bird")
    assert read_file("example.txt") == "cat bird cat"
    with pytest.raises(ValueError):
        edit_file("example.txt", "cat", "fish")
    with pytest.raises(ValueError):
        edit_file("example.txt", "cow", "fish")
    os.remove("example.txt")

    with pytest.raises(PermissionError):
        edit_file("mini_agent.py", "def main():", "def hacked():")


def test_pytest_config_files_are_read_only():
    for name in ("conftest.py", "pytest.ini", "pyproject.toml"):
        with pytest.raises(PermissionError):
            write_file(name, "")


def test_run_tool():
    assert run_tool("unknown_tool", {}) == ("Unknown tool: unknown_tool", True)
    text, is_error = run_tool("read_file", {"path": "mini_agent.py"})
    assert "def main():" in text
    assert is_error == False
    text, is_error = run_tool("read_file", {"path": ".env"})
    assert text == "PermissionError: Access denied to .env"
    assert is_error == True




@dataclass
class FakeText:
    text: str = "done"
    type: str = "text"


@dataclass
class FakeToolUse:
    name: str = "list_files"
    input: dict = field(default_factory=dict)
    id: str = "toolu_test"
    type: str = "tool_use"


@dataclass
class FakeReply:
    stop_reason: str
    content: list


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        if len(self.replies) > 1:
            return self.replies.pop(0)
        return self.replies[0]


class FakeClient:
    def __init__(self, *replies):
        self.messages = FakeMessages(replies)




def test_agent_rejects_no_budget():
    with pytest.raises(ValueError):
        Agent(FakeClient(), max_tool_calls=0)


def test_agent_saves_turn():
    client = FakeClient(FakeReply("end_turn", [FakeText("4")]))
    agent = Agent(client)

    answer = agent.ask("what is 2+2")

    assert answer.stop_reason == "end_turn"
    assert len(agent.messages) == 2
    assert agent.messages[0] == {"role": "user", "content": "what is 2+2"}
    assert agent.messages[1]["role"] == "assistant"


def test_agent_discards_bad_turn():
    client = FakeClient(FakeReply("max_tokens", [FakeToolUse()]))
    agent = Agent(client)

    agent.ask("write a very long file")

    assert agent.messages == []


def test_agent_discards_exhausted_turn():
    client = FakeClient(FakeReply("tool_use", [FakeToolUse()]))
    agent = Agent(client, max_tool_calls=3)

    agent.ask("keep calling tools")

    assert agent.messages == []
    assert len(client.messages.calls) == 3


def test_bad_turn_not_poison():
    client = FakeClient(
        FakeReply("max_tokens", [FakeToolUse()]),
        FakeReply("end_turn", [FakeText("4")]),
    )
    agent = Agent(client)

    agent.ask("write a very long file")
    agent.ask("what is 2+2")

    sent = client.messages.calls[-1]["messages"]
    assert len(sent) == 1
    assert all(message["content"] for message in sent)