"""Tests unitaires hermétiques pour le client Ollama."""

import json
from unittest.mock import MagicMock, patch

from harness_tools.llm.client import OllamaClient
from harness_tools.models import Message, ToolCall


def test_client_headers():
    client_local = OllamaClient(host="http://localhost:11434")
    assert client_local._headers() == {"Content-Type": "application/json"}

    client_cloud = OllamaClient(host="https://ollama.com", api_key="secret-key")
    assert client_cloud._headers() == {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret-key",
    }


@patch("urllib.request.urlopen")
def test_client_chat_text_response(mock_urlopen):
    fake_response = {
        "message": {
            "role": "assistant",
            "content": "Bonjour ! Comment puis-je vous aider ?",
        }
    }
    mock_cm = MagicMock()
    mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_cm

    client = OllamaClient()
    res = client.chat([Message(role="user", content="Salut")])

    assert isinstance(res, Message)
    assert res.role == "assistant"
    assert res.content == "Bonjour ! Comment puis-je vous aider ?"
    assert res.tool_calls == []


@patch("urllib.request.urlopen")
def test_client_chat_with_tool_calls(mock_urlopen):
    fake_response = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "function": {
                        "name": "calculate",
                        "arguments": {"expression": "14 * 25"},
                    },
                }
            ],
        }
    }
    mock_cm = MagicMock()
    mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_cm

    client = OllamaClient()
    tools_schema = [{"type": "function", "function": {"name": "calculate"}}]
    res = client.chat([Message(role="user", content="Calcule 14 * 25")], tools=tools_schema)

    assert len(res.tool_calls) == 1
    tc = res.tool_calls[0]
    assert isinstance(tc, ToolCall)
    assert tc.id == "call_123"
    assert tc.name == "calculate"
    assert tc.arguments == {"expression": "14 * 25"}


@patch("urllib.request.urlopen")
def test_client_chat_handles_string_arguments(mock_urlopen):
    fake_response = {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "get_current_time",
                        "arguments": '{"timezone": "UTC"}',
                    }
                }
            ],
        }
    }
    mock_cm = MagicMock()
    mock_cm.read.return_value = json.dumps(fake_response).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = mock_cm

    client = OllamaClient()
    res = client.chat([Message(role="user", content="Quelle heure est-il ?")])

    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].name == "get_current_time"
    assert res.tool_calls[0].arguments == {"timezone": "UTC"}
