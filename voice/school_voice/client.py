"""Authenticated HTTPS, with no redirects, proxies, audio, retries or remote commands."""
import json
import secrets
import ssl
import time
from urllib.request import Request, build_opener, HTTPSHandler, HTTPRedirectHandler, ProxyHandler
from .policy import catalog, trusted_file
from pathlib import Path
from .routing import candidates


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Laya redirects are not permitted")


def decide(text: str, policy: dict) -> str:
    if not isinstance(text, str) or not 1 <= len(text) <= 500:
        raise ValueError("Please use a shorter instruction")
    choices = candidates(text, policy)
    if not choices:
        return "unknown"
    # Stable bounded choice slots let new parent-approved apps work without
    # changing the Laya server's device enrollment. Slot labels are data only.
    mapped = {f'choice_{i}': key for i, key in enumerate(choices)} if policy.get('parent_controls') else {key: key for key in choices}
    wire_choices = {slot: choices[key] for slot, key in mapped.items()}
    server = policy["server"]
    ca = trusted_file(Path(server["ca_file"]))
    token = trusted_file(Path(server["token_file"])).read_text().strip()
    if len(token) < 32 or any(c.isspace() for c in token):
        raise ValueError("Invalid device pairing token")
    request_id = secrets.token_hex(16)
    payload = {"version": 1, "id": request_id, "text": text, "actions": wire_choices}
    context = ssl.create_default_context(cafile=str(ca))
    context.hostname_checks_common_name = False
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPSHandler(context=context))
    started = time.monotonic()
    request = Request(server["url"].rstrip("/") + "/v1/decide", data=json.dumps(payload).encode(),
                      headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    with opener.open(request, timeout=12) as response:
        body = response.read(4097)
    if len(body) > 4096 or time.monotonic() - started > 15:
        raise ValueError("Laya's response was late or invalid. Please try again.")
    result = json.loads(body)
    if not isinstance(result, dict) or set(result) != {"version", "id", "action"} or result["version"] != 1 or result["id"] != request_id:
        raise ValueError("Invalid Laya response")
    action = result["action"]
    if not isinstance(action, str) or (action != "unknown" and action not in wire_choices):
        raise ValueError("Laya suggested an action that is not approved")
    return mapped.get(action, 'unknown')
