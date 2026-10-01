import io
import unittest

from rich.console import Console

from epic_adapter import console as ui
from epic_adapter import progress


def render(renderable, width: int, height: int = 40) -> str:
    out = Console(width=width, height=height, file=io.StringIO(), legacy_windows=False,
                  force_terminal=False, color_system=None)
    with out.capture() as capture:
        out.print(renderable)
    return capture.get()


class TitleTests(unittest.TestCase):
    def test_big_letters_are_four_rows_of_block_glyphs(self):
        rows = ui.big_text(ui.TITLE + " " + ui.EVENT, "bold").plain.splitlines()
        self.assertEqual(4, len(rows))
        self.assertLessEqual(set("".join(rows)), set("█▀▄ "))

    def test_title_uses_big_letters_on_projector_and_zoomed_widths(self):
        wide = render(ui.title_block(160, 40), 160).splitlines()
        zoomed = render(ui.title_block(90, 28), 90).splitlines()
        self.assertEqual(4, len([row for row in wide if row.strip()]))
        self.assertEqual(8, len([row for row in zoomed if row.strip()]))
        self.assertIn("█", "".join(zoomed))

    def test_title_falls_back_to_plain_text_when_very_narrow(self):
        self.assertIn("RETRIEVAL AGENT", render(ui.title_block(60, 30), 60))

    def test_every_title_letter_has_a_glyph(self):
        for char in ui.TITLE + ui.EVENT:
            self.assertIn(char, ui._GLYPHS)

    def test_agent_name_and_capability_are_in_the_header(self):
        header = render(ui.Header(ui.Settings.from_env(), 8000), 200)
        self.assertIn("DATA RETRIEVAL AGENT - OSPEDALE DI MONTALCINO", header)
        self.assertIn("maps it to the requested data standard", header)
        self.assertNotIn("portal", header.lower())

    def test_task_and_handover_lines_are_badged(self):
        feed = ui.Feed()
        for kind, text in (("task", "Retrieve all relevant medical information for patient Anna Ricci."),
                           ("start", "New request"), ("handover", "Handing over to the MDT dashboard")):
            feed.lines.append(("10:00:00", kind, 20, text))
        text = render(ui.FeedView(feed), 160, 14)
        self.assertIn("TASK", text)
        self.assertIn("HANDOVER", text)
        self.assertIn("patient Anna Ricci.", text)


class StatusTests(unittest.TestCase):
    def setUp(self):
        progress.end()
        progress._last = None

    def tearDown(self):
        progress.end()
        progress._last = None

    def test_status_follows_ask_watch_receive(self):
        self.assertIn("Ready", render(ui.status_row(), 160))
        progress.begin([], "1 - Clinical data from the EMR", "job")
        self.assertIn("Working", render(ui.status_row(), 160))
        progress.story("done", "Done in 84 s · 9 clinical item(s)")
        progress.end()
        self.assertIn("Delivered", render(ui.status_row(), 160))
        progress.begin([], "1 - Clinical data from the EMR", "job2")
        progress.story("error", "Stopped after 3 s · session_expired")
        progress.end()
        self.assertIn("Stopped", render(ui.status_row(), 160))


if __name__ == "__main__":
    unittest.main()
