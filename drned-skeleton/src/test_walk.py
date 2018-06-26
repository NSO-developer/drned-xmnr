import common.test_walk as common

yang = "../../src/yang/tailf-ned-%NAME%.yang"

type_map = {
    "inet:ipv4-address"  : ["1%d.1%d.1%d.1%d"],
    "yang:mac-address"   : ["%d0:%d0:%d0:%d0:%d0:%d0"],
    "inet:ipv6-address"  : ["fe80:%d:100%d:200%d:300%d:400%d:500%d:600%d"],
    "inet:ip-address"    : ["1%d.1%d.1%d.1%d"],
    "tailf:ipv4-address-and-prefix-length" :  ["1%d.1%d.1%d.0/24"],
    "tailf:ipv6-address-and-prefix-length" : ["200%d::4/32"],
}

pattern_map = {
}

leaf_map = {
}

xpath_map = {
}

avoid_map = {
}

avoid_map_device = {
}

map_list = [("type_map"   , type_map),
            ("pattern_map", pattern_map),
            ("leaf_map"   , leaf_map),
            ("xpath_map"  , xpath_map),
            ("avoid_map"  , avoid_map)]

def test_walk_direct(device, iteration, root):
    if not device.name.startswith("netsim"):
        avoid_map.update(avoid_map_device)
    common.test_walk_direct(device, iteration, root, map_list, yang)

def test_walk_saved(device, root):
    if not device.name.startswith("netsim"):
        avoid_map.update(avoid_map_device)
    common.test_walk_saved(device, root, map_list)
