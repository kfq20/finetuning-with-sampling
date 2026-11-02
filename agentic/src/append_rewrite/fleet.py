"""Controller-only durable Fleet Jobs. POST once; reconnect by saved job ID."""

from __future__ import annotations
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from http.client import IncompleteRead, RemoteDisconnected
from .collect import dump


class FleetError(RuntimeError):
    pass


class Fleet:
    def __init__(self, private_config: Path):
        if private_config.stat().st_mode & 0o077:
            raise PermissionError("Fleet controller config must be private")
        self.config = json.loads(private_config.read_text())
        self.endpoint = self.config["base_url"] + "/d/" + self.config["task_id"] + "/v1"

    def request(self, route, body=None):
        req = Request(
            self.endpoint + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "x-api-key": self.config["api_key"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=90) as response:
                return json.load(response)
        except HTTPError as exc:
            raise FleetError("HTTP_" + str(exc.code)) from None

    def chat(self, messages, tools=None, max_tokens=32768, *, journal, deadline):
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
            body.update(tools=tools, tool_choice="auto")
        # Exclusive intent prevents accidental resubmission if POST acknowledgement is lost.
        journal.mkdir(parents=True, exist_ok=False, mode=0o700)
        dump(
            journal / "intent.json",
            {"status": "submission_started", "automatic_retry": False},
        )
        accepted = self.request("/control/jobs", {"requests": [body]})
        dump(journal / "accepted.json", accepted)
        job_id = accepted["job_id"]
        errors = 0
        while time.time() < deadline:
            try:
                result = self.request("/control/jobs/" + job_id + "/result")
            except (
                URLError,
                IncompleteRead,
                RemoteDisconnected,
                TimeoutError,
                FleetError,
            ) as exc:
                # GET reconnects never generate a second paid completion. Auth/policy errors remain fatal.
                if isinstance(exc, FleetError) and str(exc) in (
                    "HTTP_401",
                    "HTTP_403",
                    "HTTP_404",
                ):
                    raise
                errors += 1
                dump(
                    journal / "read-errors.json",
                    {
                        "count": errors,
                        "last_type": type(exc).__name__,
                        "job_id": job_id,
                    },
                )
                time.sleep(5)
                continue
            status = result.get("status")
            entries = result.get("results") or []
            if status in ("completed", "partial", "failed", "cancelled"):
                dump(journal / "result.json", result)
                if (
                    len(entries) == 1
                    and entries[0].get("status") == "completed"
                    and entries[0].get("response")
                ):
                    return entries[0]["response"]
                raise FleetError("JobTerminal:" + str(status))
            dump(
                journal / "progress.json",
                {"status": status, "job_id": job_id, "read_errors": errors},
            )
            time.sleep(3)
        raise TimeoutError("DurableJobDeadline:" + job_id)
