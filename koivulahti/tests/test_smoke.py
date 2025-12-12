import json
import os
import time
import unittest
import urllib.error
import urllib.request


API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8082")
GATEWAY_BASE_URL = os.getenv("LLM_GATEWAY_BASE_URL", "http://localhost:8081")
DEFAULT_TIMEOUT_S = float(os.getenv("SMOKE_TIMEOUT_S", "5"))


def http_json(method: str, url: str, data: dict | None = None, timeout: float = DEFAULT_TIMEOUT_S):
    body = None
    req = urllib.request.Request(url, method=method.upper())
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data=body, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8")
        return resp.status, json.loads(payload)


def wait_for_health(url: str, tries: int = 30, delay_s: float = 1.0):
    last_err: Exception | None = None
    for _ in range(tries):
        try:
            status, data = http_json("GET", url)
            if status == 200 and isinstance(data, dict) and data.get("status") == "ok":
                return
        except Exception as e:  # noqa: BLE001
            last_err = e
        time.sleep(delay_s)
    raise RuntimeError(f"Health check did not pass for {url}: {last_err}")


class SmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wait_for_health(f"{API_BASE_URL}/health")
        wait_for_health(f"{GATEWAY_BASE_URL}/health")

    def test_api_health(self):
        status, data = http_json("GET", f"{API_BASE_URL}/health")
        self.assertEqual(status, 200)
        self.assertEqual(data.get("status"), "ok")

    def test_api_events_and_posts(self):
        status, events = http_json("GET", f"{API_BASE_URL}/events?limit=5")
        self.assertEqual(status, 200)
        self.assertIsInstance(events, list)
        status, posts = http_json("GET", f"{API_BASE_URL}/posts?limit=5")
        self.assertEqual(status, 200)
        self.assertIsInstance(posts, list)

    def test_gateway_generate(self):
        payload = {
            "prompt": "Kirjoita CHAT-julkaisu tapahtumasta. Tyyppi: SMALL_TALK. Paikka: place_kahvio.",
            "channel": "CHAT",
            "author_id": "npc_sanni",
            "source_event_id": "evt_test_001",
            "context": {"event": {"id": "evt_test_001", "type": "SMALL_TALK"}},
            "temperature": 0.3,
        }
        status, data = http_json("POST", f"{GATEWAY_BASE_URL}/generate", payload, timeout=30.0)
        self.assertEqual(status, 200)
        for key in ("channel", "author_id", "source_event_id", "tone", "text", "tags"):
            self.assertIn(key, data)
        self.assertNotEqual(data.get("tags"), ["stub"])
        self.assertFalse(str(data.get("text", "")).startswith("[stub]"))


if __name__ == "__main__":
    unittest.main(verbosity=2)

