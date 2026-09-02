#!/usr/bin/env python3
"""Tests for the human sound check.

Run with:  /usr/bin/python3 -m unittest tools/test_listening_session.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import os
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import listening_session as ls  # noqa: E402
import llm  # noqa: E402

# The deterministic path is what these tests cover. A real key may exist on
# the machine running them, so the model is switched off while this module
# runs - for this process and for the CLI subprocesses it spawns - and put
# back afterwards so other test modules see the environment they expect. The
# model tests below inject a fake transport instead.
_PREVIOUS_NEON_AI = None


def setUpModule():
    global _PREVIOUS_NEON_AI
    _PREVIOUS_NEON_AI = os.environ.get("NEON_AI")
    os.environ["NEON_AI"] = "off"


def tearDownModule():
    if _PREVIOUS_NEON_AI is None:
        os.environ.pop("NEON_AI", None)
    else:
        os.environ["NEON_AI"] = _PREVIOUS_NEON_AI
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

    def test_sections_carry_no_working_fields(self):
        for section in ls.derive_sections(five_section_project()):
            self.assertEqual(sorted(section), ["bars", "id", "label", "startBar", "type"], section["id"])

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

    def test_an_answer_to_a_key_the_section_could_not_be_asked_is_refused(self):
        # The model may pick any bank key at question time except the ones KEY_ONLY_FOR
        # reserves; apply time draws the same line, so "intro.lands" is unknown, not mapped.
        result, _spec = self.apply([
            {"questionId": "intro.lands", "option": "it's flat"},
            {"questionId": "drop-1.compare", "option": "smaller"},
            {"questionId": "outro.lands", "option": "it's flat"},
            {"questionId": "drop-2.compare", "option": "smaller"},
        ])
        self.assertTrue(result["ok"])
        self.assertEqual(sorted(w.split("unknown question: ")[1] for w in result["warnings"]),
                         ["drop-1.compare", "intro.lands", "outro.lands"])
        self.assertTrue(all(step["section"] == "drop-2" for step in result["steps"]), result["steps"])
        self.assertGreater(len(result["steps"]), 0)

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


# ---------------------------------------------------------------------------
# The model path. Nothing here touches the network: a fake transport answers
# by looking at which role the tool asked it to play.
# ---------------------------------------------------------------------------

class FakeModel:
    """A Gemini-shaped transport that answers per role and records every call."""

    def __init__(self, questions=None, notes=None, whys=None):
        self.questions = questions
        self.notes = notes
        self.whys = whys
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        system = body.get("systemInstruction", {}).get("parts", [{}])[0].get("text", "")
        prompt = body["contents"][0]["parts"][0]["text"]
        if "listening session" in system and "question KEYS" in system:
            role, reply = "questions", self.questions
        elif "decide which production requirements" in system:
            role, reply = "notes", self.notes
        elif "explain production steps" in system:
            role, reply = "whys", self.whys
        else:
            role, reply = "unknown", None
        self.calls.append((role, prompt))
        text = reply if isinstance(reply, str) else json.dumps(reply if reply is not None else {})
        return 200, json.dumps({"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]})


def assist_with(fake):
    client = llm.Client("gemini", api_key="k", transport=fake, use_cache=False, env={"NEON_CONFIG_DIR": "/nonexistent"})
    return ls.Assist(client=client)


class ModelQuestionTests(unittest.TestCase):
    def test_the_role_states_the_limit_the_validator_enforces(self):
        self.assertIn(f"at most {ls.MAX_QUESTION_CHARS} characters", ls.QUESTIONS_ROLE)
        self.assertNotIn("140", ls.QUESTIONS_ROLE)
        self.assertNotIn("120", ls.QUESTIONS_ROLE)

    def test_the_keys_a_section_may_be_asked_cover_the_table_and_honour_the_reservations(self):
        for section_type, keys in ls.QUESTIONS_BY_SECTION_TYPE.items():
            allowed = ls.keys_for_section_type(section_type)
            self.assertTrue(set(keys) <= set(allowed), section_type)
            for key, types in ls.KEY_ONLY_FOR.items():
                self.assertEqual(key in allowed, section_type in types, (section_type, key))

    def test_model_rephrases_and_picks_keys_but_ids_options_and_maps_stay_the_banks(self):
        fake = FakeModel(questions={"sections": [
            {"id": "drop-1", "questions": [
                {"key": "lands", "text": "Does the drop hit after the clap roll?", "reason": "a drop with a roll before it"},
                {"key": "hum", "text": "Can you hum the square lead by now?"},
                {"key": "fullness", "text": "Does the drop feel full with the sub and chords in?"},
                {"key": "muddy_harsh", "text": "a fourth question that must be cut?"},
            ], "notesPrompt": "Anything else about the drop, like the hook echo?"},
            {"id": "intro", "questions": [
                {"key": "fullness", "text": "Is the filtered intro too bare?"},
                {"key": "hum", "text": "Can you already hum the hook fragments?"},
            ], "notesPrompt": "not a question"},
        ]})
        payload = ls.build_questions(five_section_project(), None, assist_with(fake))
        by_id = {s["id"]: s for s in payload["sections"]}
        self.assertEqual(len(fake.calls), 1, "one call for every section")
        self.assertEqual(fake.calls[0][0], "questions")
        self.assertIn('"drop-2"', fake.calls[0][1])

        drop = by_id["drop-1"]["questions"]
        self.assertEqual([q["id"] for q in drop], ["drop-1.lands", "drop-1.hum", "drop-1.fullness", "drop-1.notes"])
        self.assertEqual(drop[0]["text"], "Does the drop hit after the clap roll?")
        self.assertEqual(drop[0]["source"], "model")
        self.assertEqual(drop[0]["reason"], "a drop with a roll before it")
        self.assertEqual(drop[0]["bankText"], "Does the drop land?")
        self.assertEqual(drop[0]["options"], ls.QUESTION_BANK["lands"]["options"])
        self.assertEqual(drop[0]["maps"], {o: ls.QUESTION_BANK["lands"]["maps"][o] for o in ls.QUESTION_BANK["lands"]["options"]})
        self.assertEqual(drop[3]["text"], "Anything else about the drop, like the hook echo?")
        self.assertTrue(drop[3]["freeText"])

        intro = by_id["intro"]["questions"]
        self.assertEqual([q["id"] for q in intro], ["intro.fullness", "intro.hum", "intro.notes"])
        self.assertEqual(intro[2]["text"], "Anything else?", "a notes prompt that is not a question falls back")

        # Sections the model did not answer get the table.
        self.assertEqual([q["id"].split(".")[1] for q in by_id["outro"]["questions"]], ["ends", "fullness", "notes"])
        self.assertNotIn("source", by_id["outro"]["questions"][0])
        self.assertTrue(payload["ai"]["used"])
        self.assertEqual(payload["ai"]["provider"], "gemini")

    def test_bad_wording_unknown_keys_and_unknown_sections_are_dropped_and_noted(self):
        fake = FakeModel(questions={"sections": [
            {"id": "build-1", "questions": [
                {"key": "tension", "text": "Does the sidechain pump harder into the drop?"},
                {"key": "fullness", "text": "Is the build busy enough at 128 bpm?"},
                {"key": "loudness", "text": "Is it loud?"},
                {"key": "muddy_harsh", "text": "Do the clap rolls get harsh?"},
            ]},
            {"id": "nowhere", "questions": [{"key": "fullness", "text": "Full?"}]},
            {"id": "outro", "questions": [{"key": "ends", "text": "Does it end?"}, {"key": "compare", "text": "Bigger than the first drop?"}]},
        ]})
        payload = ls.build_questions(five_section_project(), None, assist_with(fake))
        by_id = {s["id"]: s for s in payload["sections"]}
        build = by_id["build-1"]["questions"]
        self.assertEqual([q["id"] for q in build], ["build-1.tension", "build-1.fullness", "build-1.muddy_harsh", "build-1.notes"])
        self.assertEqual(build[0]["text"], "Does the tension rise?", "jargon falls back to the bank text")
        self.assertEqual(build[0]["source"], "bank")
        self.assertEqual(build[1]["text"], "How full does this part feel?", "a number the model was not given falls back")
        self.assertEqual(build[2]["text"], "Do the clap rolls get harsh?")
        # Only one usable question for the outro: the table wins.
        self.assertEqual([q["id"].split(".")[1] for q in by_id["outro"]["questions"]], ["ends", "fullness", "notes"])
        dropped = payload["ai"]["dropped"]
        self.assertTrue(any("unknown key loudness" in d for d in dropped))
        self.assertTrue(any("unknown section nowhere" in d for d in dropped))
        self.assertTrue(any("build-1.tension wording rejected" in d for d in dropped))
        self.assertTrue(any("outro got 1 usable" in d for d in dropped))
        self.assertTrue(any("outro (outro) cannot take compare" in d for d in dropped))

    def test_a_nonsense_reply_leaves_the_questions_exactly_as_the_table(self):
        offline = ls.build_questions(five_section_project(), None, ls.Assist(enabled=False))
        for reply in ("not json at all", [1, 2, 3], {"sections": "nope"}):
            fake = FakeModel(questions=reply)
            payload = ls.build_questions(five_section_project(), None, assist_with(fake))
            self.assertEqual(payload["sections"], offline["sections"])
        # The last reply was JSON of the wrong shape: the adapter counts it as
        # an answer, and the tool says what it threw away.
        self.assertEqual(payload["ai"]["dropped"], ["questions: reply had no sections list"])

    def test_context_names_the_tracks_playing_and_what_is_on_file(self):
        fake = FakeModel(questions={"sections": []})
        spec = spec_from([dict(measured_gap("hpf_ladder"), section="drop-1", evidence="The sound check measured mud")])
        spec["listeningNotes"] = [{"section": "drop-1", "label": "Drop 1", "text": "bass too loud last time"}]
        ls.build_questions(five_section_project(), spec, assist_with(fake))
        prompt = fake.calls[0][1]
        self.assertIn("Drop 1 hook", prompt)
        self.assertIn("The sound check measured mud", prompt)
        self.assertIn("bass too loud last time", prompt)
        self.assertIn("Default wording", prompt)


class ModelApplyTests(unittest.TestCase):
    def apply(self, answers, fake, gaps=None):
        spec = spec_from(gaps)
        result = ls.apply_answers(five_section_project(), spec, {"answers": answers}, assist_with(fake))
        return result, spec

    def test_notes_are_read_by_the_model_with_the_persons_words_as_evidence(self):
        note = "the bass isn't muddy at all, but the vocal chop is missing in the second half"
        fake = FakeModel(
            notes={"notes": [{"index": 0, "requirementIds": ["roles_need_content", "not_a_requirement"],
                              "quote": "the vocal chop is missing in the second half",
                              "meaning": "Bring the vocal chop back for the second half of the drop.",
                              "doNotTouch": ["hpf_ladder", "low_end_ownership"]}]},
            whys={"steps": [], "listenerSummary": "", "iterationNote": ""},
        )
        result, spec = self.apply([{"questionId": "drop-1.notes", "text": note}], fake)
        self.assertEqual([s["id"] for s in result["steps"]], ["roles_need_content"], "the keyword table would have said muddy")
        step = result["steps"][0]
        self.assertEqual(step["reading"]["source"], "model")
        self.assertEqual(step["reading"]["quote"], "the vocal chop is missing in the second half")
        self.assertIn("You wrote about Drop 1: 'the vocal chop is missing in the second half'", step["evidence"])
        self.assertEqual(result["notes"], [note])
        kept = spec["listeningNotes"][0]
        self.assertEqual(kept["text"], note)
        self.assertEqual(kept["reading"]["requirementIds"], ["roles_need_content"])
        self.assertEqual(kept["doNotTouch"], ["hpf_ladder", "low_end_ownership"])
        self.assertEqual(result["noteReadings"][0]["source"], "model")
        self.assertTrue(any("unknown requirement not_a_requirement" in d for d in result["ai"]["dropped"]))
        self.assertEqual([c[0] for c in fake.calls], ["notes", "whys"])
        self.assertIn("Catalogue", fake.calls[0][1])

    def test_a_quote_that_is_not_in_the_note_falls_back_to_keywords(self):
        fake = FakeModel(
            notes={"notes": [
                {"index": 0, "requirementIds": ["outro_resolution"], "quote": "words the listener never wrote", "meaning": "x"},
                {"index": 7, "requirementIds": ["outro_resolution"], "quote": "muddy", "meaning": "x"},
            ]},
            whys={"steps": []},
        )
        result, spec = self.apply([{"questionId": "drop-1.notes", "text": "the bass feels muddy under the kick"}], fake)
        self.assertEqual([s["id"] for s in result["steps"]], ["hpf_ladder", "low_end_ownership", "duck_parameters"])
        self.assertNotIn("reading", result["steps"][0])
        self.assertEqual(result["noteReadings"][0]["source"], "keywords")
        self.assertNotIn("reading", spec["listeningNotes"][0])
        self.assertTrue(any("quote not found" in d for d in result["ai"]["dropped"]))
        self.assertTrue(any("does not exist (7)" in d for d in result["ai"]["dropped"]))

    def test_whys_are_written_for_this_song_and_numbers_are_checked(self):
        fake = FakeModel(whys={
            "steps": [
                {"requirementId": "roles_need_content", "why": "You said Drop 1 felt too empty. The hook lead is there but nothing sits under it, so this puts a bed behind it."},
                {"requirementId": "texture_bed", "why": "The drop needs a pad at -18 dB under the lead."},
                {"requirementId": "gain_ladder", "why": "not a step in this session"},
            ],
            "listenerSummary": "You liked the intro. Drop 1 felt empty, so the next render fills it in under the lead.",
            "iterationNote": "Listener wants Drop 1 fuller under the hook lead",
        })
        result, spec = self.apply([
            {"questionId": "drop-1.fullness", "option": "too empty"},
            {"questionId": "intro.fullness", "option": "just right"},
        ], fake)
        by_id = {s["id"]: s for s in result["steps"]}
        first = by_id["roles_need_content"]
        self.assertEqual(first["whySource"], "model")
        self.assertTrue(first["why"].startswith("You said Drop 1 felt too empty"))
        self.assertEqual(first["rubricWhy"], ls.requirement_by_id("roles_need_content").why)
        second = by_id["texture_bed"]
        self.assertEqual(second["whySource"], "rubric", "a number the model was not given is rejected")
        self.assertEqual(second["why"], ls.requirement_by_id("texture_bed").why)
        self.assertNotIn("rubricWhy", second)
        self.assertEqual(result["listenerSummary"], "You liked the intro. Drop 1 felt empty, so the next render fills it in under the lead.")
        self.assertEqual(result["iterationNote"], "Listening session: 2 answers, 2 steps added — Listener wants Drop 1 fuller under the hook lead")
        self.assertEqual(result["summary"], "2 steps added from 2 answers", "the summary line the app shows is untouched")
        spec_gap = {g["id"]: g for g in spec["fillInBlanks"]["gaps"]}["roles_need_content"]
        self.assertEqual(spec_gap["whySource"], "model")
        self.assertTrue(spec_gap["why"].startswith("You said Drop 1"))
        dropped = result["ai"]["dropped"]
        self.assertTrue(any("texture_bed rejected" in d for d in dropped))
        self.assertTrue(any("unknown step gain_ladder" in d for d in dropped))
        # One call for the whys; no notes, so no notes call.
        self.assertEqual([c[0] for c in fake.calls], ["whys"])
        self.assertIn("Intro: 'How full does this part feel?' -> just right", fake.calls[0][1])

    def test_model_failure_on_apply_is_the_offline_result_plus_an_ai_block(self):
        answers = [{"questionId": "drop-1.fullness", "option": "too empty"}, {"questionId": "drop-1.notes", "text": "the bass feels muddy"}]
        offline_spec = spec_from()
        offline = ls.apply_answers(five_section_project(), offline_spec, {"answers": answers}, ls.Assist(enabled=False))
        fake = FakeModel(notes="garbage", whys="garbage")
        result, spec = self.apply(answers, fake)
        for key in ("steps", "added", "notes", "summary", "iterationNote", "warnings"):
            self.assertEqual(result[key], offline[key], key)
        self.assertEqual(spec["fillInBlanks"]["gaps"], offline_spec["fillInBlanks"]["gaps"])
        self.assertFalse(result["ai"]["used"])
        self.assertEqual(offline["ai"]["note"], "AI off for this run")
        self.assertNotIn("listenerSummary", result)

    def test_an_answer_to_a_bank_question_the_table_does_not_ask_still_maps(self):
        # The model may have asked intro.hum at question time; apply maps it through the bank.
        spec = spec_from()
        result = ls.apply_answers(five_section_project(), spec, {"answers": [{"questionId": "intro.hum", "option": "not really"}]}, ls.Assist(enabled=False))
        self.assertEqual([s["id"] for s in result["steps"]], ["hook_carrier_declaration", "hook_contour", "hook_recurrence"])
        self.assertEqual(result["warnings"], [])
        self.assertEqual(result["steps"][0]["whySource"], "rubric")


class ModelCliTests(unittest.TestCase):
    def test_ai_off_flag_is_accepted_on_either_side_and_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            project_path = Path(tmp) / "p.neon.json"
            project_path.write_text(json.dumps(five_section_project()), encoding="utf-8")
            env = dict(os.environ)
            env.pop("NEON_AI", None)
            env["NEON_CONFIG_DIR"] = "/nonexistent"
            env.pop("GEMINI_API_KEY", None)
            env.pop("GOOGLE_API_KEY", None)
            env.pop("ANTHROPIC_API_KEY", None)
            for args in (["--ai", "off", "questions"], ["questions", "--ai", "off"], ["--format", "markdown", "questions"]):
                command = [sys.executable, str(Path(ls.__file__)), "--root", tmp, "--project", str(project_path), *args]
                completed = subprocess.run(command, capture_output=True, text=True, check=False, env=env)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                if "markdown" in args:
                    self.assertIn("AI: offline rules", completed.stdout)
                else:
                    payload = json.loads(completed.stdout.strip().splitlines()[-1])
                    self.assertFalse(payload["ai"]["used"])
                    self.assertEqual(payload["ai"]["note"], "AI off for this run")


if __name__ == "__main__":
    unittest.main()
