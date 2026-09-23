"""Read actual test cases from fresh runner-owned reports, without running tools.

Adapters support pytest xunit1 XML, Jest JSON, Gradle Test-task JUnit XML, and
xcresulttool's modern ``get test-results tests`` plus ``summary`` JSON. The
caller executes every command through the shared gate runner. In particular,
Xcode's two report_commands must succeed and their complete stdout must be
written to the corresponding report_json_paths before parse_report is called.
Command names select a report format; they are never evidence of execution.
Jest rejects known hook frames. Under the approved D2 policy, concrete assertion
failures with source frames remain valid when async/deep stacks omit the Circus
body frame. Such stacks can also hide async hooks; declaration location alone
cannot resolve that ambiguity. No runner or test environment is overridden.
"""

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import unquote, urlparse

_INVALID = 'TDD_RED_REASON_INVALID'
_PATH_INVALID = 'TDD_REPORT_PATH_INVALID'
_JEST_UNSUPPORTED = 'TDD_JEST_PHASE_UNSUPPORTED'
_REPORT_LIMIT = 32 * 1024 * 1024
_ASSERTION = re.compile(
    r'Assertion(?:Failed)?Error|AssertionFailedException|ComparisonFailure|'
    r'\bassert\s+|\bDID NOT RAISE\b|\bDID NOT WARN\b|\bFailed:\s|'
    r'\bJestAssertionError\b|\bexpect\([^\n]*\)\.|'
    r'\bXCTAssert\w*\b|\bXCTFail\b|\bXCTUnwrap\b|\bExpectation failed\b',
    re.IGNORECASE,
)
_FIXTURE = re.compile(
    r'failed on (?:setup|teardown)|\b(?:beforeAll|beforeEach|afterAll|afterEach)\b|'
    r'\b(?:fixture|setUp|tearDown)\s+(?:error|failure|failed)|'
    r'\b(?:collection|compilation|compile|import)\s+(?:error|failure|failed)',
    re.IGNORECASE,
)
_RUNTIME_ERROR = re.compile(
    r'\b(?:TypeError|ValueError|AttributeError|RuntimeError|KeyError|IndexError|'
    r'ImportError|ModuleNotFoundError|NameError|SyntaxError|ReferenceError|RangeError|'
    r'NullPointerException|IllegalStateException|IllegalArgumentException)(?::|\s*$)',
    re.MULTILINE,
)
_JEST_BODY_FRAME = re.compile(
    r'^\s+at (?:async )?_callCircusTest \([^\n()]*[/\\]jest-circus[/\\]build[/\\]'
    r'[^\n()]+\.js:\d+:\d+\)\s*$', re.MULTILINE,
)
_JEST_HOOK_FRAME = re.compile(r'^\s+at (?:async )?_callCircusHook\b', re.MULTILINE)
_JEST_ASSERTION_HEADER = re.compile(
    r'^\s*(?:(?:Error:\s*)?expect\([^\n]*\)\.|'
    r'(?:JestAssertionError|AssertionError)(?::|\s|\[))',
)
_JEST_JASMINE_FRAME = re.compile(
    r'^\s+at [^\n]*(?:[/\\]jest-jasmine2[/\\]|[/\\]jasmine-core[/\\])', re.MULTILINE,
)
_JEST_SOURCE_FRAME = re.compile(
    # Match the terminal line/column suffix, allowing parentheses within a
    # normal source path (including nested archive/worktree directory names).
    r'^\s+at (?:(?:[^\n(]+\s+)?\(([^\n]+):\d+:\d+\)|([^\n]+):\d+:\d+)\s*$',
    re.MULTILINE,
)


def _new_path(path: Path) -> None:
    if path.exists() or path.is_symlink():
        raise ValueError(_PATH_INVALID)


def _reject_overrides(argv: List[str]) -> None:
    for index, value in enumerate(argv):
        option = value.split('=', 1)[0].lower()
        if (option in {'--junitxml', '--junit-xml', '--json', '--outputfile',
                       '--output-file', '--reporters', '--testresultsprocessor',
                       '--init-script', '-resultbundlepath', '--testlocationinresults',
                       '--no-testlocationinresults'}
                or value.startswith('-I') or option == '-resultstreampath'):
            raise ValueError(_PATH_INVALID)
        if value in ('-o', '--override-ini'):
            if index + 1 < len(argv) and argv[index + 1].lower().startswith('junit_'):
                raise ValueError(_PATH_INVALID)
        if re.match(r'^(?:--override-ini=|-o=?)(?:junit_)', value, re.IGNORECASE):
            raise ValueError(_PATH_INVALID)
        # Gradle has no standard report CLI flag; these project/system property
        # overrides and caller init scripts must not compete with our init file.
        if value.startswith(('-P', '-D')) and re.search(r'junit|test.?report|test.?result', value, re.IGNORECASE):
            raise ValueError(_PATH_INVALID)


def _kind(argv: List[str]) -> str:
    names = [Path(value).name.lower() for value in argv]
    if 'xcodebuild' in names:
        return 'xcodebuild'
    if any(name in ('gradle', 'gradlew', 'gradlew.bat') for name in names):
        return 'gradle'
    if any(re.fullmatch(r'pytest(?:-\d+(?:\.\d+)*)?', name) for name in names):
        return 'pytest'
    if any(name in ('jest', 'jest.js', 'npm', 'yarn', 'pnpm', 'bun') for name in names):
        return 'jest'
    raise ValueError(_INVALID)


def _reject_unsupported_jest_options(argv: List[str]) -> None:
    for index, token in enumerate(argv):
        option, separator, value = token.partition('=')
        if not separator:
            value = argv[index + 1] if index + 1 < len(argv) and not argv[index + 1].startswith('-') else ''
        option = option.lower().replace('-', '')
        if option == 'nostacktrace' and value.lower() not in ('false', '0'):
            raise ValueError(_JEST_UNSUPPORTED)
        if option == 'testrunner' and 'jasmine' in value.lower():
            raise ValueError(_JEST_UNSUPPORTED)
        if option == 'config' and value.lstrip().startswith('{'):
            try:
                config = json.loads(value)
            except ValueError:
                continue  # The runner reports malformed configuration itself.
            if isinstance(config, dict) and (config.get('noStackTrace') is True
                    or 'jasmine' in str(config.get('testRunner', '')).lower()):
                raise ValueError(_JEST_UNSUPPORTED)


def prepare_report(argv: List[str], temporary: Path) -> Dict[str, Any]:
    """Inject owned output paths, preserving framework test selectors."""
    if not isinstance(argv, list) or not argv or any(not isinstance(x, str) or not x for x in argv):
        raise ValueError(_INVALID)
    _reject_overrides(argv)
    if temporary.is_symlink() or not temporary.is_dir():
        raise ValueError(_PATH_INVALID)
    temporary = temporary.resolve()
    kind = _kind(argv)
    if kind == 'jest':
        _reject_unsupported_jest_options(argv)
    names = {'pytest': 'pytest.xml', 'jest': 'jest.json', 'gradle': 'gradle-results',
             'xcodebuild': 'tests.xcresult'}
    report = temporary / names[kind]
    _new_path(report)
    command = list(argv)
    plan = {'kind': kind, 'argv': command, 'report_path': report, 'temporary': temporary}
    if kind == 'pytest':
        command.extend(['--junitxml=' + str(report), '-o', 'junit_family=xunit1'])
    elif kind == 'jest':
        if any(Path(x).name == 'npm' for x in argv) and '--' not in argv:
            command.append('--')
        command.extend(['--json', '--outputFile=' + str(report), '--testLocationInResults'])
    elif kind == 'gradle':
        script = temporary / 'runner-reports.gradle'
        _new_path(script)
        # projectsEvaluated runs after normal project/build-script setup. Final
        # values prevent a later task action from redirecting the owned output.
        # Configure every Test task, including those lazily registered by AGP.
        base = str(report).replace('\\', '\\\\').replace("'", "\\'")
        script.write_text("""gradle.projectsEvaluated {
    allprojects { project ->
        project.tasks.withType(org.gradle.api.tasks.testing.Test).configureEach { task ->
            def projectKey = project.path == ':' ? '_root' : project.path.substring(1).replace(':', '/')
            task.reports.junitXml.required.set(true)
            task.reports.junitXml.outputLocation.set(new File('%s', projectKey + '/' + task.name))
            task.reports.junitXml.required.finalizeValue()
            task.reports.junitXml.outputLocation.finalizeValue()
            task.outputs.upToDateWhen { false }
        }
    }
}
""" % base, encoding='utf-8')
        command.extend(['--init-script', str(script), '--rerun-tasks', '--no-build-cache'])
    else:
        command.extend(['-resultBundlePath', str(report)])
        paths = [temporary / 'xcresult-tests.json', temporary / 'xcresult-summary.json']
        for path in paths:
            _new_path(path)
        plan['report_json_path'] = paths[0]
        plan['report_json_paths'] = paths
        plan['report_commands'] = [
            ['xcrun', 'xcresulttool', 'get', 'test-results', name, '--path', str(report), '--compact']
            for name in ('tests', 'summary')
        ]
    return plan


def _owned_path(plan: Dict[str, Any], path: Path, *, directory: bool = False) -> Path:
    root = Path(plan['temporary'])
    path = Path(path)
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError(_PATH_INVALID) from error
    if '..' in relative.parts or root.is_symlink():
        raise ValueError(_PATH_INVALID)
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(_PATH_INVALID)
    if not (path.is_dir() if directory else path.is_file()):
        raise ValueError(_INVALID)
    return path


def _read(plan: Dict[str, Any], path: Path) -> str:
    path = _owned_path(plan, path)
    try:
        if path.stat().st_size > _REPORT_LIMIT:
            raise ValueError(_INVALID)
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as error:
        raise ValueError(_INVALID) from error


def _json(plan: Dict[str, Any], path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(_read(plan, path))
    except (TypeError, json.JSONDecodeError) as error:
        raise ValueError(_INVALID) from error
    if not isinstance(data, dict):
        raise ValueError(_INVALID)
    return data


def _file(value: Any, repo: Path) -> Optional[str]:
    if value is None or value == '':
        return None
    if not isinstance(value, str):
        raise ValueError(_INVALID)
    if value.startswith('file://'):
        value = unquote(urlparse(value).path)
    path = Path(value)
    path = path if path.is_absolute() else repo / path
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except (OSError, ValueError) as error:
        raise ValueError(_INVALID) from error


def _assertion(message: str) -> bool:
    return (bool(_ASSERTION.search(message)) and not bool(_FIXTURE.search(message))
            and not bool(_RUNTIME_ERROR.search(message)))


def _jest_assertion(message: str, repo: Path) -> bool:
    # Known hook frames win even if a body frame appears in the same message.
    # Matcher expected/received exception names are not the actual error type.
    if _JEST_HOOK_FRAME.search(message) or not _JEST_ASSERTION_HEADER.search(message):
        return False
    if _JEST_JASMINE_FRAME.search(message):
        raise ValueError(_JEST_UNSUPPORTED)
    if _JEST_BODY_FRAME.search(message):
        return True
    # D2: await and deep helpers can remove the Circus frame. Test declaration
    # location is not callback scope, so comparing line order would reject a
    # legitimate helper declared above the test. Accept a complete repository
    # source frame instead, with the explicit risk of an indistinguishable hook.
    for match in _JEST_SOURCE_FRAME.finditer(message):
        source = match.group(1) or match.group(2)
        if source in ('<anonymous>', 'native') or source.startswith('node:'):
            continue
        if source.startswith('file://'):
            source = unquote(urlparse(source).path)
        path = Path(source)
        path = path if path.is_absolute() else repo / path
        try:
            relative = path.resolve().relative_to(repo.resolve())
        except (OSError, ValueError):
            continue
        if 'node_modules' not in relative.parts and path.is_file():
            return True
    # This includes configured/trimmed no-stack reports. Missing phase support
    # is a distinct configuration limitation, not a claim of a runtime failure.
    raise ValueError(_JEST_UNSUPPORTED)


def _xml_assertion(failure: ET.Element) -> bool:
    kind = failure.get('type', '')
    message = failure.get('message', '')
    body = ''.join(failure.itertext())
    if _FIXTURE.search(message + '\n' + body):
        return False
    # Explicit JUnit types describe the reported failure, whereas earlier
    # exceptions in the body may be an assertion's expected or wrapped cause.
    if kind:
        return bool(_ASSERTION.search(kind))
    terminal = body.rstrip().splitlines()[-1] if body.rstrip() else ''
    # Pytest xunit1 has no failure type. Its final traceback line identifies
    # the terminal exception, including after pytest.raises catches an error.
    # Prefer that exception over source lines or earlier chained tracebacks.
    exception = re.search(
        r'(?:^|:\d+:\s*)([A-Za-z_][\w.]*(?:Error|Exception|Failure|Failed)|Failed)(?::|\s*$)',
        terminal,
    )
    if exception:
        name = exception.group(1)
        return bool(_ASSERTION.search(name)) or name.rsplit('.', 1)[-1] == 'Failed'
    return _assertion(message)


def _case(identifier: str, file: Optional[str], classname: str, outcome: str,
          assertion: bool = False) -> Dict[str, Any]:
    return {'id': identifier, 'file': file, 'classname': classname,
            'outcome': outcome, 'assertion': assertion}


def _xml_cases(plan: Dict[str, Any], path: Path, repo: Path) -> List[Dict[str, Any]]:
    text = _read(plan, path)
    if '<!DOCTYPE' in text or '<!ENTITY' in text:
        raise ValueError(_INVALID)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(_INVALID) from error
    if root.tag not in ('testsuite', 'testsuites'):
        raise ValueError(_INVALID)
    cases = []
    for node in root.iter('testcase'):
        name = node.get('name', '')
        classname = node.get('classname', '')
        file = _file(node.get('file'), repo)
        if not name or not (file or classname):
            raise ValueError(_INVALID)
        identity = file or classname
        if file:
            module = file.rsplit('.', 1)[0].replace('/', '.')
            if classname and classname != module:
                class_part = classname[len(module) + 1:] if classname.startswith(module + '.') else classname
                identity += '::' + class_part
        failures, errors, skipped = node.findall('failure'), node.findall('error'), node.findall('skipped')
        if sum(bool(x) for x in (failures, errors, skipped)) > 1:
            raise ValueError(_INVALID)
        outcome, assertion = 'PASS', False
        if errors:
            outcome = 'ERROR'
        elif skipped or node.get('status') in ('notrun', 'disabled'):
            outcome = 'SKIP'
        elif failures:
            outcome = 'FAIL'
            assertion = all(_xml_assertion(failure) for failure in failures)
        cases.append(_case(identity + '::' + name, file, classname, outcome, assertion))
    return cases


def _jest_cases(plan: Dict[str, Any], repo: Path) -> List[Dict[str, Any]]:
    data = _json(plan, plan['report_path'])
    suites = data.get('testResults')
    if not isinstance(suites, list):
        raise ValueError(_INVALID)
    cases = []
    outcomes = {'passed': 'PASS', 'failed': 'FAIL', 'pending': 'SKIP',
                'todo': 'SKIP', 'disabled': 'SKIP', 'skipped': 'SKIP'}
    for suite in suites:
        if not isinstance(suite, dict):
            raise ValueError(_INVALID)
        file = _file(suite.get('name'), repo)
        tests = suite.get('assertionResults')
        if not file or not isinstance(tests, list):
            raise ValueError(_INVALID)
        failed_cases = any(isinstance(test, dict) and test.get('status') == 'failed' for test in tests)
        if suite.get('testExecError') or (suite.get('status') == 'failed' and not failed_cases):
            cases.append(_case(file + '::[suite error]', file, '', 'ERROR'))
        for test in tests:
            if not isinstance(test, dict):
                raise ValueError(_INVALID)
            name, status = test.get('fullName'), test.get('status')
            ancestors, messages = test.get('ancestorTitles', []), test.get('failureMessages', [])
            if (not isinstance(name, str) or not name or not isinstance(status, str) or status not in outcomes
                    or not isinstance(ancestors, list) or not all(isinstance(x, str) for x in ancestors)
                    or not isinstance(messages, list) or not all(isinstance(x, str) for x in messages)):
                raise ValueError(_INVALID)
            outcome = outcomes[status]
            assertion = outcome == 'FAIL' and bool(messages) and all(_jest_assertion(message, repo) for message in messages)
            cases.append(_case(file + '::' + name, file, '.'.join(ancestors), outcome, assertion))
    return cases


def _xcode_cases(plan: Dict[str, Any], repo: Path) -> List[Dict[str, Any]]:
    _owned_path(plan, plan['report_path'], directory=True)
    tree, summary = [_json(plan, path) for path in plan['report_json_paths']]
    nodes, failures = tree.get('testNodes'), summary.get('testFailures')
    if not isinstance(nodes, list) or not isinstance(failures, list):
        raise ValueError(_INVALID)
    failure_messages = {}  # type: Dict[str, List[str]]
    for failure in failures:
        if not isinstance(failure, dict) or not isinstance(failure.get('failureText'), str):
            raise ValueError(_INVALID)
        identifier = failure.get('testIdentifierString')
        identifier_url = failure.get('testIdentifierURL')
        if not identifier and not identifier_url:
            raise ValueError(_INVALID)
        keys = [identifier, identifier_url]
        target = failure.get('targetName')
        if isinstance(target, str) and isinstance(identifier, str) and not identifier.startswith(target + '/'):
            keys.append(target + '/' + identifier)
        for key in keys:
            if key:
                if not isinstance(key, str):
                    raise ValueError(_INVALID)
                failure_messages.setdefault(key, []).append(failure['failureText'])
    cases = []
    outcomes = {'Passed': 'PASS', 'Failed': 'FAIL', 'Skipped': 'SKIP',
                'Expected Failure': 'SKIP', 'unknown': 'ERROR'}

    def walk(items: List[Any], bundle: str = '') -> None:
        for node in items:
            if not isinstance(node, dict):
                raise ValueError(_INVALID)
            children = node.get('children', [])
            if not isinstance(children, list):
                raise ValueError(_INVALID)
            kind = node.get('nodeType')
            current_bundle = node.get('name', '') if kind in ('Unit test bundle', 'UI test bundle') else bundle
            if kind in ('Test Case', 'Test Case Run'):
                identifier = node.get('nodeIdentifier')
                if not isinstance(identifier, str) or not identifier:
                    raise ValueError(_INVALID)
                result = node.get('result')
                if not isinstance(result, str) or result not in outcomes:
                    raise ValueError(_INVALID)
                outcome = outcomes[result]
                # A Test Case is the selected identity. Nested runs/repetitions
                # must not be counted again or allow a failed retry to disappear.
                run_results = []
                pending = list(children)
                while pending:
                    child = pending.pop()
                    if not isinstance(child, dict) or not isinstance(child.get('children', []), list):
                        raise ValueError(_INVALID)
                    pending.extend(child.get('children', []))
                    if child.get('nodeType') == 'Test Case Run':
                        if not isinstance(child.get('result'), str) or child.get('result') not in outcomes:
                            raise ValueError(_INVALID)
                        run_results.append(outcomes[child['result']])
                for more_severe in ('ERROR', 'FAIL', 'SKIP'):
                    if more_severe in run_results:
                        outcome = more_severe
                        break
                keys = [identifier, node.get('nodeIdentifierURL')]
                if current_bundle and not identifier.startswith(current_bundle + '/'):
                    keys.append(current_bundle + '/' + identifier)
                messages = [message for key in keys if key for message in failure_messages.get(key, [])]
                assertion = outcome == 'FAIL' and bool(messages) and all(_assertion(message) for message in messages)
                parts = identifier.split('/')
                classname = parts[-2] if len(parts) > 1 else ''
                cases.append(_case(identifier, None, classname, outcome, assertion))
            else:
                walk(children, current_bundle)
    walk(nodes)
    return cases


def parse_report(plan: Dict[str, Any], repo: Path) -> List[Dict[str, Any]]:
    """Return normalized cases. Missing, empty and malformed reports fail closed."""
    kind = plan.get('kind')
    if kind == 'pytest':
        cases = _xml_cases(plan, plan['report_path'], repo)
    elif kind == 'jest':
        cases = _jest_cases(plan, repo)
    elif kind == 'gradle':
        root = _owned_path(plan, plan['report_path'], directory=True)
        paths = sorted(root.rglob('*.xml'))
        cases = [case for path in paths for case in _xml_cases(plan, path, repo)]
    elif kind == 'xcodebuild':
        cases = _xcode_cases(plan, repo)
    else:
        raise ValueError(_INVALID)
    if not cases or len({case['id'] for case in cases}) != len(cases):
        raise ValueError(_INVALID)
    return cases
