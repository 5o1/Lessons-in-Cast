"""Annotation API contracts, story memory, scoped direction, and recovery."""

from dataclasses import replace
from html import escape
from http.client import RemoteDisconnected
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from lessons_in_cast_core.annotation import build_annotation_request
from lessons_in_cast_core.annotation.agent import AnnotationAgent, chat_completion
from lessons_in_cast_core.annotation.context import build_messages, transition_memory
from lessons_in_cast_core.annotation.protocol import wire_schema, check_shape
from lessons_in_cast_core.config import load_pipeline_config, ConfigurationError
from lessons_in_cast_core.dialogue import DialogueBatch
from lessons_in_cast_core.galgame.renpy.context import RenPySourceContextIndex
from lessons_in_cast_core.jsonl import read_jsonl, write_jsonl
from lessons_in_cast_core.kantoku import Kantoku, bind_direction, split_directed_request
from lessons_in_cast_core.polish import PolishStage
from lessons_in_cast_core.workflow.artifacts import ArtifactLayout
from lessons_in_cast_core.workflow.validation import AnnotationValidationStage
from .helpers import record
from .test_synthesis import character

ROOT = Path(__file__).resolve().parents[1]


def valid_reply(messages, schema):
    text = messages[2]['content']
    turn_id = re.search(r'^Turn: (.+)$', text, re.M)[1]
    rows = re.findall(r'^(T\d+) \[evidence=("[^"]+"),.*\| (".*")$', text, re.M)
    properties = schema['properties']['annotations']['items']['properties']
    annotations = []
    for alias, evidence, dialogue in rows:
        spoken = json.loads(dialogue)
        row = {'id': alias, 'action': 'speak', 'spoken_text': spoken,
               'effects': [], 'confidence': 1.0, 'review_required': False, 'reason': None,
               'performance': {key: ([] if key == 'cues' else None)
                               for key in properties['performance']['properties']}}
        if 'delivery' in properties:
            row.update(delivery=[], keyframe_effects=None,
                       spoken_text=f'<emotion name="neutral">{escape(spoken)}</emotion>')
        annotations.append(row)
    output = {'turn_id': turn_id, 'annotations': annotations, 'memory': []}
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(output)}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 100}}


def modify_response(response, callback):
    document = json.loads(response['choices'][0]['message']['content'])
    callback(document)
    response['choices'][0]['message']['content'] = json.dumps(document)
    return response


class AnnotationAgentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'prompts').mkdir()
        (self.root / 'configs').mkdir()
        for path in ROOT.joinpath('prompts').glob('*.md'):
            shutil.copy2(path, self.root / 'prompts' / path.name)
        for name in ('characters.toml', 'pipeline.toml', 'emotions.toml'):
            shutil.copy2(ROOT / 'configs' / name, self.root / 'configs' / name)
        self.config = replace(load_pipeline_config(repository_root=ROOT), repository_root=self.root)
        self.characters = {'a': character('a')}
        self.layout = ArtifactLayout(self.root / 'run')
        self.layout.root.mkdir()
        self.records = [replace(record(i, dialogue=f'Line {i}.'), label='opening', scene='room') for i in range(4)]
        self.calls = []

    def prepare(self, sizes=(1, 1, 1, 1)):
        requests, start = [], 0
        for index, size in enumerate(sizes):
            targets = tuple(self.records[start:start + size])
            batch = DialogueBatch(f'batch-{index}', tuple(self.records[:start]), targets, tuple(self.records[start + size:]))
            request = build_annotation_request(batch, annotation_config=self.config.annotation, stage='cleaning')
            requests.append(bind_direction(request, Kantoku(self.root, self.config, self.characters)))
            start += size
        write_jsonl([r.to_dict() for r in self.records], self.layout.raw_dialogue)
        write_jsonl(requests, self.layout.annotation_requests)
        return requests

    def agent(self, stage='cleaning', complete=None):
        def completion(settings, messages, schema):
            self.calls.append(messages)
            return complete(messages, schema) if complete else valid_reply(messages, schema)
        return AnnotationAgent(self.root, self.config, self.characters, stage,
                               completion=completion, voice_lookup=lambda *args: {'a': []})

    def test_missing_completion_is_reported_for_repair(self):
        self.prepare((4,))
        def complete(messages, schema):
            return {'choices': []} if len(self.calls) == 1 else valid_reply(messages, schema)
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 2)
        self.assertIn('Validation errors', self.calls[1][-1]['content'])

    def test_whole_json_fence_is_accepted_without_repair(self):
        self.prepare((4,))
        def complete(messages, schema):
            reply = valid_reply(messages, schema)
            message = reply['choices'][0]['message']
            message['content'] = '```json\n' + message['content'] + '\n```'
            return reply
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(AnnotationValidationStage(self.config).run(self.layout).accepted_count, 4)

    def test_polish_omitted_silence_needs_no_emotion_markup(self):
        self.records = [replace(self.records[0], dialogue='...')]
        self.prepare((1,))
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0].update(action='omit', spoken_text='', reason='Silent beat.', review_required=True))
        self.agent(complete=complete).run(self.layout)
        overrides = self.root / 'silence.toml'
        overrides.write_text('[dialogue."id-0"]\napproved = true\nreview_required = false\nreason = "Confirmed silent beat."\n')
        self.assertEqual(AnnotationValidationStage(self.config).run(self.layout, overrides_path=overrides).accepted_count, 1)
        stage = PolishStage(self.config)
        stage.prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        (self.layout.root / 'polish_overrides.toml').write_text(
            '[dialogue."id-0"]\napproved = true\nreview_required = false\nreason = "Confirmed."\n')
        self.calls.clear()
        self.agent('polish', complete=complete).run(self.layout.polish)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(stage.validate(self.layout).accepted_count, 1)

    def test_unknown_polish_preset_becomes_arbitrary_emotion(self):
        self.prepare((4,))
        self.agent().run(self.layout)
        AnnotationValidationStage(self.config).run(self.layout)
        stage = PolishStage(self.config)
        stage.prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0].update(spoken_text='<emotion name="defensive">Line 0.</emotion>'))
        self.calls.clear()
        self.agent('polish', complete=complete).run(self.layout.polish)
        self.assertEqual(len(self.calls), 1)
        row = next(read_jsonl(self.layout.polish.annotation_responses))['response']['annotations'][0]
        self.assertEqual(row['spoken_text'],
                         '<arbitrary_emotion description="defensive">Line 0.</arbitrary_emotion>')

    def test_existing_arbitrary_polish_emotion_is_preserved(self):
        self.prepare((4,))
        self.agent().run(self.layout)
        AnnotationValidationStage(self.config).run(self.layout)
        stage = PolishStage(self.config)
        stage.prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0].update(spoken_text=
                    '<arbitrary_emotion description="dry disbelief">Line 0.</arbitrary_emotion>'))
        self.calls.clear()
        self.agent('polish', complete=complete).run(self.layout.polish)
        self.assertEqual(len(self.calls), 1)

    def test_plain_polish_speech_gets_neutral_markup_without_repair(self):
        self.prepare((4,))
        self.agent().run(self.layout)
        AnnotationValidationStage(self.config).run(self.layout)
        PolishStage(self.config).prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0].update(spoken_text='Line 0.'))
        self.calls.clear()
        self.agent('polish', complete=complete).run(self.layout.polish)
        self.assertEqual(len(self.calls), 1)
        row = next(read_jsonl(self.layout.polish.annotation_responses))['response']['annotations'][0]
        self.assertEqual(row['spoken_text'], '<emotion name="neutral">Line 0.</emotion>')

    def test_required_fade_moves_model_keyframes_to_text_endpoints(self):
        self.prepare((4,))
        self.agent().run(self.layout)
        AnnotationValidationStage(self.config).run(self.layout)
        PolishStage(self.config).prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        request = next(read_jsonl(self.layout.polish.annotation_requests))
        request['keyframe_required'] = [self.records[0].id]
        write_jsonl([request], self.layout.polish.annotation_requests)
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0].update(
                    spoken_text='<emotion name="neutral">{1}Line 0{2}.</emotion>',
                    keyframe_effects=[{'type': 'gain_envelope', 'interpolation': 'smooth',
                                       'keyframes': [{'anchor': '1', 'gain': 0}, {'anchor': '2', 'gain': 1}]}]))
        self.calls.clear()
        self.agent('polish', complete=complete).run(self.layout.polish)
        self.assertEqual(len(self.calls), 1)
        row = next(read_jsonl(self.layout.polish.annotation_responses))['response']['annotations'][0]
        self.assertEqual(row['spoken_text'], '<emotion name="neutral">{1}Line 0.{2}</emotion>')

    def test_non_speaking_polish_drops_stray_text_without_repair(self):
        self.records = [replace(self.records[0], dialogue='...')]
        self.prepare((1,))
        self.agent().run(self.layout)
        overrides = self.root / 'omit.toml'
        overrides.write_text('[dialogue."id-0"]\naction = "sfx_only"\nspoken_text = ""\neffects = ["echo"]\napproved = true\nreview_required = false\nreason = "Audible non-speech beat."\n')
        AnnotationValidationStage(self.config).run(self.layout, overrides_path=overrides)
        PolishStage(self.config).prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0].update(action='sfx_only', effects=['echo'],
                                           spoken_text='<emotion name="neutral">...</emotion>'))
        self.calls.clear()
        self.agent('polish', complete=complete).run(self.layout.polish)
        self.assertEqual(len(self.calls), 1)
        row = next(read_jsonl(self.layout.polish.annotation_responses))['response']['annotations'][0]
        self.assertEqual(row['spoken_text'], '')

    def test_cleaning_polish_round_trip_and_stable_resume(self):
        self.prepare()
        self.agent().run(self.layout)
        original = self.layout.annotation_responses.read_bytes()
        self.assertEqual(AnnotationValidationStage(self.config).run(self.layout).accepted_count, 4)
        stage = PolishStage(self.config)
        stage.prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        self.agent('polish').run(self.layout.polish)
        self.assertEqual(stage.validate(self.layout).accepted_count, 4)
        calls = len(self.calls)
        self.agent().run(self.layout)
        self.assertEqual(calls, len(self.calls))
        self.assertEqual(original, self.layout.annotation_responses.read_bytes())
        stage.check_inputs(self.layout)

    def test_repairs_only_current_turn_before_committing(self):
        self.prepare((4,))
        def complete(messages, schema):
            response = valid_reply(messages, schema)
            if len(self.calls) == 1:
                return modify_response(response, lambda d: d['annotations'].pop())
            return response
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 2)
        self.assertIn('Validation errors', self.calls[1][-1]['content'])
        self.assertEqual(self.calls[1][-2]['role'], 'assistant')
        self.assertIn('annotations', self.calls[1][-2]['content'])
        commit = next(read_jsonl(self.layout.root / 'api/initial/turn-000000.jsonl'))
        self.assertEqual(len(commit['attempts']), 2)
        self.assertEqual(commit['memory_after'], [])

    def test_cleaning_strips_style_tags_and_repairs_extreme_length(self):
        self.prepare((4,))
        def complete(messages, schema):
            response = valid_reply(messages, schema)
            def change(document):
                document['annotations'][0]['spoken_text'] = ('{i}x{/i}' if len(self.calls) == 1
                                                              else '{i}Line 0.{/i}')
            return modify_response(response, change)
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 2)
        commit = next(read_jsonl(self.layout.root / 'api/initial/turn-000000.jsonl'))
        self.assertEqual(commit['annotations'][0]['spoken_text'], 'Line 0.')
        self.assertIn('length_ratio', self.calls[1][-1]['content'])

    def test_cleaning_drops_unusable_pause_cues_locally(self):
        self.prepare((4,))
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0]['performance'].update(cues=[
                    {'kind': 'pause', 'offset': 99, 'duration_seconds': 0.2, 'intensity': None},
                    {'kind': 'pause', 'offset': 2, 'duration_seconds': None, 'intensity': None},
                    {'kind': 'pause', 'offset': 3, 'duration_seconds': 0.2, 'intensity': None},
                ]))
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 1)
        row = next(read_jsonl(self.layout.annotation_responses))['response']['annotations'][0]
        self.assertEqual(row['performance']['cues'], [])

    def test_cleaning_reserves_fragment_fade_for_polish(self):
        self.records[0] = replace(self.records[0], dialogue='...sei?')
        self.prepare((4,))
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema), lambda d:
                d['annotations'][0].update(
                    action='speak_with_effect', spoken_text='Sensei?', effects=['echo'],
                    performance={'cues': [
                        {'kind': 'pause', 'offset': 3, 'duration_seconds': 0.2, 'intensity': None},
                    ]},
                ))
        self.agent(complete=complete).run(self.layout)
        row = next(read_jsonl(self.layout.annotation_responses))['response']['annotations'][0]
        self.assertEqual((row['action'], row['effects'], row['performance']['cues']),
                         ('speak', [], []))

    def test_memory_continuity_resets_at_label_and_lookahead_is_not_evidence(self):
        self.records[2:] = [replace(r, label='next') for r in self.records[2:]]
        self.prepare()
        def complete(messages, schema):
            response = valid_reply(messages, schema)
            source = re.search(r'T001 \[evidence=("[^"]+")', messages[2]['content'])[1]
            return modify_response(response, lambda d: d.update(memory=[{
                'character_id': 'a', 'kind': 'fact', 'text': 'A previous exchange is unresolved.',
                'evidence_ids': [json.loads(source)]}]))
        self.agent(complete=complete).run(self.layout)
        self.assertIn('A previous exchange is unresolved.', self.calls[1][2]['content'])
        self.assertNotIn('A previous exchange is unresolved.', self.calls[2][2]['content'])

    def test_invalid_future_memory_is_repaired(self):
        self.prepare((1, 3))
        def complete(messages, schema):
            response = valid_reply(messages, schema)
            if len(self.calls) == 1:
                return modify_response(response, lambda d: d.update(memory=[{
                    'character_id': 'a', 'kind': 'fact', 'text': 'Future event.', 'evidence_ids': ['id-3']}]))
            return response
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 2)
        first = next(read_jsonl(self.layout.root / 'api/initial/turn-000000.jsonl'))
        self.assertEqual(first['memory_after'], [])

    def test_same_label_is_one_turn_across_scene_changes(self):
        self.records[2:] = [replace(r, scene='hall') for r in self.records[2:]]
        self.prepare((4,))
        self.agent().run(self.layout)
        self.assertEqual(len(self.calls), 1)
        self.assertIn('T003 and following targets in this scope', self.calls[0][1]['content'])

    def test_independent_labels_run_as_parallel_turns(self):
        self.records[2:] = [replace(r, label='next') for r in self.records[2:]]
        self.prepare((4,))
        self.agent().run(self.layout)
        self.assertEqual(len(self.calls), 2)
        response = next(read_jsonl(self.layout.annotation_responses))['response']
        self.assertEqual([row['id'] for row in response['annotations']], [r.id for r in self.records])

    def test_failure_keeps_prior_commits_and_resume_skips_them(self):
        self.prepare()
        def complete(messages, schema):
            if len(self.calls) > 1:
                raise ValueError('Temporary simulated service failure')
            return valid_reply(messages, schema)
        with self.assertRaisesRegex(ValueError, 'simulated'):
            self.agent(complete=complete).run(self.layout)
        self.calls.clear()
        self.agent().run(self.layout)
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(len(list(read_jsonl(self.layout.annotation_responses))), 4)

    def test_truncated_output_splits_and_replays_checkpoints(self):
        self.prepare((4,))
        def complete(messages, schema):
            response = valid_reply(messages, schema)
            if len(self.calls) == 1:
                response['choices'][0]['finish_reason'] = 'length'
            return response
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 3)
        self.calls.clear()
        self.agent().run(self.layout)
        self.assertEqual(len(self.calls), 0)

    def test_truncated_parallel_output_falls_back_to_adaptive_split(self):
        self.records[2:] = [replace(r, label='next') for r in self.records[2:]]
        self.prepare((4,))
        truncations = 0
        def complete(messages, schema):
            nonlocal truncations
            response = valid_reply(messages, schema)
            if truncations < 2 and 'opening' in messages[1]['content']:
                truncations += 1
                response['choices'][0]['finish_reason'] = 'length'
            return response
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(AnnotationValidationStage(self.config).run(self.layout).accepted_count, 4)
        self.assertEqual(len(self.calls), 6)

    def test_large_turn_is_split_before_requesting_completion(self):
        self.prepare((4,))
        self.config = replace(self.config, cleaning=replace(
            self.config.cleaning,
            api=replace(self.config.cleaning.api, max_completion_tokens=640),
        ))
        self.agent().run(self.layout)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all('T003' not in messages[2]['content'] for messages in self.calls))

    def test_repeated_batch_validation_failure_splits_the_turn(self):
        self.prepare((4,))
        def complete(messages, schema):
            response = valid_reply(messages, schema)
            if 'T003' in messages[2]['content']:
                return modify_response(response, lambda d: d['annotations'].pop())
            return response
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(AnnotationValidationStage(self.config).run(self.layout).accepted_count, 4)

    def test_retry_checkpoint_does_not_alias_initial_checkpoint(self):
        requests = self.prepare((4,))
        self.agent().run(self.layout)
        write_jsonl(requests, self.layout.retry_requests)
        self.calls.clear()
        self.agent().run(self.layout, retry=True)
        self.assertEqual(len(self.calls), 1)

    def test_split_survives_failure_before_first_child_commit(self):
        self.prepare((4,))
        def complete(messages, schema):
            if len(self.calls) == 2:
                raise ValueError('Interrupted child')
            response = valid_reply(messages, schema)
            response['choices'][0]['finish_reason'] = 'length'
            return response
        with self.assertRaisesRegex(ValueError, 'Interrupted child'):
            self.agent(complete=complete).run(self.layout)
        self.calls.clear()
        self.agent().run(self.layout)
        self.assertEqual(len(self.calls), 2)
        self.assertNotIn('T003', self.calls[0][2]['content'])

    def test_preview_is_readable_and_does_not_call_provider(self):
        self.prepare((4,))
        report = self.agent().run(self.layout, preview=True)
        preview = next(read_jsonl(Path(report['preview'])))
        self.assertEqual(preview['response_format_schema']['properties']['memory']['items']['properties']['kind']['enum'],
                         ['fact', 'unresolved'])
        self.assertIn('T001', preview['messages'][2]['content'])
        self.assertIn('Current dialogue', preview['messages'][2]['content'])
        self.assertEqual(self.calls, [])
        self.assertFalse(self.layout.annotation_responses.exists())

    def test_wrong_polish_text_cannot_pass_by_producing_valid_json(self):
        self.prepare((4,))
        self.agent().run(self.layout)
        AnnotationValidationStage(self.config).run(self.layout)
        PolishStage(self.config).prepare(self.layout, prompt_path=self.root / self.config.codex.polish_prompt_path)
        def complete(messages, schema):
            return modify_response(valid_reply(messages, schema),
                lambda d: d['annotations'][0].update(spoken_text='<emotion name="neutral">Changed words.</emotion>'))
        with self.assertRaises(ValueError):
            self.agent('polish', complete).run(self.layout.polish)
        self.assertFalse((self.layout.polish.root / 'api/initial/turn-000000.jsonl').exists())
        self.assertTrue(list((self.layout.polish.root / 'api/initial/failed-attempts').glob('*.jsonl')))

    def test_configuration_stages_are_independent(self):
        path = self.root / 'configs/pipeline.toml'
        base = re.sub(r'backend = "api"', 'backend = "codex"', path.read_text())
        base = re.sub(r'base_url = "[^\"]*"', 'base_url = ""', base)
        base = re.sub(r'model = "[^\"]*"', 'model = ""', base)
        for cleaning in ('codex', 'api'):
            for polish in ('codex', 'api'):
                text = base.replace('[cleaning]\nbackend = "codex"', f'[cleaning]\nbackend = "{cleaning}"')
                text = text.replace('[polish]\nbackend = "codex"', f'[polish]\nbackend = "{polish}"')
                text = text.replace('base_url = ""', 'base_url = "https://example.invalid/v1"').replace('model = ""', 'model = "test"')
                path.write_text(text)
                config = load_pipeline_config(repository_root=self.root)
                self.assertEqual((config.cleaning.backend, config.polish.backend), (cleaning, polish))
        path.write_text(base.replace('[cleaning]\nbackend = "codex"', '[cleaning]\nbackend = "api"'))
        with self.assertRaises(ConfigurationError):
            load_pipeline_config(repository_root=self.root)

    def test_kantoku_scopes_merge_and_do_not_leak(self):
        (self.root / 'kantoku').mkdir()
        (self.root / 'kantoku/a.toml').write_text('''name = "game/AmiEvents.rpy"
[characters.a]
state = "Concealing anxiety."
acting = "Restrained."
[[labels]]
name = "opening"
[labels.characters.a]
acting = "Trying to sound cheerful."
[[labels.scenes]]
name = "room"
start_line = 2
end_line = 2
[labels.scenes.characters.a]
acting = "Beginning to falter."
''')
        director = Kantoku(self.root, self.config, self.characters)
        middle = director.resolve(self.records[1].model_view())
        later = director.resolve(self.records[2].model_view())
        self.assertEqual(middle['characters']['a']['state'], 'Concealing anxiety.')
        self.assertEqual(middle['characters']['a']['acting'], 'Beginning to falter.')
        self.assertEqual(later['characters']['a']['acting'], 'Trying to sound cheerful.')
        request = self.prepare((4,))[0]
        parts = list(split_directed_request(request))
        self.assertEqual([len(p['batch']['targets']) for p in parts], [1, 1, 2])
        (self.root / 'kantoku/a.toml').write_text('name = "game/AmiEvents.rpy"')
        with self.assertRaisesRegex(ValueError, 'Kantoku changed'):
            self.agent().run(self.layout)

    def test_source_round_trip_and_scene_instances(self):
        path = self.root / 'source.rpy'
        path.write_text('label a:\n    scene bg room with fade\n    a "First"\n'
                        '    scene bg room\n    a "Second"\nlabel b:\n    a "Third"\n')
        index = RenPySourceContextIndex(path)
        self.assertEqual(index.at(3).scene, 'bg room')
        self.assertNotEqual(index.at(3).scene_line, index.at(5).scene_line)
        self.assertEqual(index.at(7).scene, '')
        batch = DialogueBatch('b', (), (self.records[0],), ())
        self.assertEqual(DialogueBatch.from_dict(batch.to_dict()).targets[0].scene, 'room')
        self.assertEqual(DialogueBatch.from_dict(batch.to_dict()).targets[0].label, 'opening')

    def test_transport_uses_configured_endpoint_and_strict_schema(self):
        api = replace(self.config.cleaning.api, base_url='https://example.invalid/v1', model='model-a', response_format='json_schema')
        reply = MagicMock()
        reply.__enter__.return_value.read.side_effect = [b'{"choices": [', b'{"choices": []}']
        opener = MagicMock()
        opener.open.side_effect = [RemoteDisconnected('closed'), reply, reply]
        with patch.dict('os.environ', {api.api_key_environment: 'test-secret'}), patch(
                'lessons_in_cast_core.annotation.agent.build_opener', return_value=opener), patch(
                'lessons_in_cast_core.annotation.agent.time.sleep'):
            chat_completion(api, [{'role': 'user', 'content': 'input'}], {'type': 'object'})
        self.assertEqual(opener.open.call_count, 3)
        request = opener.open.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.full_url, 'https://example.invalid/v1/chat/completions')
        self.assertEqual(payload['model'], 'model-a')
        self.assertTrue(payload['reasoning_split'])
        self.assertTrue(payload['response_format']['json_schema']['strict'])
        self.assertNotIn('test-secret', request.data.decode())

    def test_review_memory_remains_unresolved_and_cannot_enable_polish(self):
        self.prepare((4,))
        def complete(messages, schema):
            def change(document):
                document['annotations'][0]['review_required'] = True
                document['memory'] = [{'character_id': 'a', 'kind': 'fact' if len(self.calls) == 1 else 'unresolved',
                                       'text': 'Intent unclear.', 'evidence_ids': ['id-0']}]
            return modify_response(valid_reply(messages, schema), change)
        self.agent(complete=complete).run(self.layout)
        self.assertEqual(len(self.calls), 1)
        commit = next(read_jsonl(self.layout.root / 'api/initial/turn-000000.jsonl'))
        self.assertEqual(commit['memory_after'][0]['kind'], 'unresolved')
        summary = AnnotationValidationStage(self.config).run(self.layout)
        self.assertEqual(summary.review_required_count, 1)
        with self.assertRaisesRegex(ValueError, 'requires accepted'):
            PolishStage(self.config).prepare(self.layout)

    def test_scene_changes_drop_local_memory_but_keep_character_state(self):
        state = {'character_id': 'a', 'kind': 'acting_hypothesis', 'text': 'Restrained.', 'evidence_ids': ['id-0']}
        local = {**state, 'character_id': '', 'kind': 'fact', 'text': 'In a quiet room.'}
        previous = ['file', 'label', 'room', 1]
        following = ['file', 'label', 'room', 10]
        self.assertEqual(transition_memory([state, local], previous, following, {}), [state])
        self.assertEqual(transition_memory([state], previous, ['other', 'label', 'room', 1], {}), [])
        self.assertEqual(transition_memory([state], previous, ['file', 'next', 'room', 1], {}), [])
        self.assertEqual(transition_memory([state], previous, ['file', 'next', 'room', 1], {'continuity_from': 'label'}), [state])

    def test_kantoku_render_overrides_reach_production_jobs(self):
        from lessons_in_cast_core.synthesis.planner import SynthesisPlanner
        from .helpers import accepted_annotation
        source = self.records[0]
        routed = []
        planner = SynthesisPlanner(self.characters, direction_context={source.id: {'render': {'a': {
            'default_voice_profile': 'profiles/directed/pipeline.py', 'performance': {'speed': 0.85}}}}},
            voice_route_available=lambda character_id, profile: routed.append(profile) or True)
        result = planner.plan({source.id: source}, [accepted_annotation(source)])
        self.assertEqual(result.jobs[0].voice_profile, 'profiles/directed/pipeline.py')
        self.assertEqual(result.jobs[0].performance.speed, 0.85)
        self.assertEqual(routed, ['profiles/directed/pipeline.py'])

    def test_modified_checkpoint_is_rejected(self):
        self.prepare((4,))
        self.agent().run(self.layout)
        path = self.layout.root / 'api/initial/turn-000000.jsonl'
        commit = next(read_jsonl(path))
        commit['annotations'][0]['spoken_text'] = 'Tampered.'
        write_jsonl([commit], path)
        with self.assertRaisesRegex(ValueError, 'checkpoint was modified'):
            self.agent().run(self.layout)

    def test_cli_dispatches_to_the_selected_stage_backend(self):
        from contextlib import redirect_stdout
        from io import StringIO
        from types import SimpleNamespace
        from lessons_in_cast_core.cli import main
        self.prepare((4,))
        for backend in ('api', 'codex'):
            configured = replace(self.config, cleaning=replace(self.config.cleaning, backend=backend),
                                 codex=replace(self.config.codex, source_files=()))
            agent = MagicMock()
            agent.run.return_value = {'backend': 'api'}
            with patch('lessons_in_cast_core.cli.load_pipeline_config', return_value=configured), patch(
                    'lessons_in_cast_core.cli.load_workspace_config', return_value=SimpleNamespace(release_path=self.root)), patch(
                    'lessons_in_cast_core.cli.load_characters', return_value=self.characters), patch(
                    'lessons_in_cast_core.cli.load_dialogue_sources', return_value=()), patch(
                    'lessons_in_cast_core.cli.load_dialogue_scopes', return_value={}), patch(
                    'lessons_in_cast_core.annotation.agent.AnnotationAgent', return_value=agent), redirect_stdout(StringIO()):
                main(['--root', str(self.root), '--build-dir', str(self.layout.root), 'annotate', '--stage', 'cleaning'])
            self.assertEqual(agent.run.call_count, 1 if backend == 'api' else 0)
        self.assertTrue((self.layout.root / 'codex/initial/inbox.json').is_file())


if __name__ == '__main__':
    unittest.main()
