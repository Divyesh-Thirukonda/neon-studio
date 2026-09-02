#!/usr/bin/env python3
"""Tests for the production rubric and the fill-in-the-blanks enrichment.

Run with:  /usr/bin/python3 -m unittest tools/test_fill_in_blanks.py
"""

from __future__ import annotations

import sys
import unittest
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import production_rubric as rubric  # noqa: E402
from fill_in_blanks import (  # noqa: E402
    fill_in_blanks,
    gaps_from_sound_check,
    merge_gaps,
    render_markdown,
)


def spec_from(**overrides):
    """A minimal transcript spec of the shape ingest_transcript.py produces."""
    base = {
        "schemaVersion": 1,
        "projectId": "test-song",
        "titleHint": "Test Song",
        "sections": [],
        "globalTracks": [],
        "globalTechniques": [],
        "arrangementNotes": [],
        "mixNotes": [],
        "automationNotes": [],
        "coverageChecklist": [],
        "openQuestions": [],
    }
    base.update(overrides)
    return base


def section(section_type, *, roles=(), techniques=(), summary="", lane_events=None):
    return {
        "id": f"s-{section_type}",
        "type": section_type,
        "label": section_type.replace("_", " ").title(),
        "summary": summary,
        "excerpt": "",
        "transcriptText": "",
        "trackRoles": list(roles),
        "techniques": list(techniques),
        "plugins": [],
        "laneEvents": lane_events or {},
    }


class RubricIntegrityTests(unittest.TestCase):
    """The catalogue has to stay well-formed however it grows."""

    def test_there_are_requirements(self):
        self.assertGreater(len(rubric.REQUIREMENTS), 10, "the rubric should be substantive")

    def test_ids_are_unique(self):
        ids = [r.id for r in rubric.REQUIREMENTS]
        duplicates = {i for i in ids if ids.count(i) > 1}
        self.assertEqual(duplicates, set(), f"duplicate requirement ids: {duplicates}")

    def test_ids_are_slugs(self):
        for requirement in rubric.REQUIREMENTS:
            self.assertRegex(requirement.id, r"^[a-z][a-z0-9_]*$", requirement.id)

    def test_areas_are_from_the_sound_check_vocabulary(self):
        # A requirement that names an area the checker never emits can never be
        # re-raised from a real report, which silently breaks the feedback loop.
        allowed = set(rubric.SOUND_CHECK_AREAS) | {"none"}
        for requirement in rubric.REQUIREMENTS:
            self.assertIn(requirement.area, allowed, f"{requirement.id} has area {requirement.area!r}")

    def test_style_lanes_are_real(self):
        allowed = set(rubric.STYLE_LANES) | {"all"}
        for requirement in rubric.REQUIREMENTS:
            self.assertTrue(requirement.applies_to, f"{requirement.id} applies to nothing")
            for lane in requirement.applies_to:
                self.assertIn(lane, allowed, f"{requirement.id} names lane {lane!r}")

    def test_every_requirement_says_something_useful(self):
        for requirement in rubric.REQUIREMENTS:
            self.assertTrue(requirement.label.strip(), requirement.id)
            self.assertGreater(len(requirement.why), 20, f"{requirement.id} why is too thin")
            self.assertGreater(len(requirement.step), 30, f"{requirement.id} step is not actionable")

    def test_most_requirements_pre_empt_a_real_finding(self):
        # Some requirements are purely musical, but the majority should map onto
        # something the checker measures, or the two tools have drifted apart.
        mapped = [r for r in rubric.REQUIREMENTS if r.area != "none"]
        self.assertGreater(
            len(mapped),
            len(rubric.REQUIREMENTS) // 2,
            "most requirements should pre-empt a sound-check finding",
        )

    def test_every_finding_the_checker_can_emit_maps_to_a_step(self):
        # This is what makes the backward loop complete: if the checker can
        # report it, the filler must be able to turn it into something to do.
        for area in rubric.SOUND_CHECK_AREAS:
            self.assertTrue(
                rubric.requirements_for_area(area),
                f"nothing in the rubric pre-empts a {area!r} finding",
            )

    def test_secondary_areas_are_real(self):
        allowed = set(rubric.SOUND_CHECK_AREAS)
        for requirement in rubric.REQUIREMENTS:
            for area in requirement.also_prevents:
                self.assertIn(area, allowed, f"{requirement.id} also_prevents {area!r}")
            self.assertNotIn(
                requirement.area,
                requirement.also_prevents,
                f"{requirement.id} lists its primary area twice",
            )

    def test_lookup_helpers(self):
        first = rubric.REQUIREMENTS[0]
        self.assertIs(rubric.requirement_by_id(first.id), first)
        self.assertIsNone(rubric.requirement_by_id("no_such_requirement"))
        for area in rubric.SOUND_CHECK_AREAS:
            for requirement in rubric.requirements_for_area(area):
                self.assertIn(area, requirement.areas)


class SpecViewTests(unittest.TestCase):
    """Specs come from parsed prose, so every accessor has to tolerate junk."""

    def test_empty_spec_is_safe(self):
        view = rubric.SpecView({})
        self.assertEqual(view.sections, [])
        self.assertEqual(view.roles, set())
        self.assertEqual(view.techniques, set())
        self.assertEqual(view.notes, "")
        self.assertFalse(view.mentions("anything"))

    def test_malformed_spec_is_safe(self):
        view = rubric.SpecView({
            "sections": "not a list",
            "globalTracks": [None, 5, {"name": "Bass"}],
            "globalTechniques": ["Sidechain", {"name": "EQ"}, 7],
        })
        self.assertEqual(view.sections, [])
        self.assertIn("bass", view.roles)
        self.assertIn("sidechain", view.techniques)

    def test_mentions_searches_prose_as_well_as_fields(self):
        view = rubric.SpecView(spec_from(
            mixNotes=["Duck the pads under the kick"],
            sections=[section("drop")],
        ))
        self.assertTrue(view.mentions("duck"))
        self.assertTrue(view.has_technique("duck"))
        self.assertFalse(view.mentions("vocoder"))

    def test_sections_of_and_payoffs(self):
        view = rubric.SpecView(spec_from(sections=[
            section("intro"), section("drop"), section("second_drop"),
        ]))
        self.assertEqual(len(view.sections_of("drop")), 1)
        self.assertEqual(len(view.payoff_sections), 2)
        self.assertTrue(view.has_section("intro"))
        self.assertFalse(view.has_section("break"))


class FindGapsTests(unittest.TestCase):
    def test_a_bare_spec_produces_gaps(self):
        gaps = rubric.find_gaps(spec_from(sections=[section("drop")]), "bright_future_bass")
        self.assertGreater(len(gaps), 5, "a one-line brief should surface plenty of missing steps")
        for gap in gaps:
            self.assertTrue(gap.step)
            self.assertIn(gap.area, set(rubric.SOUND_CHECK_AREAS) | {"none"})

    def test_gaps_are_skippable(self):
        spec = spec_from(sections=[section("drop")])
        every = rubric.find_gaps(spec, "bright_future_bass")
        skip_one = rubric.find_gaps(spec, "bright_future_bass", skip=[every[0].id])
        self.assertEqual(len(skip_one), len(every) - 1)

    def test_a_broken_predicate_never_takes_the_pipeline_down(self):
        def explode(_view):
            raise RuntimeError("boom")

        bad = rubric.Requirement(
            id="explodes", label="Explodes", why="x" * 30, step="y" * 40,
            area="none", covered=explode,
        )
        rubric.REQUIREMENTS.append(bad)
        try:
            gaps = rubric.find_gaps(spec_from(), "modern_edm")
            self.assertNotIn("explodes", [g.id for g in gaps])
        finally:
            rubric.REQUIREMENTS.remove(bad)

    def test_style_lane_filtering(self):
        only_house = rubric.Requirement(
            id="house_only", label="House only", why="x" * 30, step="y" * 40,
            area="none", covered=lambda _v: False, applies_to=("house_pop",),
        )
        rubric.REQUIREMENTS.append(only_house)
        try:
            self.assertIn("house_only", [g.id for g in rubric.find_gaps(spec_from(), "house_pop")])
            self.assertNotIn("house_only", [g.id for g in rubric.find_gaps(spec_from(), "dark_bass")])
        finally:
            rubric.REQUIREMENTS.remove(only_house)

    def test_saying_it_in_prose_counts_as_covering_it(self):
        # The whole point: never override what somebody actually asked for.
        bare = spec_from(sections=[section("drop")])
        detailed = spec_from(
            sections=[section("drop", techniques=["sidechain"], summary="Kick ducks the bass and chords")],
            mixNotes=[
                "Sub owns everything under 80 Hz, kick ducks it",
                "High-pass every melodic layer at 200 Hz",
                "Keep the bass mono below 120 Hz, widen only the pads",
            ],
            arrangementNotes=[
                "Riser and impact into every drop, reverse cymbal on the last beat",
                "Second drop adds an octave lead and a ride, plus a drum fill every 8 bars",
            ],
        )
        self.assertLess(
            len(rubric.find_gaps(detailed, "bright_future_bass")),
            len(rubric.find_gaps(bare, "bright_future_bass")),
            "a detailed brief should surface fewer missing steps than a bare one",
        )


class StructuralRepairTests(unittest.TestCase):
    """A walkthrough is not narrated in playback order, and ingest cannot fix that."""

    def test_sections_are_reordered_into_playback_order(self):
        # Regression: a real transcript parsed with second_drop at index 1,
        # ahead of the intro, so the biggest section was laid out at bar 1.
        spec = spec_from(sections=[
            section("second_drop", roles=["lead", "bass"]),
            section("intro", roles=["chords"]),
            section("drop", roles=["lead", "bass", "kick"]),
        ])
        enriched = fill_in_blanks(spec, prompt="future bass")
        order = [s["type"] for s in enriched["sections"] if s.get("bars")]
        self.assertLess(order.index("intro"), order.index("drop"))
        self.assertLess(order.index("drop"), order.index("second_drop"))

    def test_unclassified_sections_carrying_parts_are_rescued(self):
        # Regression: production_notes sections were filtered out at build time,
        # taking every lane event they carried with them.
        notes = section("production_notes", roles=["kick", "bass", "lead", "chords"])
        notes["laneEvents"] = {"bass": {"kind": "beatPattern", "events": [{"beat": 0.0}]}}
        spec = spec_from(sections=[section("intro", roles=["chords"]), notes])
        enriched = fill_in_blanks(spec, prompt="future bass")
        kept = [s for s in enriched["sections"] if s.get("rescued")]
        self.assertTrue(kept, "a section with real parts must not be silently dropped")
        self.assertIn(kept[0]["type"], ("drop", "second_drop"))

    def test_every_mention_of_a_section_folds_into_one(self):
        # Regression: a 53-minute walkthrough returns to the drop a dozen times
        # and ingest made a section each time — 360 bars of verse/drop/verse/drop.
        spec = spec_from(sections=[
            section("verse", roles=["bass"]), section("drop", roles=["lead"]),
            section("verse", roles=["chords"]), section("drop", roles=["kick"]),
            section("verse", roles=["hat"]), section("drop", roles=["sub"]),
        ])
        enriched = fill_in_blanks(spec, prompt="future bass")
        types = [s["type"] for s in enriched["sections"] if s.get("bars")]
        self.assertEqual(types.count("drop"), 1)
        self.assertEqual(types.count("verse"), 1)
        # Folding keeps the parts, it does not throw the later mentions away.
        drop = next(s for s in enriched["sections"] if s["type"] == "drop")
        self.assertTrue({"lead", "kick", "sub"} <= set(drop["trackRoles"]))

    def test_a_song_has_one_intro(self):
        spec = spec_from(sections=[
            section("intro", roles=["chords"]),
            section("drop", roles=["lead", "kick"]),
            section("intro", roles=["chords", "lead"]),
        ])
        enriched = fill_in_blanks(spec, prompt="future bass")
        types = [s["type"] for s in enriched["sections"] if s.get("bars")]
        self.assertEqual(types.count("intro"), 1)

    def test_every_section_gets_a_length(self):
        spec = spec_from(sections=[section("intro"), section("drop")])
        enriched = fill_in_blanks(spec, prompt="future bass")
        musical = [s for s in enriched["sections"] if s["type"] in rubric.SpecView.ENERGY_RANK]
        for item in musical:
            self.assertTrue(item.get("bars"), f"{item['type']} has no length")
            self.assertEqual(int(item["bars"]) % 4, 0, "sections are written in fours")

    def test_lengths_come_from_timecodes_when_present(self):
        # 32 seconds at 120 BPM is 16 bars.
        early = section("intro")
        early["startSeconds"], early["endSeconds"] = 0.0, 32.0
        spec = spec_from(tempoHint=120, sections=[early, section("drop")])
        enriched = fill_in_blanks(spec)
        intro = next(s for s in enriched["sections"] if s["type"] == "intro")
        self.assertEqual(intro["bars"], 16)

    def test_producer_terms_map_to_buildable_roles(self):
        # Regression: "808" and "stab" parsed fine and then produced no track.
        spec = spec_from(sections=[section("drop", roles=["808", "stab", "shaker", "arp"])])
        enriched = fill_in_blanks(spec, prompt="future bass")
        drop = next(s for s in enriched["sections"] if s["type"] == "drop")
        roles = set(drop["trackRoles"])
        self.assertIn("sub", roles)
        self.assertIn("chords", roles)
        self.assertIn("hat", roles)
        self.assertIn("pluck", roles)
        self.assertNotIn("808", roles)


class SoundCheckFeedbackTests(unittest.TestCase):
    def test_tagged_issues_become_measured_gaps(self):
        requirement = next(r for r in rubric.REQUIREMENTS if r.area != "none")
        report = {
            "issues": [{
                "severity": "high",
                "area": requirement.area,
                "detail": "The low-frequency balance is probably crowding the mix.",
                "requirementIds": [requirement.id],
            }],
            "nextActions": [],
        }
        gaps = gaps_from_sound_check(report)
        self.assertEqual([g.id for g in gaps], [requirement.id])
        self.assertEqual(gaps[0].confidence, "measured")
        self.assertEqual(gaps[0].source, "sound-check")
        self.assertIn("crowding", gaps[0].evidence)

    def test_untagged_issues_fall_back_to_the_area(self):
        # Reports written before the tagging existed must still work.
        requirement = next(r for r in rubric.REQUIREMENTS if r.area != "none")
        gaps = gaps_from_sound_check({
            "issues": [{"severity": "medium", "area": requirement.area, "detail": "something"}],
        })
        self.assertIn(requirement.id, [g.id for g in gaps])

    def test_next_actions_are_carried_but_boilerplate_is_dropped(self):
        gaps = gaps_from_sound_check({
            "issues": [],
            "nextActions": [
                "Dip 200-500 Hz on pads, reverbs, or stacked melodic layers.",
                "Run one human listen pass for hook memorability, transition impact, and emotional payoff.",
            ],
        })
        steps = [g.step for g in gaps]
        self.assertIn("Dip 200-500 Hz on pads, reverbs, or stacked melodic layers.", steps)
        self.assertFalse(any("human listen" in s for s in steps))

    def test_garbage_reports_are_ignored(self):
        self.assertEqual(gaps_from_sound_check({}), [])
        self.assertEqual(gaps_from_sound_check(None), [])
        self.assertEqual(gaps_from_sound_check({"issues": "nope"}), [])


class MergeGapsTests(unittest.TestCase):
    def make_gap(self, gap_id, confidence="medium"):
        return rubric.Gap(
            id=gap_id, label=gap_id, why="because", step="do the thing",
            area="none", confidence=confidence,
        )

    def test_new_gaps_are_appended(self):
        merged = merge_gaps([], [self.make_gap("a"), self.make_gap("b")])
        self.assertEqual([g["id"] for g in merged], ["a", "b"])

    def test_measured_replaces_inferred(self):
        existing = merge_gaps([], [self.make_gap("a")])
        self.assertEqual(existing[0]["confidence"], "medium")
        merged = merge_gaps(existing, [self.make_gap("a", confidence="measured")])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["confidence"], "measured")

    def test_inferred_does_not_downgrade_measured(self):
        measured = merge_gaps([], [self.make_gap("a", confidence="measured")])
        merged = merge_gaps(measured, [self.make_gap("a")])
        self.assertEqual(merged[0]["confidence"], "measured")

    def test_merge_is_stable(self):
        once = merge_gaps([], [self.make_gap("a"), self.make_gap("b")])
        twice = merge_gaps(once, [self.make_gap("a"), self.make_gap("b")])
        self.assertEqual(once, twice)


class FillInBlanksIntegrationTests(unittest.TestCase):
    def test_a_vague_brief_gets_both_values_and_steps(self):
        spec = spec_from(
            sourcePrompt="A big future bass track with a catchy supersaw drop",
            sections=[section("drop", roles=["lead"], summary="the drop hits hard")],
        )
        enriched = fill_in_blanks(spec, prompt="big future bass drop")
        fill = enriched["fillInBlanks"]

        self.assertTrue(enriched.get("tempoHint"), "a value blank should be filled")
        self.assertTrue(fill.get("gaps"), "a step blank should be found")
        self.assertEqual(fill["schemaVersion"], 2)

        gap_ids = {g["id"] for g in fill["gaps"]}
        decision_ids = {d.get("requirementId") for d in fill["decisions"] if d.get("requirementId")}
        self.assertTrue(gap_ids & decision_ids, "gaps should also appear as decisions")

    def test_the_input_spec_is_not_mutated(self):
        spec = spec_from(sections=[section("drop")])
        before = deepcopy(spec)
        fill_in_blanks(spec)
        self.assertEqual(spec, before)

    def test_running_twice_is_stable(self):
        spec = spec_from(sections=[section("drop")])
        once = fill_in_blanks(spec, prompt="future bass")
        twice = fill_in_blanks(deepcopy(once), prompt="future bass")
        self.assertEqual(
            [g["id"] for g in once["fillInBlanks"]["gaps"]],
            [g["id"] for g in twice["fillInBlanks"]["gaps"]],
            "re-running must not churn the gap list",
        )

    def test_sound_check_feedback_upgrades_a_gap(self):
        requirement = next(r for r in rubric.REQUIREMENTS if r.area != "none")
        spec = spec_from(sections=[section("drop")])
        first = fill_in_blanks(spec, prompt="future bass")
        second = fill_in_blanks(
            deepcopy(first),
            prompt="future bass",
            sound_check={
                "issues": [{
                    "severity": "high",
                    "area": requirement.area,
                    "detail": "measured detail",
                    "requirementIds": [requirement.id],
                }],
            },
        )
        by_id = {g["id"]: g for g in second["fillInBlanks"]["gaps"]}
        self.assertIn(requirement.id, by_id)
        self.assertEqual(by_id[requirement.id]["confidence"], "measured")
        self.assertIn("measured detail", by_id[requirement.id]["evidence"])

    def test_markdown_report_shows_both_kinds(self):
        spec = spec_from(sections=[section("drop")])
        enriched = fill_in_blanks(spec, prompt="future bass")
        text = render_markdown(enriched)
        self.assertIn("## Inferred Decisions", text)
        self.assertIn("## Missing Steps", text)

    def test_markdown_separates_measured_findings(self):
        requirement = next(r for r in rubric.REQUIREMENTS if r.area != "none")
        enriched = fill_in_blanks(
            spec_from(sections=[section("drop")]),
            sound_check={"issues": [{
                "severity": "high", "area": requirement.area,
                "detail": "measured detail", "requirementIds": [requirement.id],
            }]},
        )
        text = render_markdown(enriched)
        self.assertIn("Measured", text)
        self.assertIn("measured detail", text)

    def test_an_empty_spec_does_not_crash(self):
        enriched = fill_in_blanks({})
        self.assertIn("fillInBlanks", enriched)


if __name__ == "__main__":
    unittest.main()


class ProductionNotesMergeTests(unittest.TestCase):
    def test_production_notes_fold_into_one_section(self) -> None:
        spec = spec_from(sections=[section("intro", roles=["chords"]), section("drop", roles=["drums", "bass"])])
        for index, (technique, text) in enumerate((("eq", "cut the pad"), ("compression", "glue the drums"), ("eq", "cut the pad"))):
            spec["sections"].append({"id": f"notes-{index}", "type": "production_notes", "label": "Production Notes",
                                     "techniques": [technique], "plugins": [f"plugin-{index}"], "trackRoles": [],
                                     "transcriptText": text, "summary": text, "excerpt": text, "bars": None})
        from fill_in_blanks import resolve_duplicate_sections
        decisions: list = []
        resolve_duplicate_sections(spec, decisions)
        notes = [s for s in spec["sections"] if s.get("type") == "production_notes"]
        self.assertEqual(len(notes), 1)
        self.assertEqual(sorted(notes[0]["techniques"]), ["compression", "eq"])
        self.assertEqual(notes[0]["plugins"], ["plugin-0", "plugin-1", "plugin-2"])
        self.assertEqual(notes[0]["transcriptText"], "cut the pad glue the drums")
        self.assertEqual([s["type"] for s in spec["sections"]][:2], ["intro", "drop"])
        self.assertTrue(any("production note" in str(d.get("summary", d)) for d in decisions), decisions)
