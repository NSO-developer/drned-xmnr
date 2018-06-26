## Tox/pytest testing

The directory `unit` contains tests that do not require DrNED to be installed
and do not start NSO; they require NSO and in particular its Python API to be
installed though (FIXME: this dependency is planned to be removed).

The tests are not actual unit tests, they try to test the code end-to-end, but
with as few external dependencies as possible.  In particular, they use `mock`
and `pyfakefs` modules to mock NSO libraries or system calls.  As a result, no
NSO instance is started or needs to be running, no device or device simulator
is required, and the filesystem is not changed.

### Using tox

You can run tests using [tox](https://pypi.org/project/tox/); for that you need
to have `tox` itself, and an NSO installation pointed to by `NCS_DIR`.  Also,
the project must have been compiled (namely, the generated Python namespace
module needs to exist).

```
$ tox
... (some output)
  py27: commands succeeded
  py36: commands succeeded
  congratulations :)
$ 
```

### Using pytest alone

You can use `pytest` directly and select only a subset of tests.  All
requirements are in `requirements.txt`, so you can do

```
$ pip install -r requirements.txt
```

- this should install everything that is needed.  Apart from that, your
PYTHONPATH should point to NSO Python API and to the code itself, e.g.

```
$ export PYTHONPATH=$NCS_DIR/ncs/src/ncs/pyapi:../../python
$ pytest
...
$ pytest -v -k test_filter
...
$
```

## Lux testing

The directory `lux` contains one test case that tries to verify that basic
integration with NSO and DrNED works.  The prerequisites are:

 * DrNED must be installed and the environment variable `DRNED` points to the
   installation directory
 * `PYTHONPATH` must point to NSO Python API
 * several additional Python packages need to be installed, see
   `requirements.txt`

When this is set correctly, run

```
$ lux basic.lux
...
successful        : 1
summary           : SUCCESS
...
$
```
