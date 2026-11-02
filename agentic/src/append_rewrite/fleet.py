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
        if self.config.get("inference_transport") == "sse":
            return self.stream(body, journal, deadline)
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

    def stream(self, body, journal, deadline):
        body = dict(body, stream=True, stream_options={"include_usage": True})
        req = Request(
            self.endpoint + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": self.config["api_key"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(
                req, timeout=min(1800, max(1, deadline - time.time()))
            ) as response:
                with (journal / "events.jsonl").open("x") as log:

                    def events():
                        for raw in response:
                            if time.time() > deadline:
                                raise TimeoutError("SourceTaskAgentTimeout")
                            line = raw.decode().strip()
                            if not line.startswith("data:"):
                                continue
                            payload = line[5:].strip()
                            if payload == "[DONE]":
                                yield None
                                return
                            event = json.loads(payload)
                            log.write(json.dumps(event) + "\n")
                            log.flush()
                            yield event

                    return assemble_stream(events())
        except HTTPError as exc:
            raise FleetError("HTTP_" + str(exc.code)) from None


def assemble_stream(events):
    content = []
    calls = {}
    finish = None
    done = False
    usage = {}
    identity = {}
    for event in events:
        if event is None:
            done = True
            break
        if event.get("error"):
            raise FleetError("StreamProviderError")
        identity.update({k: event[k] for k in ("id", "model") if k in event})
        if event.get("usage"):
            usage = event["usage"]
        for choice in event.get("choices", []):
            if choice.get("index", 0) != 0:
                raise FleetError("UnexpectedMultipleChoices")
            if choice.get("finish_reason"):
                finish = choice["finish_reason"]
            delta = choice.get("delta", {})
            if delta.get("content"):
                content.append(delta["content"])
            for part in delta.get("tool_calls") or []:
                dst = calls.setdefault(
                    part["index"],
                    {
                        "id": "",
                        "type": "function",
                        "function": {"name": "", "arguments": ""},
                    },
                )
                if part.get("id"):
                    dst["id"] += part["id"]
                for key in ("name", "arguments"):
                    dst["function"][key] += part.get("function", {}).get(key, "") or ""
    if not done or not finish:
        raise FleetError("IncompleteSSE")
    message = {"role": "assistant", "content": "".join(content) or None}
    if calls:
        message["tool_calls"] = [calls[k] for k in sorted(calls)]
    return identity | {
        "choices": [{"index": 0, "message": message, "finish_reason": finish}],
        "usage": usage,
    }
