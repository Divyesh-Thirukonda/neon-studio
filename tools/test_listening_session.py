#!/usr/bin/env python3
"""Tests for the human sound check.

Run with:  /usr/bin/python3 -m unittest tools/test_listening_session.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import listening_session as ls  # noqa: E402
from fill_in_blanks import merge_gaps  # noqa: E402


def clip(name, start, bars):
    return {"id": f"clip-{ls.slugify(name)}", "name": name, "startBar": start, "bars": bars, "lane": 0, "color": "#ffffff", "type": "audio"}


def track(track_id, clips):
    return {"id": track_id, "name": track_id.title(), "kind": "audio", "file": None, "instrument": None,
            "color": "#ffffff", "gain": 0.8, "pan": 0.0, "steps": [], "clips": clips, "effects": []}


def recipe(item_id, section):
    return {"id": item_id, "section": section, "label": section, "detail": "", "status": "implemented", "trackIds": []}


def project_from(recipe_items, tracks):
    """A project shaped like the materializer writes, with only what the tool reads."""
    return {
        "id": "test-song",
        "name": "Test Song",
        "keyCenter": "E Minor",
        "snapshot": {"bpm": 142, "snap": "1/4", "loopEnabled": False, "loopStartBar": 0, "loopEndBar": 8,
                     "tracks": tracks, "controls": {}, "notes": [], "automationLanes": [], "recipe": recipe_items},
    }


def five_section_project():
    """Intro / build / drop / second drop / outro, with the recipe deliberately out of bar order."""
    recipe_items = [
        recipe("hook", "Hook"),  # not a place in the song; must be skipped
        recipe("drop-2", "Drop 2"),
        recipe("intro", "Intro"),
        recipe("outro", "Outro"),
        recipe("build-1", "Build 1"),
        recipe("drop-1", "Drop 1"),
        recipe("mix", "Mix"),
    ]
    tracks = [
        track("lead", [clip("Intro hook fragments", 0, 8), clip("Drop 1 hook", 16, 16), clip("Drop 2 hook", 40, 16), clip("Outro hook echo", 56, 8)]),
        track("drums", [clip("Build 1 roll", 8, 8), clip("Build clap roll", 8, 8), clip("Drop 1 drums", 16, 16), clip("Drop 2 drums", 40, 16)]),
        track("fx", [clip("Drop 1 impact", 16, 1)]),
    ]
    return project_from(recipe_items, tracks)


def spec_from(gaps=None):
    return {"projectId": "test-song", "titleHint": "Test Song", "sections": [],
            "fillInBlanks": {"styleLane": "bright_future_bass", "decisions": [], "gaps": list(gaps or [])}}


def inferred_gap(requirement_id):
    return {"id": requirement_id, "label": "guess", "why": "", "step": "guessed step", "soundCheckArea": "Arrangement",
            "roles": [], "confidence": "medium", "source": "rubric"}


def measured_gap(requirement_id):
    gap = inferred_gap(requirement_id)
    gap.update({"confidence": "measured", "source": "sound-check", "step": "measured step"})
    return gap


class SectionDerivationTests(unittest.TestCase):
    def test_sections_come_out_in_bar_order_with_the_right_types(self):
        sections = ls.derive_sections(five_section_project())
        self.assertEqual([s["id"] for s in sections], ["intro", "build-1", "drop-1", "drop-2", "outro"])
        self.assertEqual([s["type"] for s in sections], ["intro", "build", "drop", "second_drop", "outro"])
        self.assertEqual([(s["startBar"], s["bars"]) for s in sections], [(0, 8), (8, 8), (16, 16), (40, 16), (56, 8)])

    def test_recipe_headings_that_are_not_places_are_skipped(self):
        ids = [s["id"] for s in ls.derive_sections(five_section_project())]
        self.assertNotIn("hook", ids)
        self.assertNotIn("mix", ids)

    def test_a_project_with_no_recipe_uses_clip_names(self):
        project = five_section_project()
        project["snapshot"]["recipe"] = []
        sections = ls.derive_sections(project)
        self.assertEqual([s["type"] for s in sections], ["intro", "build", "drop", "second_drop", "outro"])

    def test_a_project_with_nothing_to_go_on_is_one_section(self):
        project = project_from([], [track("lead", [clip("Loop", 0, 8)])])
        sections = ls.derive_sections(project)
        self.assertEqual(len(sections), 1)
        self.assertEqual(sections[0]["id"], "song")
        self.assertEqual(sections[0]["bars"], 8)

    def test_unplaced_sections_fall_back_to_canonical_order(self):
        project = project_from([recipe("outro", "Outro"), recipe("break", "Break"), recipe("intro", "Intro")], [])
        self.assertEqual([s["type"] for s in ls.derive_sections(project)], ["intro", "break", "outro"])

    def test_derivation_is_deterministic(self):
        once = ls.build_questions(five_section_project())
        twice = ls.build_questions(deepcopy(five_section_project()))
        self.assertEqual(json.dumps(once, sort_keys=True), json.dumps(twice, sort_keys=True))


class QuestionTests(unittest.TestCase):
    def setUp(self):
        self.payload = ls.build_questions(five_section_project())
        self.by_id = {s["id"]: s for s in self.payload["sections"]}

    def keys(self, section_id):
        return [q["id"].split(".", 1)[1] for q in self.by_id[section_id]["questions"]]

    def test_each_section_type_gets_its_own_questions(self):
        self.assertEqual(self.keys("intro"), ["fullness", "muddy_harsh", "notes"])
        self.assertEqual(self.keys("build-1"), ["tension", "fullness", "muddy_harsh", "notes"])
        self.assertEqual(self.keys("drop-1"), ["lands", "fullness", "hum", "notes"])
        self.assertEqual(self.keys("drop-2"), ["compare", "fullness", "muddy_harsh", "notes"])
        self.assertEqual(self.keys("outro"), ["ends", "fullness", "notes"])

    def test_two_or_three_questions_plus_free_text(self):
        for section in self.payload["sections"]:
            choice = [q for q in section["questions"] if not q.get("freeText")]
            free = [q for q in section["questions"] if q.get("freeText")]
            self.assertIn(len(choice), (2, 3), section["id"])
            self.assertEqual(len(free), 1)
            self.assertEqual(free[0]["id"], f"{section['id']}.notes")

    def test_every_option_has_a_map_entry_and_maps_name_real_requirements(self):
        from production_rubric import requirement_by_id
        for section in self.payload["sections"]:
            for question in section["questions"]:
                if question.get("freeText"):
                    continue
                self.assertEqual(set(question["maps"]), set(question["options"]))
                for ids in question["maps"].values():
                    for requirement_id in ids:
                        self.assertIsNotNone(requirement_by_id(requirement_id), requirement_id)

    def test_question_wording_avoids_jargon(self):
        jargon = ("sidechain", "hpf", "eq", "automation", "lfo", "compressor", "stereo")
        for bank in ls.QUESTION_BANK.values():
            for word in jargon:
                self.assertNotIn(word, bank["text"].lower())


class ApplyTests(unittest.TestCase):
    def apply(self, answers, gaps=None):
        spec = spec_from(gaps)
        result = ls.apply_answers(five_section_project(), spec, {"answers": answers})
        return result, spec

    def test_too_empty_on_the_drop_becomes_a_human_gap(self):
        result, spec = self.apply([{"questionId": "drop-1.fullness", "option": "too empty"}])
        ids = [s["id"] for s in result["steps"]]
        self.assertEqual(ids, ["roles_need_content", "texture_bed"])
        step = result["steps"][0]
        self.assertEqual(step["confidence"], "human")
        self.assertEqual(step["section"], "drop-1")
        self.assertEqual(step["requirementId"], "roles_need_content")
        self.assertIn("You said Drop 1 'too empty'", step["evidence"])
        self.assertTrue(step["step"])
        spec_ids = [g["id"] for g in spec["fillInBlanks"]["gaps"]]
        self.assertEqual(spec_ids, ["roles_need_content", "texture_bed"])
        self.assertEqual(result["summary"], "2 steps added from 1 answer")
        self.assertEqual(result["iterationNote"], "Listening session: 1 answer, 2 steps added")

    def test_answers_that_map_to_nothing_add_no_steps(self):
        result, spec = self.apply([{"questionId": "drop-1.lands", "option": "yes"}])
        self.assertEqual(result["steps"], [])
        self.assertEqual(result["summary"], "0 steps added from 1 answer")
        self.assertEqual(spec["fillInBlanks"]["gaps"], [])

    def test_human_outranks_inferred_but_not_measured(self):
        result, spec = self.apply(
            [{"questionId": "drop-1.fullness", "option": "too empty"}],
            gaps=[inferred_gap("roles_need_content"), measured_gap("texture_bed")],
        )
        by_id = {g["id"]: g for g in spec["fillInBlanks"]["gaps"]}
        self.assertEqual(by_id["roles_need_content"]["confidence"], "human")
        self.assertEqual(by_id["texture_bed"]["confidence"], "measured")
        self.assertEqual(by_id["texture_bed"]["step"], "measured step")
        self.assertEqual(result["added"], ["roles_need_content"])
        self.assertEqual(result["confirmedMeasured"], ["texture_bed"])

    def test_merge_gaps_ranks_measured_over_human_over_inferred(self):
        human = ls.human_gap("gain_ladder", "drop-1", "You said so")
        merged = merge_gaps([inferred_gap("gain_ladder")], [human])
        self.assertEqual(merged[0]["confidence"], "human")
        merged = merge_gaps(merged, [measured_gap("gain_ladder")])
        self.assertEqual(merged[0]["confidence"], "measured")
        merged = merge_gaps(merged, [human])
        self.assertEqual(merged[0]["confidence"], "measured")
        merged = merge_gaps(merged, [inferred_gap("gain_ladder")])
        self.assertEqual(merged[0]["confidence"], "measured")

    def test_free_text_is_preserved_and_keyworded(self):
        result, spec = self.apply([{"questionId": "drop-1.notes", "text": "the bass feels muddy under the kick"}])
        self.assertEqual(result["notes"], ["the bass feels muddy under the kick"])
        self.assertEqual(spec["listeningNotes"][0]["text"], "the bass feels muddy under the kick")
        ids = [s["id"] for s in result["steps"]]
        self.assertIn("hpf_ladder", ids)
        self.assertIn("low_end_ownership", ids)
        self.assertIn("You wrote about Drop 1", result["steps"][0]["evidence"])

    def test_free_text_with_no_keywords_is_still_kept(self):
        result, _spec = self.apply([{"questionId": "outro.notes", "text": "lovely"}])
        self.assertEqual(result["notes"], ["lovely"])
        self.assertEqual(result["steps"], [])
        self.assertEqual(result["summary"], "0 steps added from 1 answer, 1 note kept")

    def test_unknown_question_ids_warn_instead_of_failing(self):
        result, _spec = self.apply([
            {"questionId": "bridge.fullness", "option": "too empty"},
            {"questionId": "drop-1.fullness", "option": "somewhat"},
            {"questionId": "drop-1.lands", "option": "it's flat"},
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["warnings"]), 2)
        self.assertIn("unknown question: bridge.fullness", result["warnings"][0])
        self.assertEqual([s["id"] for s in result["steps"]], ["duck_parameters", "gain_ladder", "low_end_ownership"])
        self.assertEqual(result["summary"], "3 steps added from 1 answer")

    def test_the_same_requirement_from_two_sections_merges_evidence(self):
        result, _spec = self.apply([
            {"questionId": "drop-1.fullness", "option": "too empty"},
            {"questionId": "intro.fullness", "option": "too empty"},
        ])
        step = result["steps"][0]
        self.assertEqual(step["section"], "drop-1")
        self.assertEqual(step["sections"], ["drop-1", "intro"])
        self.assertIn("Drop 1", step["evidence"])
        self.assertIn("Intro", step["evidence"])

    def test_missing_answers_list_is_an_error(self):
        with self.assertRaises(ValueError):
            ls.apply_answers(five_section_project(), spec_from(), {"nope": []})


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project_path = self.root / "test-song.neon.json"
        self.spec_path = self.root / "transcript_spec.json"
        self.answers_path = self.root / "answers.json"
        self.project_path.write_text(json.dumps(five_section_project()), encoding="utf-8")
        self.spec_path.write_text(json.dumps(spec_from([inferred_gap("roles_need_content")])), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        command = [sys.executable, str(Path(ls.__file__)), "--root", str(self.root), "--project", str(self.project_path), *args]
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_questions_json_last_line_is_one_object(self):
        completed = self.run_cli("questions", "--format", "json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual([s["id"] for s in payload["sections"]], ["intro", "build-1", "drop-1", "drop-2", "outro"])

    def test_questions_markdown(self):
        completed = self.run_cli("--format", "markdown", "questions")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("## Drop 1 (bars 16–32)", completed.stdout)
        self.assertIn("Does the drop land?", completed.stdout)

    def test_apply_writes_the_spec_and_warns_when_songlab_has_no_session(self):
        self.answers_path.write_text(json.dumps({"answers": [
            {"questionId": "drop-1.fullness", "option": "too empty"},
            {"questionId": "drop-1.notes", "text": "nice"},
            {"questionId": "nowhere.notes", "text": "ignored"},
        ]}), encoding="utf-8")
        completed = self.run_cli("--spec", str(self.spec_path), "--project-id", "no-such-session-xyz",
                                 "apply", "--answers", str(self.answers_path))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["summary"], "2 steps added from 2 answers, 1 note kept")
        self.assertFalse(payload["iterationLogged"])
        self.assertTrue(any("unknown question: nowhere.notes" in w for w in payload["warnings"]))
        self.assertTrue(any("Could not log the iteration note" in w for w in payload["warnings"]))
        written = json.loads(self.spec_path.read_text(encoding="utf-8"))
        gaps = {g["id"]: g for g in written["fillInBlanks"]["gaps"]}
        self.assertEqual(gaps["roles_need_content"]["confidence"], "human")
        self.assertEqual(gaps["roles_need_content"]["section"], "drop-1")
        self.assertEqual(gaps["texture_bed"]["confidence"], "human")
        self.assertEqual(written["listeningNotes"][0]["text"], "nice")

    def test_missing_project_is_a_json_error(self):
        command = [sys.executable, str(Path(ls.__file__)), "--root", str(self.root), "--project", str(self.root / "missing.neon.json"), "questions"]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
