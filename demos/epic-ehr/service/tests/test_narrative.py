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
        kind, text = describe_step("emr-browser", "stop", {"reason": "session_expired"})
        self.assertEqual("warn", kind)
        self.assertIn("EMR session", text)
        self.assertIn("PACS", describe_step("pacs-viewer", "click", {"x": 1, "y": 2})[1])
        self.assertIn("the EMR", describe_step("emr-browser", "observe", {})[1])

    def test_results_are_summarized(self):
        self.assertEqual(
            "Rate: 104 /min (2026-09-18)",
            summarize(resource(ResourceType.observations, {
                "code": {"text": "Rate"}, "valueQuantity": {"value": 104, "unit": "/min"},
                "effectiveDateTime": "2026-09-18T22:50:00Z",
            })),
        )
        self.assertEqual(
            "Patient: Anna Ricci · female · 1971-03-14",
            summarize(resource(ResourceType.patient, {
                "name": [{"given": ["Anna"], "family": "Ricci"}],
                "gender": "female", "birthDate": "1971-03-14",
            })),
        )
        self.assertTrue(summarize(resource(
            ResourceType.ecg, {"conclusion": "Printed on ECG: Rate 104"},
        )).startswith("ECG report: Printed on ECG"))
        self.assertEqual(
            "Imaging report (RM fegato): two liver lesions",
            summarize(resource(ResourceType.imaging, {
                "code": {"text": "RM fegato"}, "conclusion": "two liver lesions",
            })),
        )

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

        names = ["TUS-2026-0417", "ecg.jpg"]
        for title in ("TUS-2026-0417", r"C:\EpicDemo\files\TUS-2026-0417", "ecg - Paint",
                      "ecg.jpg - Photos"):
            self.assertTrue(_title_matches(title, names), title)
        for title in ("SanitaCartella - Microsoft Edge", "ecgviewer", "TUS-2026-0417 backup"):
            self.assertFalse(_title_matches(title, names), title)


if __name__ == "__main__":
    unittest.main()
