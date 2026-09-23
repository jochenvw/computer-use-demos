import unittest

from epic_adapter import progress
from epic_adapter.models import ClinicalResource, ResourceType, SourceRecord
from epic_adapter.narrative import describe_step, summarize


def resource(kind, data, source_id="r1"):
    return ClinicalResource(
        resource_type=kind, source_id=source_id, data=data,
        provenance=SourceRecord(source="test"),
    )


class NarrativeTests(unittest.TestCase):
    def test_steps_are_readable(self):
        self.assertEqual(
            ("query", "Writing and running SQL in SSMS: SELECT 1"),
            describe_step("sql-desktop", "run_query", {"sql": "SELECT\n  1"}),
        )
        kind, text = describe_step("sql-desktop", "observe", {}, first_observe=True)
        self.assertIn("SQL Server Management Studio", text)
        kind, text = describe_step("epic-browser", "stop", {"reason": "session_expired"})
        self.assertEqual("warn", kind)
        self.assertIn("log in again", text)

    def test_results_are_summarized(self):
        self.assertEqual(
            "Rate: 63 /min (2026-09-01)",
            summarize(resource(ResourceType.observations, {
                "code": {"text": "Rate"}, "valueQuantity": {"value": 63, "unit": "/min"},
                "effectiveDateTime": "2026-09-01T10:00:00Z",
            })),
        )
        self.assertEqual(
            "Patient: Maria Rossi · female · 1961-04-02",
            summarize(resource(ResourceType.patient, {
                "name": [{"given": ["Maria"], "family": "Rossi"}],
                "gender": "female", "birthDate": "1961-04-02",
            })),
        )
        self.assertTrue(summarize(resource(
            ResourceType.ecg, {"conclusion": "Printed on ECG: Rate 63"},
        )).startswith("ECG report: Printed on ECG"))

    def test_story_feeds_active_timeline_only(self):
        timeline = []
        progress.story("step", "before")
        progress.begin(timeline, "Files", "job1")
        self.assertEqual("Files", progress.current()["label"])
        progress.story("thinking", "  looking   at the ECG ")
        progress.story("bogus", "x")
        progress.end()
        progress.story("step", "after")
        self.assertEqual(["thinking", "info"], [e["kind"] for e in timeline])
        self.assertEqual("looking at the ECG", timeline[0]["text"])
        self.assertIsNone(progress.current()["job"])

    def test_window_titles_match_opened_files(self):
        from epic_adapter.desktop import _title_matches

        names = ["assets", "ecg.jpg"]
        for title in ("assets", r"C:\Users\demo\Desktop\assets", "ecg - Paint",
                      "ecg.jpg - Photos"):
            self.assertTrue(_title_matches(title, names), title)
        for title in ("Mijn Dossier - Microsoft Edge", "ecgviewer", "assets backup"):
            self.assertFalse(_title_matches(title, names), title)


if __name__ == "__main__":
    unittest.main()
