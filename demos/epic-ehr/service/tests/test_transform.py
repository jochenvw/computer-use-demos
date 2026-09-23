import json
import unittest
from unittest import mock

from epic_adapter import transform as transform_module


class _Response:
    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self._data


class _Credential:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get_token(self, scope):
        return mock.Mock(token="t")


def _settings():
    return mock.Mock(
        foundry_endpoint="https://example.invalid", model_deployment="dep",
        reasoning_effort="low",
    )


class TransformTests(unittest.TestCase):
    def test_maps_via_responses_api(self):
        seen = {}

        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["body"] = json.loads(request.data)
            return _Response({"output": [{"type": "message", "content": [
                {"type": "output_text", "text": '{"labuitslagen": [{"waarde": 9.8}]}'},
            ]}]})

        with mock.patch("azure.identity.DefaultAzureCredential", _Credential), \
                mock.patch.object(transform_module.urllib.request, "urlopen", fake_urlopen):
            out = transform_module.transform(_settings(), {"observations": []}, '{"labuitslagen": []}')
        self.assertEqual({"labuitslagen": [{"waarde": 9.8}]}, out["result"])
        self.assertEqual("https://example.invalid/openai/v1/responses", seen["url"])
        self.assertEqual("dep", seen["body"]["model"])
        self.assertIn("TARGET SCHEMA", seen["body"]["input"])

    def test_rejects_empty_or_huge_schema(self):
        with self.assertRaises(ValueError):
            transform_module.transform(_settings(), {}, "  ")
        with self.assertRaises(ValueError):
            transform_module.transform(_settings(), {}, "x" * 20_000)


if __name__ == "__main__":
    unittest.main()
