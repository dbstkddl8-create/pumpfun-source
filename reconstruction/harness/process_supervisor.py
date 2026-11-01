"""Crash-resistant POSIX process-group supervision for harness commands.

The guardian is the session and process-group leader.  A trial inherits that
group, while a close-on-exec control pipe remains owned only by the caller.  If
the caller disappears, the guardian observes EOF and kills its own group.
"""
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time


SCHEMA = 'process-supervisor-v1'
STARTUP_TIMEOUT = 10.0
TERMINATION_GRACE = .5
TERMINATION_TIMEOUT = 2.0
IMPLEMENTATION_BYTES = Path(__file__).read_bytes()
IMPLEMENTATION_SHA256 = hashlib.sha256(IMPLEMENTATION_BYTES).hexdigest()


class SupervisionError(RuntimeError):
    """The guardian failed without returning an authenticated child status."""


def _write_event(descriptor, value):
    payload = (json.dumps(value, sort_keys=True) + '\n').encode('utf-8')
    while payload:
        written = os.write(descriptor, payload)
        payload = payload[written:]


def _guardian(control_descriptor, config_descriptor, status_descriptor):
    group = os.getpgrp()
    if group != os.getpid():
        _write_event(status_descriptor, {'schema': SCHEMA, 'event': 'error',
                                         'reason': 'guardian is not its process-group leader'})
        return 125
    try:
        with os.fdopen(config_descriptor, 'rb') as stream:
            config = json.loads(stream.read().decode('utf-8'))
        if config.get('schema') != SCHEMA:
            raise ValueError('invalid supervisor configuration schema')
        process = subprocess.Popen(
            config['argv'], executable=config['executable'], cwd=config['cwd'],
            env=config['env'], close_fds=True,
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        _write_event(status_descriptor, {'schema': SCHEMA, 'event': 'error',
                                         'reason': 'process start failed', 'detail': str(error)})
        return 125

    _write_event(status_descriptor, {
        'schema': SCHEMA, 'event': 'started', 'guardian_pid': os.getpid(),
        'process_group': group, 'trial_pid': process.pid,
    })
    while True:
        code = process.poll()
        if code is not None:
            _write_event(status_descriptor, {'schema': SCHEMA, 'event': 'completed',
                                             'returncode': code})
            return 0
        readable, _, _ = select.select([control_descriptor], [], [], .05)
        if readable:
            # No process receives the write end. EOF therefore means that the
            # caller exited, was killed, or deliberately requested cleanup.
            if not os.read(control_descriptor, 1):
                os.killpg(group, signal.SIGKILL)
                return 125


class SupervisedProcess:
    """A child command mediated by a parent-death guardian process group."""

    def __init__(self, guardian, control_descriptor, status_descriptor, events,
                 command, process_group, trial_pid):
        self.guardian = guardian
        self._control_descriptor = control_descriptor
        self._status_descriptor = status_descriptor
        self._events = events
        self.command = command
        self.process_group = process_group
        self.trial_pid = trial_pid
        self.returncode = None

    @classmethod
    def start(cls, command, *, executable, cwd, stdout, stderr, env,
              startup_timeout=STARTUP_TIMEOUT):
        if os.name != 'posix':
            raise OSError('process supervision requires POSIX process groups')
        control_read, control_write = os.pipe()
        config_read, config_write = os.pipe()
        status_read, status_write = os.pipe()
        guardian = None
        guardian_source = None
        try:
            descriptor, guardian_source = tempfile.mkstemp(prefix='.process-supervisor-',
                                                           suffix='.py', dir=cwd)
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(IMPLEMENTATION_BYTES); stream.flush(); os.fsync(stream.fileno())
            guardian = subprocess.Popen(
                [sys.executable, '-I', '-S', guardian_source,
                 '--guardian', str(control_read), str(config_read), str(status_write)],
                pass_fds=(control_read, config_read, status_write),
                stdin=None, stdout=stdout, stderr=stderr, start_new_session=True,
                close_fds=True,
            )
            os.close(control_read); control_read = -1
            os.close(config_read); config_read = -1
            os.close(status_write); status_write = -1
            config = json.dumps({
                'schema': SCHEMA, 'argv': list(command), 'executable': str(executable),
                'cwd': str(cwd), 'env': dict(env),
            }, sort_keys=True).encode('utf-8')
            with os.fdopen(config_write, 'wb') as stream:
                config_write = -1
                stream.write(config)
            event, remainder = _read_event(status_read, b'', startup_timeout)
            if event is None:
                raise SupervisionError('guardian exited before starting the trial')
            if event.get('schema') != SCHEMA or event.get('event') != 'started':
                detail = event.get('detail') if isinstance(event, dict) else None
                raise OSError(detail or 'process start failed')
            group = event.get('process_group')
            trial_pid = event.get('trial_pid')
            if (type(group) is not int or group != guardian.pid
                    or type(trial_pid) is not int or trial_pid <= 0
                    or os.getpgid(guardian.pid) != group):
                raise SupervisionError('guardian process-group ownership check failed')
            os.unlink(guardian_source); guardian_source = None
            result = cls(guardian, control_write, status_read, remainder, command,
                         group, trial_pid)
            control_write = -1; status_read = -1
            return result
        except BaseException:
            if guardian is not None:
                _terminate_owned_group(guardian, guardian.pid, None)
            raise
        finally:
            if guardian_source is not None:
                try:
                    os.unlink(guardian_source)
                except FileNotFoundError:
                    pass
            for descriptor in (control_read, control_write, config_read, config_write,
                               status_read, status_write):
                if descriptor >= 0:
                    os.close(descriptor)

    def wait(self, timeout=None):
        try:
            self.guardian.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            raise subprocess.TimeoutExpired(self.command, timeout) from None
        events = self._drain_events()
        completed = [event for event in events
                     if event.get('schema') == SCHEMA and event.get('event') == 'completed']
        if len(completed) != 1 or type(completed[0].get('returncode')) is not int:
            raise SupervisionError('guardian exited without one completed child status')
        self.returncode = completed[0]['returncode']
        return self.returncode

    def terminate(self):
        self._close_control()
        _terminate_owned_group(self.guardian, self.process_group, self.trial_pid)
        self._close_status()

    def _drain_events(self):
        payload = self._events
        self._events = b''
        while True:
            chunk = os.read(self._status_descriptor, 4096)
            if not chunk:
                break
            payload += chunk
        events = []
        for line in payload.splitlines():
            try:
                event = json.loads(line.decode('utf-8'))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise SupervisionError(f'invalid guardian status: {error}') from error
            if not isinstance(event, dict):
                raise SupervisionError('invalid guardian status object')
            events.append(event)
        return events

    def _close_control(self):
        if self._control_descriptor is not None:
            os.close(self._control_descriptor)
            self._control_descriptor = None

    def _close_status(self):
        if self._status_descriptor is not None:
            os.close(self._status_descriptor)
            self._status_descriptor = None


def _read_event(descriptor, initial, timeout):
    payload = initial
    deadline = time.monotonic() + timeout
    while b'\n' not in payload:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([descriptor], [], [], remaining)[0]:
            raise SupervisionError('guardian did not start within the bounded timeout')
        chunk = os.read(descriptor, 4096)
        if not chunk:
            return None, payload
        payload += chunk
    line, remainder = payload.split(b'\n', 1)
    try:
        event = json.loads(line.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SupervisionError(f'invalid guardian status: {error}') from error
    return event, remainder


def _terminate_owned_group(guardian, process_group, trial_pid):
    """Bound cleanup to a group whose original guardian or trial still owns it."""
    if guardian.poll() is not None:
        try:
            owned = trial_pid is not None and os.getpgid(trial_pid) == process_group
        except ProcessLookupError:
            return
    else:
        try:
            owned = os.getpgid(guardian.pid) == process_group == guardian.pid
        except ProcessLookupError:
            return
    if not owned:
        raise SupervisionError('refusing to signal a process group without ownership')
    try:
        os.killpg(process_group, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        guardian.wait(timeout=TERMINATION_GRACE)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        guardian.wait(timeout=TERMINATION_TIMEOUT)
    except subprocess.TimeoutExpired as error:
        raise SupervisionError('owned process group did not terminate within the bound') from error


def _main(argv):
    if len(argv) != 5 or argv[1] != '--guardian':
        raise SystemExit('internal process guardian; do not invoke directly')
    try:
        descriptors = [int(value) for value in argv[2:]]
    except ValueError:
        raise SystemExit('invalid guardian descriptors') from None
    return _guardian(*descriptors)


if __name__ == '__main__':
    raise SystemExit(_main(sys.argv))
