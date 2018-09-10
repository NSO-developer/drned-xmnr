import pytest

_num = 0

def test_incomplete_single(device, config, name, iteration=[1, 2, 3]):
    """Test different sequences of commands, and verify incomplete input.

    Args:
        device: device fixture
        config[]: map of all config chunks:
            config[n][0]: list of commands to run before each test
            config[n][1]: list of sub-commands to avoid checking
            config[n][2]: list of commands to check
        name: name of config chunk to run
        iteration: list of iterations to run, (--iteration fixture param)
    Returns:
        nothing

    Given the input (["enable something"],
                     ["set B"],
                     ["set A 1"], ["set A 2"], ["set B 1"], ["set B 1"]),
    the test will run the following CLI commands:

    Iteration 1: Test incomplete commands
        enable something
        set A    # verify incomplete input
        set A 1  # commit - compare - rollback - compare
        set A    # verify incomplete input
        set A 2  # commit - compare - rollback - compare
        set B 1  # commit - compare - rollback - compare
        set B 2  # commit - compare - rollback - compare

    Iteration 2: Test individual commits
        enable something
        (a)
        set A 1  # commit - compare
        (b)
        set A 2  # commit - compare
        (c)
        set B 1  # commit - compare
        (d)
        set B 2  # commit - compare
        (e)
        rollback to (a) - compare
        rollback to (e) - compare
        rollback to (d) - compare
        rollback to (c) - compare
        rollback to (b) - compare
        rollback to (a) - compare

    Iteration 3: Test single commit
        enable something
        set A 1
        set A 2
        set B 1
        set B 2  # commit - compare - rollback - compare
    """
    prefix,avoid,lines = config[name]

    # Loop for all iterations
    for it in range(1, 4):
        if it in iteration:
            print("\npy.test -k 'test_incomplete_single[%s]' --iteration=%d\n" %
                  (name, it))
            globals()["_iteration_%d" % it](device, prefix, avoid, lines)

def _iteration_1(device, prefix, avoid, lines):
    global _num
    def reset_to_prefix():
        device.cmd("top")
        device.cmd("devices device %s config" % device.name)
        for p in prefix:
            device.cmd(p)
    for _num,line in enumerate(lines):
        print "\n### Incomplete commands"
        reset_to_prefix()
        pwd_prompt = device.last_prompt
        words = line.split(" ")
        for i in range(len(words)-1):
            # Create incomplete cmd
            incomplete = " ".join(words[:i+1])
            for incomp in incomplete.split("\n"):
                incomp = incomp.strip()
                if incomp != "" and not incomp.startswith("no") \
                   and incomp not in avoid + lines:
                    incomp = incomp.replace("%d", str(_num))
                    try:
                        # Should fail with exception
                        print("admin@ncs(config-drned)# " + incomp)
                        device.cmd(incomp)
                    except pytest.fail.Exception as e:
                        if e.msg.endswith("PROMPT"):
                            # When prompted, the command is incomplete
                            # as expected
                            try:
                                # Get out of prompt, will give an
                                # additional exception
                                device.cmd("\x03~\b", lf=False, echo=False,
                                           prompt="~\b \b")
                            except pytest.fail.Exception as x:
                                pass
                        if device.last_prompt != pwd_prompt:
                            reset_to_prefix()
                    else:
                        pytest.fail("Expected an incomplete path exception "
                                    +"for command: \"%s\"" % incomp)

        # Finally use entire cmd, should succeed
        print "\n### Entire command"
        complete = line.replace("%d", str(_num))
        for comp in complete.split("\n"):
            comp = comp.strip()
            if not comp.startswith("no"):
                print("admin@ncs(config-drned)# " + comp)
                device.cmd(comp)
        device.commit_rollback()

def _iteration_2(device, prefix, avoid, lines):
    global _num
    # All commands in separate commits
    print "\n### All commands, separate commits"
    device.cmd("devices device %s config" % device.name)
    for p in prefix:
        device.cmd(p)
    commit_id = []
    for line in lines:
        complete = line.replace("%d", str(_num))
        for comp in complete.split("\n"):
            comp = comp.strip()
            print("admin@ncs(config-drned)# " + comp)
            device.cmd(comp)
        _num += 1
        device.commit_compare()
        commit_id.append(device.commit_id[-1])
    # Rollback to initial state
    device.rollback_compare(id=commit_id[0])
    # Rollback all commit ids, one by one
    for id in reversed(commit_id):
        device.rollback_compare(id=id)

def _iteration_3(device, prefix, avoid, lines):
    global _num
    # All commands in same commit
    print "\n### All commands, same commit"
    device.cmd("devices device %s config" % device.name)
    for p in prefix:
        device.cmd(p)
    for line in lines:
        complete = line.replace("%d", str(_num))
        for comp in complete.split("\n"):
            comp = comp.strip()
            print("admin@ncs(config-drned)# " + comp)
            device.cmd(comp)
        _num += 1
    device.commit_rollback()

def test_incomplete_union(device, config, iteration=range(1, 7)):
    """Test different sequences of commands as a union.

    Args:
        device: device fixture
        config[]: map of all config chunks:
            config[n][0]: list of commands to run before each test
            config[n][1]: list of sub-commands to avoid checking
            config[n][2]: list of commands to check
        iteration: list of iterations to run, (--iteration fixture param)
    Returns:
        nothing

    Iteration 1: Commit after each line, ascending order
    Iteration 2: Commit after each line, descending order
    Iteration 3: Commit after each chunk, ascending order
    Iteration 4: Commit after each chunk, descending order
    Iteration 5: Commit after all chunks, ascending order
    Iteration 6: Commit after all chunks, descending order
    """

    # Loop for all iterations
    for it in range(1, 7):
        if it in iteration:
            print("\npy.test -k test_incomplete_union --iteration=%d\n" % it)
            _incomplete_union(device, config, it)

def _incomplete_union(device, config, it):
    global _num
    keys = sorted(config.keys())
    if it in [2, 4, 6]:
        keys = reversed(keys)
    commit_id = []
    for k in keys:
        prefix,avoid,lines = config[k]
        device.cmd("devices device %s config" % device.name)
        for p in prefix:
            device.cmd(p)
        for line in lines:
            complete = line.replace("%d", str(_num))
            for comp in complete.split("\n"):
                comp = comp.strip()
                print("admin@ncs(config-drned)# " + comp)
                device.cmd(comp)
            _num += 1
            if it in [1, 2]:
                device.commit_compare()
                commit_id.append(device.commit_id[-1])
        if it in [3, 4]:
            device.commit_compare()
            commit_id.append(device.commit_id[-1])
    if it in [5, 6]:
        device.commit_compare()
        commit_id.append(device.commit_id[-1])
    # Rollback to initial state
    device.rollback_compare(id=commit_id[0])
    commit_id.append(device.commit_id[-1])
    # Rollback all commit ids, one by one
    for id in reversed(commit_id):
        device.rollback_compare(id=id)
