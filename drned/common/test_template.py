from distutils.version import LooseVersion
import drned
import pytest
import glob
import os
import shutil
import re
import common.test_common as common

# NOTE: Due to a py.test bug, strings with hyphens are not allowed in
# parameters. The template fixture will therefore translate all hyphens
# to tildes in filenames, and the test function will then translate back.

def test_template_raw(device_raw, template, op):
    """Configurable test with template file.

    The rollback[+-no] operation specifies an index in a list of all
    commits that have been performed in this function. This means that
    rollback-1 will undo the last commit, rollback+0 will undo all
    commits, etc.

    The operations to perform can also be specified either in the
    template file itself, or in a .load file (see Device.load). An
    example of the template file syntax:

    !op=(load,commit)

    This test is using the device_raw fixture, which means that the
    device state is not restored after test.

    Args:
        device_raw: device fixture
        template: name of the template file
        op[0..n]: operations to be performed:
            "":             no-op
            load:           load file
            commit:         commit configuration
            compare-config: compare configuration
            check-sync:     check that device is in sync
            rollback[+-no]: rollback configuration
            Default: ["load", "commit", "compare-config"]
    Returns:
        nothing

    """
    if op == None:
        op = ["load", "commit", "compare-config"]
    _drned_single_file(device_raw, template, op)

def test_template_single(device, template, op):
    """Normal test with template file.

    The rollback[+-no] operation specifies an index in a list of all
    commits that have been performed in this function. This means that
    rollback-1 will undo the last commit, rollback+0 will undo all
    commits, etc.

    The operations to perform can also be specified either in the
    template file itself, or in a .load file (see Device.load). An
    example of the template file syntax:

    !op=(load,commit)

    This test is using the device fixture, which means that the device
    state is restored after test.

    Args:
        device: device fixture
        template: name of the template file
        op[0..n]: operations to be performed:
            "":             no-op
            load:           load file
            commit:         commit configuration
            compare-config: compare configuration
            check-sync:     check that device is in sync
            rollback[+-no]: rollback configuration
            Default: ["load", "commit", "compare-config",
                      "rollback", "commit", "compare-config"]
    Returns:
        nothing

    """
    if op == None:
        op = ["load", "commit", "compare-config",
              "rollback", "commit", "compare-config"]
    device.save("drned-work/before-test.cfg")
    src,_,_ = _drned_single_file(device, template, op)
    device.save("drned-work/after-test.cfg")
    if not src and not common.filecmp("drned-work/before-test.cfg",
                                      "drned-work/after-test.cfg"):
        pytest.fail("The state after rollback differs from before load. " +
                    "Please check before-test.cfg and after-test.cfg")

def test_template_set(device, init, fname, init_op, op, end_op):
    """Normal test of template file set, defined by naming convention:

    first_set:0.txt
    first_set:1.txt
    second_set:0.txt
    second_set:1.txt

    The file list above will create the following tests:
    - load first_set:0.txt, commit, compare-config
    - load first_set:1.txt, commit, compare-config
    - rollback first_set:1.txt, commit, compare-config
    - rollback first_set:0.txt, commit, compare-config
    - load second_set:0.txt, commit, compare-config
    - load second_set:1.txt, commit, compare-config
    - rollback second_set:1.txt, commit, compare-config
    - rollback second_set:0.txt, commit, compare-config

    The rollback[+-no] operation specifies an index in a list of all
    commits that have been performed in this function. This means that
    rollback-1 will undo the last commit, rollback+0 will undo all
    commits, etc.

    The operations to perform can also be specified either in the
    template file itself, or in a .load file (see Device.load). An
    example of the template file syntax:

    !op=(load,commit)
    !end-op=(compare-config)

    This test is using the device fixture, which means that the device
    state is restored after test.

    Args:
        device: device fixture
        init[0..n]: name of the init files to load before the test begins
            Please see the Device.rload() method for additional info
        fname[0..n]: name of the template files, wildcards allowed
        init_op[0..n]: operations to be performed on each init file
            Default: ["load", "commit", "compare-config"]
        op[0..n]: operations to be performed on each single file
            Default: ["load", "commit", "compare-config"]
        end_op[0..n]: operations to be performed in the end of each set
            Default: ["rollback", "commit", "compare-config"],
            repeated until all commits are rolled back
        The operations are:
            "":             no-op
            load:           load file
            commit:         commit configuration
            compare-config: compare configuration
            check-sync:     check that device is in sync
            rollback[+-no]: rollback configuration
    Returns:
        nothing
    """
    _drned_single_set(device, init, fname, init_op, op, end_op, 1)

def test_template_union(device, init, fname, init_op, iteration):
    """Test of all combinations of file sets.

    This test is using the device fixture, which means that the device
    state is restored after test.

    Args:
        device: device fixture
        init[0..n]: name of the init files to load before the test begins
            Please see the Device.rload() method for additional info
        fname[0..n]: name of the template files, wildcards allowed
        init_op[0..n]: operations to be performed on each init file
            Default: ["load", "commit", "compare-config"]
        iteration: list of iterations to run, (--iteration fixture param)
    Returns:
        nothing

    Iteration 1: Commit after each file, ascending order
    Iteration 2: Commit after each file, descending order
    Iteration 3: Commit after each set, ascending order
    Iteration 4: Commit after each set, descending order
    Iteration 5: Commit after all sets, ascending order
    Iteration 6: Commit after all sets, descending order
    """
    for it in range(1, 7):
        if iteration == None or it in iteration:
            if it in [1, 2]:
                # Commit after each file
                op = ["load", "commit", "compare-config"]
                end_op = []
            elif it in [3, 4]:
                # Commit after each set
                op = ["load"]
                end_op = ["commit", "compare-config"]
            elif it in [5, 6]:
                # Commit in the end
                op = ["load"]
                end_op = []
            # Load the entire collection of sets
            commit_id_base = len(device.commit_id)
            _drned_single_set(device, init, fname, init_op, op, end_op, it)
            # Final commit
            if it in [5, 6]:
                device.commit_compare(dry_run=False)
            # Single rollback to start
            device.rollback_compare(device.commit_id[commit_id_base],
                                    dry_run=False)
            # Rollback to end, and then incrementally to start again
            for i in reversed(range(commit_id_base, len(device.commit_id))):
                device.rollback_compare(id=device.commit_id[i], dry_run=False)

# Test single set
def _drned_single_set(device, init, fname, init_op, op, end_op, it):
    src_in_set = False
    device.save("drned-work/before-test.cfg")
    # Load init files
    init_id_start = len(device.commit_id)
    if init != None:
        if init_op == None:
            init_op = ["load", "commit", "compare-config"]
        for init_file in init:
            src,_,_ = _drned_single_file(device, init_file, init_op)
            src_in_set = src_in_set or src
    init_id_stop = len(device.commit_id)
    # Must at least have one file
    if not fname:
        pytest.fail("Please specify a file with the --fname option")
    # Divide in sets
    tsets = sorted(list(set([re.sub(":[^\.]*", ":*", f) for f in fname])))
    if not it % 2:
        tsets = reversed(tsets)
    if op == None:
        op = ["load", "commit", "compare-config"]
    pinit = " --init=" + " --init=".join(init) if init else ""
    piop = " --init-op=" + " --init-op=".join(init_op) if init_op else ""
    pop = " --op=" + " --op=".join(op) if op else ""
    peop = " --end-op=" + " --end-op=".join(end_op) if end_op else ""
    # Loop for sets
    for tset in tsets:
        device.trace("\npy.test -k test_template_set%s " % (pinit) +
                     "--fname=%s%s%s%s --device=%s\n" %
                     (tset, piop, pop, peop, device.name))
        commit_id_base = len(device.commit_id)
        tset_files = sorted(glob.glob(tset))
        set_all_operation = True
        # Use upper scheme as default
        the_end = end_op
        for tset_file in tset_files:
            src,eop,sop = _drned_single_file(device, tset_file, op)
            src_in_set = src_in_set or src
            set_all_operation = set_all_operation and sop
            # Get end operations from file, if present
            if eop:
                # File operations override
                the_end = eop
        if the_end == None:
            # Default action is to first rollback to start, then to
            # end, then rollback all commits, one by one
            if set_all_operation:
                the_end = ["rollback+0", "commit", "compare-config"]
                extra_rollback = 1
            else:
                the_end = []
                extra_rollback = 0
            for i in reversed(range(commit_id_base, len(device.commit_id) + extra_rollback)):
                the_end += ["rollback+%d" % (i - commit_id_base), "commit", "compare-config"]
        # Use the file function also for rollbacks
        _drned_single_file(device, None, the_end,
                           commit_id_base=commit_id_base)
    # Rollback init files
    for i in reversed(range(init_id_start, init_id_stop)):
        device.rollback_compare(id=device.commit_id[i], dry_run=False)
    # Check that we're back
    device.save("drned-work/after-test.cfg")
    if not src_in_set and end_op == None \
       and not common.filecmp("drned-work/before-test.cfg",
                              "drned-work/after-test.cfg"):
        pytest.fail("The state after rollback differs from before load. " +
                    "Please check before-test.cfg and after-test.cfg")

# Test single file
ctype = None
def _drned_single_file(device, name, op, commit_id_base=None):
    global ctype
    name = name.replace("~", "-") if name else name
    if name and name.endswith(".src"):
        # Source file directly in the NCS CLI
        device.source(name, prompt="[^ ]# ", banner=False, rename_device=True)
        return True,None,False
    if commit_id_base == None:
        commit_id_base = len(device.commit_id)
    # Default set of operations
    if op == None:
        op = ["load", "commit", "compare-config",
              "rollback", "commit", "compare-config"]
    end_op = None
    set_op = True
    # Check if operations specified in .load file
    if name and os.path.isfile(name + ".load"):
        with open (name + ".load", "r") as f:
            contents = f.read()
            reg_op = r"^\s*operations\s*=\s*(\S*)"
            reg_end = r"^\s*end-operations\s*=\s*(\S*)"
            reg_ver = r"^\s*ncs-min-version\s*=\s*(\S*)"
            reg_set = r"^\s*set-all-operation\s*=\s*(\S*)"
            file_op = re.search(reg_op, contents, re.MULTILINE)
            file_end = re.search(reg_end, contents, re.MULTILINE)
            min_ver = re.search(reg_ver, contents, re.MULTILINE)
            set_all = re.search(reg_set, contents, re.MULTILINE)
            if file_op:
                print("Using operations from .load file: %s" %
                      re.sub("\\s+", "", file_op.group(1)))
                op = [o.strip() for o in file_op.group(1).split(",")]
            if file_end:
                print("Using end operations from .load file: %s" %
                      re.sub("\\s+", "", file_end.group(1)))
                end_op = [o.strip() for o in file_end.group(1).split(",")]
            if min_ver:
                def major(ver):
                    return ".".join(ver.split(".")[:2])
                myver = device.version.split("_")[0]
                ver = [v.strip() for v in min_ver.group(1).split(",")]
                present = False
                for v in ver:
                    if major(v) == major(myver):
                        present = True
                        if LooseVersion(v) > LooseVersion(myver):
                            print("NOTE: File %s not supported in NSO %s, requires %s" %
                                  (name, myver, v))
                            return False,None,False
                else:
                    # Skip if gap in min-version
                    if not present and major(myver) < major(ver[-1]):
                        print("NOTE: File %s not supported in NSO %s, requires %s" %
                              (name, myver, ver[-1]))
            if set_all and set_all.group(1).lower() in ["false", "no"]:
                set_op = False
                print("Using set-all-operation from .load file: %s" % set_op)
    # Check if operations specified in file
    if name:
        with open (name, "r") as f:
            contents = f.read()
            reg_op = r"^\s*!\s*op\s*=\s*\(\s*([^\)]*)\s*\)"
            reg_end = r"^\s*!\s*end-op\s*=\s*\(\s*([^\)]*)\s*\)"
            file_op = re.search(reg_op, contents, re.MULTILINE)
            file_end = re.search(reg_end, contents, re.MULTILINE)
            if file_op:
                print("Using operations from file: %s" %
                      re.sub("\\s+", "", file_op.group(1)))
                op = [o.strip() for o in file_op.group(1).split(",")]
            if file_end:
                print("Using end operations from file: %s" %
                      re.sub("\\s+", "", file_end.group(1)))
                end_op = [o.strip() for o in file_end.group(1).split(",")]
    # Run all operations
    for o in op:
        if o == "":
            pass
        elif o == "load":
            ctype = "load"
            _drned_template_load(device, name)
        elif o == "commit":
            try:
                # May cause confusion if present from old run
                os.remove("drned-work/drned-rollback.txt")
            except OSError:
                pass
            device.commit(show_dry_run=True)
            shutil.copyfile("drned-work/drned-dry-run.txt",
                            "drned-work/drned-%s.txt" % ctype)
        elif o == "compare-config":
            device.compare_config()
        elif o == "check-sync":
            device.check_sync()
        elif o.startswith("rollback"):
            ctype = "rollback"
            if o == "rollback":
                device.rollback()
            else:
                cid = int(o.replace("rollback", ""))
                cid = cid if cid < 0 else commit_id_base + cid
                device.rollback(device.commit_id_next(cid))
    return False,end_op,set_op

# Load template
def _drned_template_load(device, template, fail_on_errors=True):
    fname = template.replace("~", "-")
    if fname.endswith(".xml"):
        device.load(fname, rename_device=True, fail_on_errors=fail_on_errors)
    else:
        device.rload(fname, remove_device=True, fail_on_errors=fail_on_errors)

