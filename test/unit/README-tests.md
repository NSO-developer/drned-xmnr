# DrNED-XMNR unit tests

This directory contains a set of XMNR's "unit tests".  They are "unit" not in
the sense that every test tests a single Python function; every test tests a
limited functionality and in particular, no test starts NSO or a netsim
device.  As a result, these tests are much, much faster than Lux tests in `../lux/`,
but they can test only a certain subset of functionality and sometimes need a
lot of mock objects to be passed to the XMNR code.

Also, even though they do not start or really need NSO, they still need the NSO
PyAPI - the primary reason is that the tests import XMNR Python modules which
in turn import NSO Python modules.  This has some consequences:

* when running tests, NSO PyAPI needs to be on `$PYTHONPATH`;
* when running the unit tests with Python 2, the NSO release must be 5.3.x or
  older, since 5.4 and newer releases do not come with Python 2 PyAPI.

It should be possible to eliminate this dependency through some more mocking
and patching, but this has not been attempted yet.


## How to run tests

There are two possible ways how unit tests can be run: the complete test suite
(possibly in several Python environments) can be run using tox, or subset of
tests or individual tests can be run with PyTest.


### Using tox

[tox](https://tox.readthedocs.io/en/latest/) is a tool that can be used - among
other - to simplify running tests in different Python environment; here it is
used to run the unit tests in Python version 2.7, 3.6, and 3.8.

You can use it either as it is, i.e. `tox`, or with given Python version, such
as `tox -e py38`.  In either case, you of course need the tool to be installed
(available as a Linux distro package or as a PyPI package), and you need the
required Python versions to be available.  So for instance if you instruct tox
to use Python 3.6, you need to have it installed (most likely Python 3.6 is not
installed on your system by default) and have the command `python3.6` on your
PATH.

Tox takes care of everything else: it reads its configuration from `tox.ini`,
creates a Python virtual environment with all necessary Python packages (as
told in `requirements.txt`) and runs pytest on the complete test suite.


### Using pytest directly

Tox starts pytest to do actual testing, but with some setup pytest can be run
directly:

* make sure your python environment contains everything mentioned in
  `requirements.txt`:

      pip install -r requirements.txt

* add NCS PyAPI and XMNR sources to `$PYTHONPATH`:

      export PYTHONPATH=$NCS_DIR/src/ncs/pyapi:../../python:../../drned-skeleton

Now run pytest - see its documentation for full command line options, most
common form may look like

```
$ pytest -v -s -k <pattern> <filenames>
```

This would run all test in all `<filenames>` such that the test name matches
`<pattern>`.


## Sanity check tests

* module: `test_check`
* patches: import routines, version info
* runs: `XmnrCheck.startup()`
* args: none
* expects: pased / raised an exception depending on the patches

The NSO package XMNR should refuse to start if package prerequisites are not
met and successfully starts otherwise.  These prerequisite checks are done in
`XmnrCheck.startup`; this method should raise an exception if the running
Python version is not supported, or a required package is missing, or the
package `pytest` has old version.

The suite `test_check` contains only one class with four tests that verify just
this - tree tests expect the method to raise an exception because of broken
prerequisites, the fourth one expects it to succeed.

The failure tests need to tweak the environment before the test.  They use
pytest's fixture mechanism.  The three fixtures used by the tests either modify
`sys.version_info` or through patching `import_module` function pretend
unavailable or incorrect `pytest` package version for the duration of the test.


## Filter tests

* module: `test_filtering`
* patches: none
* runs: `filtering.run_test_filter()`
* args: filtering routine, prepared DrNED output file
* expects: filter output matches prepared filtered output file

Filter tests verify the DrNED output filtering routines.  The mechanism of
these tests is fairly straightforward: there is one test class for each of the
three filter types (transition, walk, explore), and every class has several
test methods.  The classes have a static method `filter` that start the
corresponding filtering mechanism; each of the test methods refers to set of
three files:

* `<file>.log`: DrNED output, either from an actual test run or containing only
  important parts of the output;
* `<file>.log.dr`: expected output in the mode `drned-overview`;
* `<file>.log.ov`: expected output in the mode `overview'.

Every test runs the filter against the `.log` file in the two modes and
compares the output with the expectation.


## CLI2NETCONF tests

* module: `test_cli2netconf`
* patches: `cli2netconf.Devcli` and `device.Device` instances
* runs: `cli2netconf.cli2netconf()`
* args: mock device names, list of file names
* expects: correct sequence of calls to the `Devcli`/`Device` mock, correct
  sequence of message output

The suite contains only one test class with four test methods.  They all test
whether the function `cli2netconf.cli2netconf` when invoked with given set of
files to convert causes expected functions of a `Devcli` and `Device` classes
to be called.

The two classes are mocked so that all calls are captured.  Also, when the mock
is initialized, it is provided with a list of file names, that should fail when
they are loaded, and another list of names, that should fail when the
configuration is synchronized from the "device".  This is used later during the
test run and again when comparing expected and actual calls and messages.

TODO: it remains to test whether the Devcli methods lead to correct calls on
a device driver.


## Action tests

* module: `test_actions`
* patches: filesystem, several OS-layer functions, most of PyAPI functions
* runs: most of the tests run `action.action_cb` with some setup, sometimes a
  bit more complex
* args: standard action arguments
* expects: typically that the action succeeds (or fails), plus some call
  checks, output, etc.


### Patching and `mocklib`

Tests in this suite verify that a XMNR action, when invoked with given
arguments and in given environment, has expected results, such as that certain
low-level calls are invoked, expected files appear on the filesystem, etc.  For
this to work a lot of patching needs to be done.

Every test function is decorated with `@xtest_patch` and accepts one argument,
a patch object, an instance of the class `mocklib.XtestPatch`.  The instance
has two important attributes:

* `xpatch.system` - instance of `mocklib.SystemMock`; when the instance is
  being created, several system calls are patched (such as `socket.socket` or
  `subprocess.Popen`), and filesystem calls are patched using `pyfakefs`.  All
  patches created here are available in test runtime using instance attributes.

* `xpatch.ncs` - instance of `mocklib.XtestMock` that refers to mocks of
  several NCS PyAPI classes and functions, including `ncs.maapi.Maapi`, several
  `maagic` objects and few low-level API functions that are used by DrNED-XMNR
  code.

These objects are used for multiple purposes:

* obviously, to mock calls to the system or to NCS so that the tests can be run
  without a running NCS instance or without affecting the filesystem;

* to check whether certain calls happen in the correct order, with correct
  arguments and so on;

* to insert prepared data so that when a mocked low-level API is called by the
  code under test, the data is returned.

An examples of the last item are `proc_stream` and `socket_stream` attributes
of the system mock, both instances of the class `StreamData` which is used for
inserting data to be returned from `Popen`-ed process' standard output and from
socket communication when doing `confd_save_config` respectively.


### Debugging

When a test starts failing, it is rarely immediately obvious where the problem
is.  The following might help to get better insight into what is going on:

* Increase `pytest` verbosity level by adding more `-v` options to the command
  line.  `tox` also accepts this option(s), but it affects only the package
  installation phase.

* You can always add `print` calls to the code (test or under-test), but make
  sure you are running `pytest` with `-s` so that `pytest` does not capture the
  standard output.

* Normally, there are quite a few log outputs into NSO's log.  NSO is not
  started for unit tests, but the log is mocked and redirected to
  `/tmp/unit.log`.
