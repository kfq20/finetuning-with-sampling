"""Controller-only Fleet access. No credentials enter solver state or logs."""

from __future__ import annotations
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


class FleetError(RuntimeError):
    pass


class Fleet:
    def __init__(self, private_config: Path):
        if private_config.stat().st_mode & 0o077:
            raise PermissionError("Fleet controller config must be private")
        self.config = json.loads(private_config.read_text())
        self.endpoint = self.config["base_url"] + "/d/" + self.config["task_id"] + "/v1"

    def chat(self, messages, tools=None, max_tokens=32768):
        body = {
            "model": self.config["model_id"],
            "messages": messages,
            "temperature": 0.6,
            "max_tokens": max_tokens,
            "stream": False,
            "logprobs": True,
            "top_logprobs": 1,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        req = Request(
            self.endpoint + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": self.config["api_key"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=1800) as response:
                return json.load(response)
        except HTTPError as exc:
            # Never log provider bodies: they can echo credentials/private input.
            raise FleetError("HTTP_" + str(exc.code)) from None
