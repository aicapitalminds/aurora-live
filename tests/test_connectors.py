import unittest
from unittest import mock

from aurora_connectors import maybe_handle_connector, open_browser_url


class AuroraConnectorTests(unittest.TestCase):
    def test_weather_prompt_is_handled(self):
        with mock.patch("aurora_connectors.get_weather_summary", return_value="Weather for Kendal: sunny-ish."):
            result = maybe_handle_connector("please check weather in Kendal")
        self.assertTrue(result.handled)
        self.assertIn("Weather for Kendal", result.prompt)

    def test_weather_can_open_browser(self):
        with mock.patch("aurora_connectors.get_weather_summary", return_value="Weather ok."), mock.patch(
            "aurora_connectors.open_browser_url", return_value="https://www.google.com/search?q=weather+Kendal"
        ):
            result = maybe_handle_connector("open browser and check weather in Kendal")
        self.assertTrue(result.handled)
        self.assertIn("opened a browser", result.prompt.lower())
        self.assertTrue(result.opened_url.startswith("https://"))

    def test_open_url_is_handled(self):
        with mock.patch("aurora_connectors.open_browser_url", return_value="https://example.com"):
            result = maybe_handle_connector("open browser example.com")
        self.assertTrue(result.handled)
        self.assertEqual(result.opened_url, "https://example.com")

    def test_non_connector_text_is_ignored(self):
        result = maybe_handle_connector("hello Aurora how are you")
        self.assertFalse(result.handled)


if __name__ == "__main__":
    unittest.main()
