"""Snapshot and frozen diff share passive ignore rules without enabling helpers."""
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'SHARED' / 'runtime'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hb_eval_review import frozen_diff
from hb_eval_review.pack import build_packet
from hb_eval_review.snapshot import PacketPolicyError, compute_source_snapshot
from test_gate_pack_run import evidence_fixture


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=str(repo), stderr=subprocess.PIPE)


class GlobalIgnoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.home = self.root / 'home'
        self.home.mkdir()
        environment = {key: value for key, value in os.environ.items()
                       if not key.startswith('GIT_')}
        environment.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / 'xdg'))
        self.environment = patch.dict(os.environ, environment, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.name', 'Fixture')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        (self.repo / 'app.py').write_text('value = 1\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'fixture')
        self.base_sha = git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        (self.repo / 'app.py').write_text('value = 2\n')

    def global_ignore(self, patterns, path_value=None):
        rules = self.home / 'ignore rules 한.txt'
        rules.write_text(patterns)
        git(self.repo, 'config', '--global', 'core.excludesFile',
            str(rules) if path_value is None else path_value)
        return rules

    def pack(self):
        artifacts, request_name = evidence_fixture(self.repo)
        snapshot = compute_source_snapshot(self.repo)
        packet = build_packet(self.repo, artifacts, request_name, 'HEAD',
                              {'claude': 'claude-test', 'codex': 'codex-test'})
        self.assertEqual(snapshot['source_snapshot_id'], packet['source_snapshot_id'])
        self.assertEqual(snapshot, compute_source_snapshot(self.repo))
        diff = (artifacts / 'eval-review' / 'diff.patch').read_bytes()
        self.assertIn(b'-value = 1\n+value = 2\n', diff)
        return snapshot, diff

    def test_pack_global_ignored_file_is_absent_from_snapshot_and_diff(self):
        for path_form in ('absolute', 'home_relative'):
            with self.subTest(path_form=path_form):
                self.global_ignore('.DS_Store\n', None if path_form == 'absolute'
                                   else '~/ignore rules 한.txt')
                ignored = self.repo / '.DS_Store'
                ignored.unlink(missing_ok=True)
                before = compute_source_snapshot(self.repo)
                ignored.write_text('synthetic globally ignored content\n')
                self.assertEqual(before, compute_source_snapshot(self.repo))
                snapshot, diff = self.pack()
                self.assertNotIn('.DS_Store', [row['path'] for row in snapshot['manifest']['files']])
                self.assertNotIn(b'.DS_Store', diff)
                self.assertNotIn(b'synthetic globally ignored content', diff)

    def test_repo_local_excludes_override_global_not_merge_with_it(self):
        self.global_ignore('.DS_Store\n')
        local = self.home / 'local ignore'
        local.write_text('local-only.txt\n')
        git(self.repo, 'config', 'core.excludesFile', str(local))
        (self.repo / '.DS_Store').write_text('global rule overridden\n')
        (self.repo / 'local-only.txt').write_text('local ignored content\n')
        snapshot, diff = self.pack()
        names = [row['path'] for row in snapshot['manifest']['files']]
        self.assertIn('.DS_Store', names)
        self.assertNotIn('local-only.txt', names)
        self.assertIn(b'+global rule overridden\n', diff)
        self.assertNotIn(b'local-only.txt', diff)

    def test_config_file_locator_env_matches_snapshot_precedence(self):
        rules = self.home / 'custom ignore'
        rules.write_text('.DS_Store\n')
        config = self.home / 'custom gitconfig'
        git(self.repo, 'config', '--file', str(config), 'core.excludesFile', str(rules))
        (self.repo / '.DS_Store').write_text('synthetic config file override\n')
        cases = (
            ({'GIT_CONFIG_GLOBAL': str(config)}, True),
            ({'GIT_CONFIG_SYSTEM': str(config)}, True),
            ({'GIT_CONFIG_SYSTEM': str(config), 'GIT_CONFIG_NOSYSTEM': '1'}, False),
        )
        for environment, ignored in cases:
            with self.subTest(environment=sorted(environment), ignored=ignored):
                with patch.dict(os.environ, environment):
                    snapshot, diff = self.pack()
                names = [row['path'] for row in snapshot['manifest']['files']]
                self.assertEqual(not ignored, '.DS_Store' in names)
                self.assertEqual(not ignored, b'+synthetic config file override\n' in diff)

    def test_empty_repo_local_excludes_disables_the_global_file(self):
        self.global_ignore('.DS_Store\n')
        git(self.repo, 'config', 'core.excludesFile', '')
        (self.repo / '.DS_Store').write_text('explicit local empty override\n')
        snapshot, diff = self.pack()
        self.assertIn('.DS_Store', [row['path'] for row in snapshot['manifest']['files']])
        self.assertIn(b'+explicit local empty override\n', diff)

    def test_command_scope_ignore_matches_snapshot_without_config_only_override(self):
        rules = self.home / 'command scope ignore'
        rules.write_text('.DS_Store\n')
        config = self.home / 'config-only gitconfig'
        git(self.repo, 'config', '--file', str(config), 'core.excludesFile', str(rules))
        (self.repo / '.DS_Store').write_text('synthetic command scope override\n')
        (self.repo / 'build').mkdir()
        (self.repo / 'build' / '.DS_Store').write_text('synthetic command scope cache\n')
        cases = (
            ({'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'core.excludesFile',
              'GIT_CONFIG_VALUE_0': str(rules)}, True),
            ({'GIT_CONFIG_PARAMETERS': shlex.quote('core.excludesFile=' + str(rules))}, True),
            # GIT_CONFIG affects only `git config`, so forwarding it to the lookup
            # would invent ignore rules that snapshot's `git ls-files` never sees.
            ({'GIT_CONFIG': str(config)}, False),
        )
        for environment, ignored in cases:
            with self.subTest(environment=sorted(environment), ignored=ignored):
                with patch.dict(os.environ, environment):
                    snapshot, diff = self.pack()
                names = [row['path'] for row in snapshot['manifest']['files']]
                self.assertEqual(not ignored, '.DS_Store' in names)
                self.assertEqual(not ignored, b'+synthetic command scope override\n' in diff)
                self.assertNotIn('build/.DS_Store', names)
                self.assertEqual(not ignored, b'+synthetic command scope cache\n' in diff)

    def test_default_xdg_ignore_and_ordinary_source_identity_stay_unchanged(self):
        rules = self.home / 'xdg' / 'git' / 'ignore'
        rules.parent.mkdir(parents=True)
        rules.write_text('xdg-ignored.txt\n')
        before = compute_source_snapshot(self.repo)
        (self.repo / 'xdg-ignored.txt').write_text('ignored by Git default\n')
        self.assertEqual(before, compute_source_snapshot(self.repo))
        (self.repo / 'visible.txt').write_text('ordinary untracked content\n')
        snapshot, diff = self.pack()
        self.assertIn('visible.txt', [row['path'] for row in snapshot['manifest']['files']])
        self.assertIn(b'+ordinary untracked content\n', diff)
        self.assertNotIn(b'xdg-ignored.txt', diff)

    def test_global_ignore_does_not_reenable_fsmonitor_or_diff_helpers(self):
        self.global_ignore('.DS_Store\n')
        (self.repo / '.DS_Store').write_text('ignored\n')
        snapshot = compute_source_snapshot(self.repo)
        markers = []
        for name, key in (('monitor', 'core.fsmonitor'), ('diff', 'diff.external'),
                          ('textconv', 'diff.danger.textconv'), ('filter', 'filter.danger.clean')):
            marker = self.root / (name + '-ran')
            helper = self.root / (name + '.sh')
            helper.write_text('#!/bin/sh\nprintf ran >> "' + str(marker) + '"\n')
            helper.chmod(0o755)
            git(self.repo, 'config', '--global', key, str(helper))
            markers.append(marker)
        attributes = self.home / 'attributes'
        attributes.write_text('app.py diff=danger filter=danger\n')
        git(self.repo, 'config', '--global', 'core.attributesFile', str(attributes))
        # The same settings really execute helpers under ordinary Git; both external
        # diff and attribute-selected textconv have positive controls.
        git(self.repo, 'diff', 'HEAD')
        self.assertTrue(markers[0].exists())
        self.assertTrue(markers[1].exists())
        git(self.repo, '-c', 'diff.external=', 'diff', '--no-ext-diff', '--textconv', 'HEAD')
        self.assertTrue(markers[2].exists())
        for marker in markers:
            marker.unlink(missing_ok=True)
        result = frozen_diff.build_frozen_diff(self.repo, self.base_sha, snapshot)
        self.assertIn(b'-value = 1\n+value = 2\n', result)
        self.assertNotIn(b'.DS_Store', result)
        self.assertEqual([], [marker.name for marker in markers if marker.exists()])

    def test_failed_ignore_lookup_is_blocked_instead_of_silently_ignored(self):
        snapshot = compute_source_snapshot(self.repo)
        run = frozen_diff.subprocess.run
        def fail_config(args, *positional, **kwargs):
            if 'config' in args and 'core.excludesFile' in args:
                return subprocess.CompletedProcess(args, 2, b'', b'synthetic config failure')
            return run(args, *positional, **kwargs)
        with patch.object(frozen_diff.subprocess, 'run', side_effect=fail_config):
            with self.assertRaises(PacketPolicyError) as blocked:
                frozen_diff.build_frozen_diff(self.repo, self.base_sha, snapshot)
        self.assertEqual('DIFF_UNAVAILABLE', blocked.exception.code)
