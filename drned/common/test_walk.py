import drned
import pytest
import pprint
import inspect
import filecmp

EQ = "#" * 30

def test_walk_direct(device, iteration, root, map_list, yang, yangpath=[]):
    if device.version < "3.4":
        pytest.xfail("test_walk will fail since pyang requires NCS 3.4")
    schema = drned.Schema(yang, map_list, yangpath)
    leaves = schema.list_nodes(root=root, ntype=["leaf", "leaf-list"])
    walker = drned.Walker(leaves)
    stage = drned.Stage(schema)
    walker.log = True

    i = 1
    for leaf in walker.gen_walk():
        if i in iteration:
            if leaf == None:
                print("%s %s --iteration=%d" % (EQ, inspect.stack()[0][3], i))
                device.save("drned-work/before-test.cfg")
                stage.flush(device)
                device.commit_rollback()
                device.save("drned-work/after-test.cfg")
                if not filecmp.cmp("drned-work/before-test.cfg",
                                   "drned-work/after-test.cfg"):
                    pytest.fail("The state after rollback differs from " +
                                "before load. Please check before-test.cfg " +
                                "and after-test.cfg")
            else:
                stage.add_leaf(leaf, leaf.value)
        if leaf == None:
            i += 1

    print("Total leaves: %d" % walker.total)
    print("Omitted leaves: %d" % len(walker.omitted))
    if len(walker.omitted) > 0:
        print(walker.omitted)

def test_walk_saved(device, root, map_list, yang, yangpath=[]):
    schema = drned.Schema(yang, map_list, yangpath)
    if not device.name.startswith("netsim"):
        schema.append_map("avoid_map", avoid_map_device)
    leaves = schema.list_nodes(root=root, ntype=["leaf", "leaf-list"])
    walker = drned.Walker(leaves)
    stage = drned.Stage(schema)
    walker.log = True

    fname = "drned-work/%s_%s_%%02d.xml" % \
        (device.name, inspect.stack()[0][3].replace("test_", "", 1))
    i = 1
    for leaf in walker.gen_walk():
        if leaf == None:
            stage.save(device, fname % i)
            i += 1
        else:
            stage.add_leaf(leaf, leaf.value)

    print("Total leaves: %d" % walker.total)
    print("Omitted leaves: %d" % len(walker.omitted))
    if len(walker.omitted) > 0:
        pprint.pprint(sorted(walker.omitted))
