import os
import pytest
from mini_agent import read_file, list_files, write_file, edit_file, run_tool


def test_read_file():
    assert "def main():" in read_file("mini_agent.py")
    with pytest.raises(FileNotFoundError):
        read_file("does_not_exist.txt")
    with pytest.raises(PermissionError):
        read_file(".env")
    with pytest.raises(PermissionError):
        read_file("../secret.txt")
    with pytest.raises(PermissionError):
        read_file("pyproject.toml")


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


def test_run_tool():
    assert run_tool("unknown_tool", {}) == ("Unknown tool: unknown_tool", True)
    text, is_error = run_tool("read_file", {"path": "mini_agent.py"})
    assert "def main():" in text
    assert is_error == False
    text, is_error = run_tool("read_file", {"path": ".env"})
    assert text == "PermissionError: Access denied to .env"
    assert is_error == True
