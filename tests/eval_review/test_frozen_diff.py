"""Diff evidence is generated from frozen, snapshot-verified source bytes."""
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'SHARED' / 'runtime'))
from hb_eval_review import frozen_diff
from hb_eval_review.snapshot import PacketPolicyError, compute_source_snapshot


def git(repo, *args):
    return subprocess.check_output(['git', *args], cwd=str(repo), stderr=subprocess.PIPE)


class FrozenDiffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        git(self.repo, 'config', 'user.name', 'Fixture')
        self.write('app.txt', b'base\n')
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'base')
        self.base_sha = git(self.repo, 'rev-parse', 'HEAD').decode().strip()

    def write(self, name, data):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def commit(self):
        git(self.repo, 'add', '-A')
        git(self.repo, 'commit', '-qm', 'fixture')
        self.base_sha = git(self.repo, 'rev-parse', 'HEAD').decode().strip()

    def build(self, snapshot=None):
        return frozen_diff.build_frozen_diff(
            self.repo, self.base_sha, snapshot or compute_source_snapshot(self.repo))

    def assert_applies_to_current(self, diff, snapshot):
        target = self.root / 'apply-check'
        git(self.root, 'clone', '-q', '--no-local', str(self.repo), str(target))
        git(target, 'checkout', '-q', self.base_sha)
        result = subprocess.run(['git', 'apply', '--binary', '-'], cwd=str(target),
                                input=diff, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(0, result.returncode, result.stderr.decode('utf-8', 'replace'))
        expected = [entry for entry in snapshot['manifest']['files']
                    if not entry['path'].startswith('.harness/artifacts/')]
        # Ignored-but-staged additions are deliberately staged in the applying copy too,
        # otherwise its independent enumerator would not see the newly applied file.
        staged = git(self.repo, 'diff', '--cached', '--name-only', '-z').split(b'\0')
        for raw in filter(None, staged):
            name = raw.decode('utf-8', 'surrogateescape')
            if (target / name).exists():
                git(target, 'add', '-f', '--', name)
        actual = [entry for entry in compute_source_snapshot(target)['manifest']['files']
                  if not entry['path'].startswith('.harness/artifacts/')]
        self.assertEqual(expected, actual)

    def test_diff_applies_all_change_kinds_and_excludes_only_artifact_tree(self):
        self.write('delete.txt', b'remove me\n')
        self.write('executable.sh', b'echo hello\n').chmod(0o644)
        self.write('binary.dat', b'\0before\xff\x10')
        self.write('space name.txt', b'old space\n')
        self.write('quote"tab\tname.txt', b'old quoted\n')
        self.write('.harness/docs/guide.md', b'old docs\n')
        self.write('.harness/artifacts/feature/old.txt', b'private old artifact\n')
        (self.repo / 'external-link').symlink_to(str(self.root / 'absent-old'))
        self.commit()
        self.write('app.txt', b'current\n')
        (self.repo / 'delete.txt').unlink()
        (self.repo / 'executable.sh').chmod(0o755)
        self.write('binary.dat', b'\0after\xff\x11')
        self.write('space name.txt', b'new space\n')
        self.write('quote"tab\tname.txt', b'new quoted\n')
        self.write('added space\t한.txt', b'untracked\n')
        self.write('untracked.txt', b'new untracked\n')
        self.write('.gitignore', b'ignored-staged.txt\n')
        self.write('ignored-staged.txt', b'new staged but ignored\n')
        git(self.repo, 'add', '-f', 'ignored-staged.txt')
        self.write('.harness/docs/guide.md', b'new docs\n')
        self.write('.harness/artifacts/feature/old.txt', b'private modified artifact\n')
        self.write('.harness/artifacts/feature/new.txt', b'private new artifact\n')
        (self.repo / 'external-link').unlink()
        (self.repo / 'external-link').symlink_to(str(self.root / 'absent-new'))
        snapshot = compute_source_snapshot(self.repo)
        before_index = (self.repo / '.git/index').read_bytes()
        result = self.build(snapshot)
        self.assertIn(b'GIT binary patch', result)
        self.assertIn(b'old mode 100644\nnew mode 100755', result)
        self.assertIn(b'.harness/docs/guide.md', result)
        self.assertNotIn(b'.harness/artifacts/', result)
        self.assertNotIn(b'private ', result)
        self.assertEqual(before_index, (self.repo / '.git/index').read_bytes())
        self.assert_applies_to_current(result, snapshot)

    def test_live_bytes_changed_since_snapshot_are_rejected(self):
        self.write('app.txt', b'A bound\n')
        snapshot = compute_source_snapshot(self.repo)
        self.write('app.txt', b'B unbound\n')
        with self.assertRaises(PacketPolicyError) as raised:
            self.build(snapshot)
        self.assertEqual('DIFF_SOURCE_MISMATCH', raised.exception.code)
        self.assertIn('app.txt', raised.exception.paths)

    def test_live_mode_changed_since_snapshot_is_rejected(self):
        self.write('app.txt', b'A bound\n').chmod(0o644)
        snapshot = compute_source_snapshot(self.repo)
        (self.repo / 'app.txt').chmod(0o755)
        with self.assertRaises(PacketPolicyError) as raised:
            self.build(snapshot)
        self.assertEqual('DIFF_SOURCE_MISMATCH', raised.exception.code)

    def test_live_symlink_changed_since_snapshot_is_rejected_without_following(self):
        victim = self.root / 'outside'
        victim.write_bytes(b'OUTSIDE SECRET NOT IN DIFF')
        (self.repo / 'link').symlink_to('app.txt')
        snapshot = compute_source_snapshot(self.repo)
        (self.repo / 'link').unlink()
        (self.repo / 'link').symlink_to(victim)
        with self.assertRaises(PacketPolicyError) as raised:
            self.build(snapshot)
        self.assertEqual('DIFF_SOURCE_MISMATCH', raised.exception.code)
        self.assertEqual(b'OUTSIDE SECRET NOT IN DIFF', victim.read_bytes())

    def test_live_parent_replaced_by_symlink_is_rejected(self):
        self.write('folder/inside.txt', b'bound\n')
        snapshot = compute_source_snapshot(self.repo)
        outside = self.root / 'outside-dir'; outside.mkdir()
        (outside / 'inside.txt').write_bytes(b'outside\n')
        shutil.rmtree(self.repo / 'folder')
        (self.repo / 'folder').symlink_to(outside)
        with self.assertRaises(PacketPolicyError) as raised:
            self.build(snapshot)
        self.assertEqual('PACKET_PATH_UNSAFE', raised.exception.code)

    def test_live_aba_during_git_diff_uses_frozen_A_bytes(self):
        self.write('app.txt', b'A bound\n')
        snapshot = compute_source_snapshot(self.repo)
        original_run = frozen_diff.subprocess.run
        observed = []
        def mutate_while_diffing(args, *positional, **kwargs):
            if '--no-index' not in args:
                return original_run(args, *positional, **kwargs)
            observed.append(Path(kwargs['cwd']))
            self.write('app.txt', b'B transient wrong\n')
            try:
                return original_run(args, *positional, **kwargs)
            finally:
                self.write('app.txt', b'A bound\n')
        with patch.object(frozen_diff.subprocess, 'run', side_effect=mutate_while_diffing):
            result = self.build(snapshot)
        self.assertEqual(1, len(observed))
        self.assertNotEqual(self.repo, observed[0])
        self.assertIn(b'+A bound\n', result)
        self.assertNotIn(b'B transient wrong', result)
        self.assertEqual(snapshot['source_snapshot_id'], compute_source_snapshot(self.repo)['source_snapshot_id'])

    def test_diff_uses_supplied_base_commit_even_when_branch_moves(self):
        self.write('app.txt', b'intermediate committed\n')
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'advance branch')
        self.write('app.txt', b'final working\n')
        result = self.build()
        self.assertIn(b'-base\n', result)
        self.assertIn(b'+final working\n', result)
        self.assertNotIn(b'intermediate committed', result)

    def test_header_prefixes_are_repo_relative_and_body_is_never_rewritten(self):
        body = b'b/new path a/deleted path\ndiff --git b/literal b/literal\n--- a/literal\n+++ b/literal\n'
        self.write('added space.txt', body)
        self.write('added"quote.txt', b'quoted\n')
        self.write('newdir/한.txt', b'unicode\n')
        result = self.build()
        self.assertIn(b'diff --git a/added space.txt b/added space.txt\n', result)
        self.assertIn(b'\n+diff --git b/literal b/literal\n', result)
        self.assertIn(b'\n+--- a/literal\n', result)
        self.assertIn(b'\n++++ b/literal\n', result)
        self.assertNotIn(str(self.root).encode(), result)
        self.assertNotIn(b'hb-frozen-diff-', result)
        self.assert_applies_to_current(result, compute_source_snapshot(self.repo))

    def test_unrelated_git_settings_and_helpers_do_not_execute(self):
        marker = self.root / 'helper-ran'
        helper_file = self.root / 'helper.sh'
        helper_file.write_text('#!/bin/sh\nprintf ran > ' + str(marker) + '\n')
        helper_file.chmod(0o755)
        helper = str(helper_file)
        self.write('app.txt', b'current source\n')
        self.write('.gitattributes', b'app.txt filter=danger diff=danger\n')
        git(self.repo, 'config', 'filter.danger.clean', helper)
        git(self.repo, 'config', 'filter.danger.smudge', helper)
        git(self.repo, 'config', 'diff.danger.command', helper)
        git(self.repo, 'config', 'diff.danger.textconv', helper)
        git(self.repo, 'config', 'core.fsmonitor', helper)
        # Snapshot enumeration belongs to the existing caller; do it before poisoning
        # env/config entries that this diff helper must independently neutralize.
        git(self.repo, 'config', '--unset', 'core.fsmonitor')
        snapshot = compute_source_snapshot(self.repo)
        # Positive control: the same repository/helper configuration executes under
        # ordinary Git diff. The frozen path must block it, not merely fail to trigger it.
        git(self.repo, 'diff', self.base_sha)
        self.assertTrue(marker.exists())
        marker.unlink()
        git(self.repo, 'config', 'core.fsmonitor', helper)
        with patch.dict(os.environ, {'GIT_EXTERNAL_DIFF': helper, 'GIT_DIR': '/missing/git-dir',
                                     'GIT_CONFIG_COUNT': '1', 'GIT_CONFIG_KEY_0': 'diff.external',
                                     'GIT_CONFIG_VALUE_0': helper}):
            result = self.build(snapshot)
        self.assertFalse(marker.exists())
        self.assertIn(b'.gitattributes', result)

    def test_external_symlink_is_diffed_as_link_text_without_reading_target(self):
        outside = self.root / 'outside-secret'
        outside.write_bytes(b'NEVER COPY THIS CONTENT')
        (self.repo / 'link').symlink_to(outside)
        result = self.build()
        self.assertIn(str(outside).encode(), result)
        self.assertNotIn(b'NEVER COPY THIS CONTENT', result)
        self.assertIn(b'new file mode 120000', result)

    def test_snapshot_path_escape_and_git_metadata_are_rejected(self):
        for name in ('../outside', '/absolute', '.git/config', 'nested/.git/config'):
            with self.subTest(path=name):
                snapshot = compute_source_snapshot(self.repo)
                snapshot['manifest']['files'].append({'path': name, 'kind': 'file',
                    'mode': 0o644, 'sha256': hashlib.sha256(b'x').hexdigest()})
                with self.assertRaises(PacketPolicyError) as raised:
                    self.build(snapshot)
                self.assertEqual('PACKET_PATH_UNSAFE', raised.exception.code)

    def test_git_visible_untracked_cache_stays_in_diff_without_claiming_snapshot_binding(self):
        before = compute_source_snapshot(self.repo)
        self.write('build/cache.txt', b'cache is full diff evidence\n')
        after = compute_source_snapshot(self.repo)
        self.assertEqual(before, after)
        self.assertNotIn('build/cache.txt', [entry['path'] for entry in after['manifest']['files']])
        result = self.build(after)
        self.assertIn(b'diff --git a/build/cache.txt b/build/cache.txt\n', result)
        self.assertIn(b'+cache is full diff evidence\n', result)
        control = subprocess.run(['git', 'diff', '--no-index', '--binary', '--',
                                  '/dev/null', 'build/cache.txt'], cwd=str(self.repo),
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertEqual(1, control.returncode)
        self.assertIn(b'+cache is full diff evidence\n', control.stdout)

    def test_untracked_cache_is_frozen_before_aba_during_diff(self):
        self.write('build/cache.txt', b'A cache\n')
        snapshot = compute_source_snapshot(self.repo)
        original = frozen_diff.subprocess.run
        def mutate(args, *positional, **kwargs):
            if '--no-index' not in args:
                return original(args, *positional, **kwargs)
            self.write('build/cache.txt', b'B cache transient\n')
            try:
                return original(args, *positional, **kwargs)
            finally:
                self.write('build/cache.txt', b'A cache\n')
        with patch.object(frozen_diff.subprocess, 'run', side_effect=mutate):
            result = self.build(snapshot)
        self.assertIn(b'+A cache\n', result)
        self.assertNotIn(b'B cache transient', result)

    def test_untracked_cache_secret_material_is_rejected(self):
        self.write('build/.env.local', b'fake fixture secret\n')
        snapshot = compute_source_snapshot(self.repo)
        self.assertNotIn('build/.env.local', [entry['path'] for entry in snapshot['manifest']['files']])
        with self.assertRaises(PacketPolicyError) as raised:
            self.build(snapshot)
        self.assertEqual('PACKET_SECRET_MATERIAL_PRESENT', raised.exception.code)
        self.assertEqual(['build/.env.local'], raised.exception.paths)

    def test_new_noncache_file_absent_from_snapshot_cannot_enter_diff(self):
        snapshot = compute_source_snapshot(self.repo)
        self.write('new-unbound.txt', b'not in Gate snapshot\n')
        with self.assertRaises(PacketPolicyError) as raised:
            self.build(snapshot)
        self.assertEqual('DIFF_SOURCE_MISMATCH', raised.exception.code)
        self.assertIn('new-unbound.txt', raised.exception.paths)

    def test_hash_check_reads_actual_copy_bytes(self):
        self.write('app.txt', b'A bound\n')
        snapshot = compute_source_snapshot(self.repo)
        original = Path.write_bytes
        corrupted = []
        def corrupt_copy(path, data):
            if path.name == 'app.txt' and path.parent.name == 'b':
                corrupted.append(path)
                return original(path, b'B corrupt copy\n')
            return original(path, data)
        with patch.object(Path, 'write_bytes', new=corrupt_copy):
            with self.assertRaises(PacketPolicyError) as raised:
                self.build(snapshot)
        self.assertEqual(1, len(corrupted))
        self.assertEqual('DIFF_SOURCE_MISMATCH', raised.exception.code)
        self.assertEqual(b'A bound\n', (self.repo / 'app.txt').read_bytes())

    def test_git_process_error_is_explicit_failure(self):
        snapshot = compute_source_snapshot(self.repo)
        original = frozen_diff.subprocess.run
        def reject(args, *positional, **kwargs):
            if '--no-index' in args:
                return subprocess.CompletedProcess(args, 128, b'', b'synthetic failure')
            return original(args, *positional, **kwargs)
        with patch.object(frozen_diff.subprocess, 'run', side_effect=reject):
            with self.assertRaises(PacketPolicyError) as raised:
                self.build(snapshot)
        self.assertEqual('DIFF_UNAVAILABLE', raised.exception.code)

    def test_missing_promisor_object_does_not_start_a_remote_helper(self):
        marker = self.root / 'remote-helper-ran'
        helper = self.root / 'remote-helper.sh'
        helper.write_text('#!/bin/sh\nprintf ran > ' + str(marker) + '\nexit 1\n')
        helper.chmod(0o755)
        object_id = git(self.repo, 'rev-parse', self.base_sha + ':app.txt').decode().strip()
        snapshot = compute_source_snapshot(self.repo)
        git(self.repo, 'config', 'extensions.partialClone', 'fixture')
        git(self.repo, 'config', 'remote.fixture.promisor', 'true')
        git(self.repo, 'config', 'remote.fixture.url', 'ext::' + str(helper))
        git(self.repo, 'config', 'protocol.ext.allow', 'always')
        (self.repo / '.git/objects' / object_id[:2] / object_id[2:]).unlink()
        control_env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        control = subprocess.run(['git', 'cat-file', 'blob', object_id], cwd=str(self.repo),
                                 env=control_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertNotEqual(0, control.returncode)
        self.assertTrue(marker.exists(), 'ordinary Git must exercise the configured remote helper')
        marker.unlink()
        with self.assertRaises(PacketPolicyError) as raised:
            self.build(snapshot)
        self.assertEqual('DIFF_UNAVAILABLE', raised.exception.code)
        self.assertFalse(marker.exists())

    def test_replace_ref_cannot_rewrite_the_fixed_base(self):
        self.write('app.txt', b'replacement commit\n')
        git(self.repo, 'add', '-A'); git(self.repo, 'commit', '-qm', 'replacement')
        other = git(self.repo, 'rev-parse', 'HEAD').decode().strip()
        git(self.repo, 'replace', self.base_sha, other)
        self.assertEqual(b'replacement commit\n', git(self.repo, 'show', self.base_sha + ':app.txt'))
        self.write('app.txt', b'current working\n')
        result = self.build()
        self.assertIn(b'-base\n', result)
        self.assertIn(b'+current working\n', result)
        self.assertNotIn(b'replacement commit', result)
