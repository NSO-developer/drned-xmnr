import inspect
import os
import pytest
import re
import shutil
import tempfile
import types
import common.test_common as common

DRY_RUN = False

def _done():
    raise StopIteration

class Xstr(str):
    """Extended string class for the drned_load and drned_rollback
    parameters.
    """
    def xindex(self, tokens, closure="exit", first=False):
        """Return index of multi-line string.

        The drned_load or drned_rollback parameters sometimes contain
        many copies of identical strings. Creating a regex that
        matches correctly can be a true challenge, and this extension
        to index() may come in handy.

        Note that the indent of the first token is ignored, but the
        indent of the following tokens is added to the actual indent
        of the first token matched.  See example below.

        Args:
            tokens: list of tokens to match
            closure: token that ends closure, default: "exit"
            first: return index of string start, else string end
        Returns:
            string index
        Example:
            lambda p: (p.drned_rollback.xindex(["mpls",
                       " interface tun-izcore-7750-2-1",
                       "  no admin-group be"]) <
               p.drned_rollback.xindex(["mpls",
                       " no interface tun-izcore-7750-2-1"]) <
               p.drned_rollback.xindex(["mpls",
                       " no admin-group be"]))

        """
        # First token accepts any indent
        regex = r"^( *)(?!^\1%s)%s" % (closure, tokens[0])
        for token in tokens[1:]:
            # Get token indent
            indent = re.search("^ *", token).end()
            # Add regex for token
            regex += r"(?!^\1%s%s).*^\1%s" % (indent * " ", closure, token)
        m = re.search(regex, self, re.MULTILINE|re.DOTALL)
        if not m:
            pytest.fail("No match for %s, regex \"%s\"" % (tokens, regex))
        return m.start() if first else m.end()

class Xrollback(object):
    """Extended rollback class to be able to fine-tune rollbacks.

    Example:
        # Create instance
        rb = common.Xrollback()
        # The testcase
        config["test_selective_rollback"] = [
            lambda p: rb.set_start(p),
            "leaflist-in-list first-1 second-1",
            "leaflist-in-list first-1 second-2",
            "leaflist-in-list first-2 second-1",
            "leaflist-in-list first-2 second-2",
            "leaflist-in-list first-3 second-1",
            "leaflist-in-list first-3 second-2",
            lambda p: rb.set_stop(p),
            # Rollback the two last lines
            lambda p: rb.rollback_all(p, -2),
            # Rollback to 2nd line
            lambda p: rb.rollback_all(p, 2),
            # Rollback to start
            lambda p: rb.rollback(p, 0),
            lambda p: p.done()
        ]
    """
    def __init__(self):
        self.start = None
        self.stop = None

    def set_start(self, p):
        self.start = len(p.device.commit_id)
        self.stop = None
        print("Rollback start set to %d" % self.start)
        return True

    def set_stop(self, p):
        assert self.start
        self.stop = len(p.device.commit_id)
        print("Rollback stop set to %d" % self.stop)
        return True

    def rollback(self, p, value):
        assert self.start
        assert self.stop
        id = p.device.commit_id[self.start:self.stop]
        print("Rollback %d (%s)" % (value, id[value]))
        p.device.rollback_compare(id[value])
        return True

    def rollback_all(self, p, value):
        assert self.start
        assert self.stop
        if value >= 0:
            values = range(self.start + value, self.stop)
        else:
            values = range(self.stop + value, self.stop)
        print values
        for i in reversed(values):
            self.rollback(p, i - self.start)
        return True

class Settings(object):
    def __init__(self):
        self.restore_data = {}

    def set_value(self, obj, attr, value):
        if obj:
            # Save for later restore
            if not attr in self.restore_data:
                self.restore_data[attr] = (obj, getattr(obj, attr))
            # Set value
            setattr(obj, attr, value)
            # Call possible set hook
            if hasattr(obj, "sethook_" + attr):
                getattr(obj, "sethook_" + attr)(value)
        return True

    def restore_value(self, attr):
        # Restore
        (obj, value) = self.restore_data[attr]
        setattr(obj, attr, value)
        # Call possible set hook
        if hasattr(obj, "sethook_" + attr):
            getattr(obj, "sethook_" + attr)(value)
        return True

    def restore_all(self):
        for attr in self.restore_data.keys():
            self.restore_value(attr)

class Parameter(object):
    def __init__(self, device=None, settings=None,
                 drned_load=None, drned_rollback=None):
        self.device = device
        self.settings = settings
        self.drned_load = Xstr(drned_load)
        self.drned_rollback = Xstr(drned_rollback)
        self.done = _done

def test_here_single(device, config, name, usrparam=None, dry_run=DRY_RUN):
    """Test a configuration sequence.

    Args:
        device: device fixture
        config[]: map of all config chunks:
            config[n][0]: first part of config chunk
            config[n][1]: second part of config chunk
            config[n][n]: last part of config chunk
        name: name of config chunk to run
    Returns:
        nothing

    Given the input ["set A 1
                      set A 2",
                     "set B 1
                      set B 2"]
    the test will run the following CLI commands:
        (a)
        set A 1
        set A 2  # commit - compare
        (b)
        set B 1
        set B 2  # commit - compare
        (c)
        rollback to (a) - compare
        rollback to (c) - compare
        rollback to (b) - compare
        rollback to (a) - compare
    """
    device.save("drned-work/before-test.cfg")
    commit_id_base = len(device.commit_id)
    # Handle all chunks
    settings = Settings()
    try:
        try:
            for i,conf in enumerate(config[name]):
                _chunk_part(device, i, name, conf, usrparam=usrparam,
                            settings=settings, dry_run=dry_run,
                            operations=["load", "commit", "compare-config"])
        except StopIteration:
            device.sync_from()
            rollback_to_start(device, commit_id_base, dry_run)
        except:
            rollback_to_start(device, commit_id_base, dry_run)
            raise
        else:
            rollback_to_start(device, commit_id_base, dry_run)
            # Rollback to end, and then incrementally to start again
            for i in reversed(range(commit_id_base, len(device.commit_id))):
                device.rollback_compare(id=device.commit_id[i], dry_run=dry_run)
    finally:
        settings.restore_all()
        # Test that we're back
        device.save("drned-work/after-test.cfg")
        if not common.filecmp("drned-work/before-test.cfg",
                              "drned-work/after-test.cfg"):
            pytest.fail("The state after rollback differs from before load. " +
                        "Please check before-test.cfg and after-test.cfg")

def test_here_union(device, config, iteration=range(1, 7), dry_run=DRY_RUN):
    """Test different sequences of commands as a union.

    Args:
        device: device fixture
        config[]: map of all config chunks:
            config[n][0]: first part of config chunk
            config[n][1]: second part of config chunk
            config[n][n]: last part of config chunk
        iteration: list of iterations to run, (--iteration fixture param)
    Returns:
        nothing

    Iteration 1: Commit after each chunk part, ascending order
    Iteration 2: Commit after each chunk part, descending order
    Iteration 3: Commit after each chunk, ascending order
    Iteration 4: Commit after each chunk, descending order
    Iteration 5: Commit after all chunks, ascending order
    Iteration 6: Commit after all chunks, descending order
    """

    # Loop for all iterations
    for it in range(1, 7):
        if it in iteration:
            device.trace("\npy.test -k test_here_union --iteration=%d\n" % it)
            _here_union(device, config, it, dry_run=dry_run)

def _here_union(device, config, it, dry_run=False):
    device.save("drned-work/before-test.cfg")
    names = sorted(config.keys())
    if it in [2, 4, 6]:
        names = reversed(names)
    commit_id_base = len(device.commit_id)
    settings = Settings()
    try:
        try:
            for name in names:
                device.trace("\npy.test -k 'test_here_single[%s]'\n" % name)
                # Commit loop
                for i,conf in enumerate(config[name]):
                    if it in [1, 2]:
                        operations=["load", "commit", "compare-config"]
                    else:
                        operations=["load"]
                    _chunk_part(device, i, name, conf,
                                settings=settings, dry_run=dry_run,
                                operations=operations, do_functions=False)
                if it in [3, 4]:
                    device.commit_compare(dry_run=dry_run)
            if it in [5, 6]:
                device.commit_compare(dry_run=dry_run)
        except StopIteration:
            device.sync_from()
            rollback_to_start(device, commit_id_base, dry_run)
        except:
            rollback_to_start(device, commit_id_base, dry_run)
            raise
        else:
            rollback_to_start(device, commit_id_base, dry_run)
            # Rollback to end, and then incrementally to start again
            for i in reversed(range(commit_id_base, len(device.commit_id))):
                device.rollback_compare(id=device.commit_id[i], dry_run=dry_run)
    finally:
        settings.restore_all()
        # Test that we're back
        device.save("drned-work/after-test.cfg")
        if not common.filecmp("drned-work/before-test.cfg",
                              "drned-work/after-test.cfg"):
            pytest.fail("The state after rollback differs from before load. " +
                        "Please check before-test.cfg and after-test.cfg")

# Handle part of chunk
def _chunk_part(device, no, name, conf, dry_run=False, operations=None,
                settings=None, usrparam=None, do_functions=True):
    if type(conf) == types.StringType:
        device.trace("\n%s\nPart %d of %s\n%s\n%s\n" %
                   ("#" * 30, no, name, conf.strip(), "#" * 30))
        _chunk_part_string(device, conf, dry_run=dry_run,
                           operations=operations)
    elif type(conf) == types.FunctionType and do_functions:
        if hasattr(conf, "pretty"):
            desc = conf.pretty
        else:
            desc = inspect.getsource(conf).strip()
        device.trace("\n%s\nPart %d of %s\n%s\n%s\n" %
                   ("#" * 30, no, name, desc, "#" * 30))
        _chunk_part_func(device, conf, settings=settings,
                         usrparam=usrparam, dry_run=dry_run)

# Handle function part of chunk
def _chunk_part_func(device, conf, settings=None, usrparam=None, dry_run=False):
    try:
        with open ("drned-work/drned-load.txt", "r") as f:
            drned_load = f.read()
    except IOError:
        drned_load = None
    try:
        with open ("drned-work/drned-rollback.txt", "r") as f:
            drned_rollback = f.read()
    except IOError:
        drned_rollback = None
    # Create parameter chunk
    p = Parameter(device=device,
                  settings=settings,
                  drned_load=drned_load,
                  drned_rollback=drned_rollback)
    # Add user parameters
    if usrparam:
        usrparam(p)
    try:
        e = "lambda expression is false"
        success = conf(p)
    except StopIteration:
        # Pass this exception to be able to abort the test from the
        # lambda function
        raise
    except Exception as e:
        success = False
    if not success:
        pretty = ""
        if hasattr(p, "pretty"):
            pretty = p.pretty(p)
        if hasattr(conf, "pretty"):
            desc = conf.pretty
        else:
            desc = inspect.getsource(conf).strip()
        pytest.fail("%s\n" % e +
                    "%s\n" % desc +
                    "\ndrned_load = \n%s" % p.drned_load +
                    "\ndrned_rollback = \n%s" % p.drned_rollback +
                    "\n\n%s" % pretty)

# Handle string part of chunk
def _chunk_part_string(device, conf, dry_run=False, operations=None):
    # Operations that are given in the file have precedence
    opr = r"^\s*!\s*op\s*=\s*\(\s*([^\)]+)\s*\)"
    op = re.search(opr, conf, re.MULTILINE)
    if op:
        print("Using operations from file: %s" %
              re.sub("\\s+", "", op.group(1)))
        operations = [o.strip() for o in op.group(1).split(",")]
        conf = re.sub(opr, "", conf)
    elif re.search(r"^\s*!\s*op", conf, re.MULTILINE):
        print("NOTE: Possibly malformed operation: %s", conf)
    # Use a local commit ID base for the chunk
    commit_id_base = len(device.commit_id)
    # Loop for operations
    for operation in operations:
        if operation == "":
            pass
        elif operation == "sync-from":
            device.sync_from()
        elif operation == "load":
            ctype = "load"
            _load(device, conf)
        elif operation == "commit":
            try:
                # May cause confusion if present from old run
                os.remove("drned-work/drned-rollback.txt")
            except OSError:
                pass
            # Create commit log
            device.commit(show_dry_run=dry_run)
            shutil.copyfile("drned-work/drned-dry-run.txt",
                            "drned-work/drned-%s.txt" % ctype)
        elif operation == "compare-config":
            device.compare_config()
        elif operation == "check-sync":
            device.check_sync()
        elif operation.startswith("rollback"):
            ctype = "rollback"
            if operation == "rollback":
                device.rollback()
            else:
                i = int(operation.replace("rollback", ""))
                i = i if i < 0 else commit_id_base + i
                device.rollback(device.commit_id_next(i))

# Load configuration by means of file, faster than CLI
def _load(device, conf):
    with tempfile.NamedTemporaryFile(dir="drned-work",
                                     prefix="test-here-",
                                     suffix=".txt",
                                     delete=False) as temp:
        with open(temp.name, "w") as f:
            f.write(conf)
        device.rload(temp.name, banner=False)

def rollback_to_start(device, commit_id_base, dry_run):
    # Single rollback to start
    if len(device.commit_id) > commit_id_base:
        device.rollback_compare(device.commit_id_next(commit_id_base),
                                dry_run=dry_run)
