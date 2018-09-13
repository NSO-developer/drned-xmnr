import optparse
import json
import datetime
import drned
import pytest
import os
import re
import sys
import glob
import string
import subprocess
from lxml import etree

import common.test_common as common

VERBOSE = False
XVERBOSE = False

def compress_path(path):
    while re.match(".*?{([^}]+)}.*?({\\1}).*", path):
        path = re.sub("(.*?{([^}]+)}.*?)({\\2})(.*)", "\\1\\4", path)
    return path

class _Coverage(object):
    set_map = {}
    schema = None
    def __init__(self, name):
        self.name = name
        self.value = None
        self.is_set = False
        self.was_read = False
        self.was_set = False
        self.was_deleted = False
        self.was_modified = False
        self.was_deleted_separately = False
        self.found = False

    # Init node without affecting transition flags
    def init_node(self, value):
        if VERBOSE:
            print("INIT " + self.name)
        self.is_set = True
        self.was_read = True
        self.value = value
        self.update_set_map()

    # Set node
    def set_node(self, value):
        if self.is_set and value != self.value:
            if VERBOSE:
                print("ADD %s: %s: was_set" % (self.name, value))
                print("ADD %s: %s: was_modified" % (self.name, value))
            self.was_set = True
            self.was_modified = True
        elif not self.is_set:
            if VERBOSE:
                v = value.strip() if value else None
                print("ADD %s: %swas_set" % (self.name, (value + ": ") if value else ""))
            self.was_set = True
        self.is_set = True
        self.was_read = True
        self.value = value
        self.update_set_map()

    # Delete node
    def delete_node(self):
        if self.is_set and not self.name in _Coverage.set_map:
            self.was_deleted = True
            self.is_set = False
            if VERBOSE:
                print("DEL %s: was_deleted" % (self.name))
            if "]/" in self.name:
                lpath = self.name[:self.name.rindex("]/")+1]
                self.was_deleted_separately = (lpath in _Coverage.set_map)
                if not self.was_deleted_separately:
                    sname = re.sub("\[[^\]]*\]", "", lpath)
                    node = _Coverage.schema.get_node(sname)
                    if (not node) or (not node.stmt):
                        print("NOTE: skipping delete of unknown element: '%s'" % compress_path(sname))
                    elif node.stmt.search_one(("tailf-common", "cli-recursive-delete")):
                        if "]/" in lpath:
                            # TODO: should walk upwards if recursive,
                            # currently we don't see nested recursive-dels
                            lpath = lpath[:lpath.rindex("]/")+1]
                            self.was_deleted_separately = (lpath in _Coverage.set_map)
                        else:
                            self.was_deleted_separately = True
            else:
                self.was_deleted_separately = True
            # Parent still present, so node deleted separately
            if VERBOSE:
                print("DEL %s: was_deleted_separately" % (self.name))

    # Update node with values from another node
    def union_node(self, node):
        if node.was_read:
            self.was_read = True
        if node.was_set:
            self.was_set = True
        if node.was_deleted:
            self.was_deleted = True
        if node.was_modified:
            self.was_modified = True
        if node.was_deleted_separately:
            self.was_deleted_separately = True

    # Update set map
    def update_set_map(self):
        _Coverage.set_map[self.name] = True

def test_coverage(fname, argv, all, devname, yangpath=""):
    """Show test coverage since the last "make covstart" command.

    The coverage data is calculated by comparing the YANG model
    specified in the --fname argument with all .xml files in the
    drned-work/coverage directory. The "make covstart" command creates
    this directory, and all subsequent commits will automatically
    create a new .xml representation of the configuration data.

    After a "make covstart", you have to run all tests in sequence to
    be able to calculate the total coverage. Note that "make restart"
    removes the coverage directory, so do not restart while
    accumulating coverage files.

    A sample output is:

    Found a total of 1554 nodes (554 of type empty) and 172 lists,
       777 ( 50%) nodes read or set
       100 ( 58%) lists read or set
        90 ( 52%) lists deleted
        85 ( 50%) lists with multiple entries read or set
       559 ( 35%) nodes set
       559 ( 35%) nodes deleted
         4 (  0%) nodes set when already set
       349 ( 22%) nodes deleted separately
      1036 ( 66%) grouping nodes read or set
       821 ( 52%) grouping nodes set
       821 ( 52%) grouping nodes deleted
         5 (  0%) grouping nodes set when already set
       590 ( 37%) grouping nodes deleted separately

    This means that:

    The total number of leaves/leaf-lists in the model is 1554
    (excluding key-leaves). Out of these 554 are of type 'empty'
    (i.e. can't be 'set when already set'). To that 172 lists were
    found.

    The node/list-counts means:

    - 777 nodes were successfully read from the device, either in the
      initial sync-from, or in a later set operation.

    - 100 lists were read or set, either read in the initial
      sync-from, or in a later set operation.

    - 90 of the lists were also deleted (i.e. at least one entry of
      each of these lists were deleted, e.g. as part of a rollback).

    - 85 lists had multiple entries, either in the initial sync-from,
      or in a later set operation. The remaining lists did however
      only have a single entry, or no entry at all. A good test suite
      should have multiple entries for all lists.

    - 559 nodes were set and deleted, which means that 1554 - 559 =
      995 nodes were never touched. A good test suite should exercise
      as many of the nodes as possible.

    - 4 nodes were modified, i.e. set with another value than the
      current one. The other nodes were only set from scratch,
      i.e. there was no previous value. A good test suite should also
      contain modification of nodes since it may trigger different
      device behaviour.

    - 349 nodes were deleted one by one, which is good. The other
      nodes were implicitly deleted, i.e. when the parent container or
      list entry was deleted. The separate delete operation is most
      often more demanding, and should be used in a good test suite.

    - The remaining "grouping" values are taking into account that a
      node may be part of a grouping. If a tested node is part of a
      grouping, all nodes that use the same grouping will also be
      considered as tested, giving increased coverage figures. Note
      that the these values should merely be used as an indication,
      the device may have different behaviour at the places where the
      grouping is used.

    Args:
        fname: YANG file to use when calculating coverage

        argv: list of paths/path-prefixes to include/exclude (to exclude a path
              give path prefixed with ^, e.g. ^/router/bgp)

        all: print a list of all nodes not found in each
             count-category

        devname: use only data from test runs with given device name. The device
                 name 'real' can be used to exclude netsim tests.  (NOTE: when
                 run through py.test the value of argument --device is used for
                 devname)

    Returns:
        nothing

    """
    # Heuristics to load YANG files in correct order
    def yangprio(str):
        prio = [
            "-common.yang",
            ".yang"
        ]
        for i,v in enumerate(prio):
            if str.endswith(v):
                return i
        pytest.fail("Files should have .yang extension: %s" % str)

    def find_yang(dir):
        exclude = ("-id.yang", "-stats.yang", "-meta.yang", "-mlx.yang", "-oper.yang")
        fname = glob.glob(dir)
        fname = [f for f in fname if not f.endswith(exclude)]
        fname = sorted(fname, key=yangprio)
        return fname

    # Hunt for YANG files
    if not fname:
        # Most likely place
        fname = find_yang("../../src/yang/*.yang")
    if not fname:
        # SNMP NEDs lack initial YANG files
        fname = find_yang("../../src/ncsc-out/modules/yang/*.yang")
    if not fname:
        pytest.fail("Cannot find any YANG files to use,\nchecked in src/yang and src/ncsc-out/modules/yang")

    print("\nUse YANG file(s):\n%s\n" % "\n".join(fname))

    _Coverage.schema = drned.Schema(fname, [], yangpath)

    skip_lists = []
    skip_leaves = []
    include_prefixes = []
    exclude_prefixes = []
    if not argv:
        argv = []
    for p in argv:
        if p.startswith("^"):
            exclude_prefixes.append(p[1:])
        else:
            include_prefixes.append(p)

    lists_to_count = [n for n in _gen_nodes(skip_lists, include_prefixes, exclude_prefixes, ["list"]) if n.is_config()]
    leafs_to_count = [n for n in _gen_nodes(skip_leaves, include_prefixes, exclude_prefixes, ["leaf-list", "leaf"]) if n.is_config()]

    # Get all collected coverage data
    all_coverage = {}
    list_multiple = set()
    cached_dirs = []
    save_cache = False

    use_cache = (subprocess.check_output("whoami", shell=True).strip() != "jenkins") \
        and (devname is None or devname == "none")

    if use_cache and os.path.exists("drned-work/coverage/covanalysis.json"):
        with open("drned-work/coverage/covanalysis.json", "rb") as covf:
            covcache = json.load(covf)
            cached_dirs = covcache["cached_dirs"]
            list_multiple = set(covcache["list_multiple"])
            for (p, d) in covcache["coverage"].iteritems():
                c = _Coverage("dummy")
                c.__dict__ = d
                all_coverage[p] = c

    # Read one session at a time in ascending order
    for dir in sorted(os.listdir("drned-work/coverage")):
        # Read one file at a time in ascending order
        in_sync = False
        coverage = {}
        if dir in cached_dirs or dir == "covanalysis.json":
            continue
        save_cache = use_cache
        cached_dirs.append(dir)
        if VERBOSE:
            sys.stdout.write("\nREAD_DIR: " + dir)
        for fn in sorted(os.listdir("drned-work/coverage/%s" % dir)):
            if VERBOSE:
                sys.stdout.write('.')
                sys.stdout.flush()
            _Coverage.set_map = {}
            fp = "drned-work/coverage/%s/%s" % (dir, fn)
            if fp.endswith(".xml") \
               and os.path.isfile(fp) \
               and os.path.getsize(fp) > 0:
                if VERBOSE:
                    print("LOAD FILE: %s" % fp)
                try:
                    root = etree.parse(fp)
                except:
                    # Remove non-ascii chars and try again
                    print(("Error when scanning %s, " % fp) +
                          "remove non-ascii chars and retry")
                    with open(fp) as r:
                        lines = r.read()
                    lines = filter(lambda x: x in string.printable, lines)
                    with open(fp + ".tmp", "w") as w:
                        w.write(lines)
                    root = etree.parse(fp + ".tmp")
                device = root.find("//{http://tail-f.com/ns/ncs}name")
                if devname and devname != "none":
                    if devname == "real" and "netsim" in device.text:
                        continue
                    if devname != "real" and not devname in device.text:
                        continue
                cfg = root.find("//{http://tail-f.com/ns/ncs}config")
                if not cfg is None:
                    ddc = root.getelementpath(cfg)
                    cfgnodes = cfg.iter()
                    cfgnodes.next()  # skip cfg itself
                else:
                    # Empty DB -> noting set initially or all deleted in the end
                    cfgnodes = []

                leaf_lists = dict()
                current_list_prefix = list()
                current_key_vals = None
                current_key_names = None
                list_keys = dict()

                for e in cfgnodes:
                    if (e.text and e.text.strip() != "") or not e.getchildren():
                        path = root.getelementpath(e)[len(ddc):]
                        orig_path = path
                        if XVERBOSE:
                            print("PATH %s" % path)
                        while current_list_prefix:
                            if path.startswith(current_list_prefix[-1][0]):
                                pn = len(current_list_prefix[-1][0])
                                path = current_list_prefix[-1][1] + "/" + path[pn:]
                                break
                            else:
                                if XVERBOSE:
                                    print("POP: " + current_list_prefix[-1][0])
                                current_list_prefix.pop()
                        if XVERBOSE and path != orig_path:
                            print("EXPANDED PATH %s" % path)
                        sname = re.sub("\[[^\]]*\]", "", path)
                        node = _Coverage.schema.get_node(sname)
                        if not node:
                            print("NOTE: skipping unknown element: '%s' (%s)" % (compress_path(path), sname))
                            continue
                        if node.is_key():
                            if not current_key_names:
                                current_key_names = node.get_parent().stmt.search_one("key").arg.split(" ")
                                current_key_vals = list()
                            key_tag = re.sub("{[^}]+}", "", e.tag)
                            if not key_tag in current_key_names:
                                raise Exception("Expected key (%s) here : %s" % (str(current_key_names), path))
                            current_key_vals.append(e.text.strip() if e.text else "")
                            if len(current_key_vals) == len(current_key_names):
                                path = path[:path.rindex(e.tag)-1]
                                orig_path = orig_path[:orig_path.rindex(e.tag)-1]
                                if path[-1] == "]":
                                    path = path[:path.rindex("[")]
                                current_key_vals = ",".join(current_key_vals)
                                path = ("%s[%s]" %
                                        (path,
                                         current_key_vals))
                                orig_path += "/"
                                if XVERBOSE:
                                    print("ADD LIST PREFIX: %s - %s" % (path + "/", orig_path))
                                current_list_prefix.append((orig_path, path))
                                nokeys_path = re.sub("\[[^\]]*\]", "", path)
                                if not list_keys.has_key(nokeys_path):
                                    list_keys[nokeys_path] = set()
                                list_keys[nokeys_path].add(current_key_vals)
                                current_key_names = None
                                current_key_vals = None
                                # Fall through and count full list instance
                            else:
                                # Skip keys in count
                                continue
                        elif node.is_leaflist():
                            # Collect leaf-lists into single value
                            if VERBOSE:
                                print("FOUND LEAFLIST: " + path)
                            if path[-1] == "]":
                                path = path[:path.rfind("[")]
                            if not path in leaf_lists:
                                leaf_lists[path] = list()
                            leaf_lists[path].append(e.text)
                            continue
                        # Ignore all but config
                        # Enter data
                        if not path in coverage:
                            coverage[path] = _Coverage(path)
                        # First file only provides init values,
                        # and does no transitions
                        if in_sync:
                            coverage[path].set_node(e.text)
                        else:
                            coverage[path].init_node(e.text)
                for (p, v) in leaf_lists.iteritems():
                    if not p in coverage:
                        coverage[p] = _Coverage(p)
                    v = ",".join(v)
                    if in_sync:
                        coverage[p].set_node(v)
                    else:
                        coverage[p].init_node(v)
                in_sync = True

            for (p, keys) in list_keys.iteritems():
                if len(keys) > 1:
                    list_multiple.add(p)
                    if VERBOSE:
                        print("LIST with multiple instances " + p)

            # Handle nodes deleted in this lap
            for p in coverage:
                coverage[p].delete_node()

        # We now have one coverage map per dir, unionize after each dir to avoid excessive calls to delete_node above
        for (p, cov) in coverage.iteritems():
            if all_coverage.has_key(p):
                all_coverage[p].union_node(cov)
            else:
                all_coverage[p] = cov

    coverage = all_coverage

    if save_cache:
        with open("drned-work/coverage/covanalysis.json", "wb") as covf:
            def dumpcov(o):
                if isinstance(o, _Coverage):
                    return o.__dict__
                else:
                    return o
            covcache = {}
            covcache["coverage"] = coverage
            covcache["cached_dirs"] = cached_dirs
            covcache["list_multiple"] = list(list_multiple)
            json.dump(covcache, covf, default=dumpcov)

    # Consolidate lists into single entries
    for p in coverage.keys():
        nolist = re.sub("\[[^\]]*\]", "", p)
        if nolist != p:
            # Ok, this path has at least one list, so move to common entry
            if not nolist in coverage:
                coverage[nolist] = _Coverage(nolist)
            coverage[nolist].union_node(coverage[p])
            if XVERBOSE and (p[-1] == "]"):
                print("CONSOLIDATE LIST: " + nolist)
            coverage.pop(p)

    # Init stats
    stats_name = [
        "nodes %s read or set",
        "lists %s read or set",
        "lists %s deleted",
        "lists %s with multiple entries read or set",
        "nodes %s set",
        "nodes %s deleted",
        "nodes %s set when already set",
        "nodes %s deleted separately",
        "grouping nodes %s read or set",
        "grouping nodes %s set",
        "grouping nodes %s deleted",
        "grouping nodes %s set when already set",
        "grouping nodes %s deleted separately"
    ]
    stats = {}
    stats["all"] = []
    stats["all_lists"] = []
    for n in stats_name:
        stats[n] = []

    # Add list stats
    list_nodes = 0
    for node in lists_to_count:
        path = node.get_path()
        stats["all_lists"].append(path)
        list_nodes += 1
        if path in list_multiple:
            stats["lists %s with multiple entries read or set"].append(path)
        if path in coverage:
            cov = coverage[path]
            cov.found = True
            if path not in stats["lists %s read or set"]:
                # Only count for one key (if list has multiple keys)
                stats["lists %s read or set"].append(path)
            if cov.was_deleted:
                stats["lists %s deleted"].append(path)

    # Accumulate grouping data
    grouping = {}
    for node in leafs_to_count:
        path = node.get_path()
        if path in coverage:
            file,line = node.get_pos()
            name = node.get_arg()
            fln = (file,line,name)
            if fln not in grouping:
                if VERBOSE:
                    print("GROUP (%s,%s,%s): %s" % (fln + tuple([path])))
                grouping[fln] = _Coverage(path)
            grouping[fln].union_node(coverage[path])

    # Compare to YANG
    schema_nodes = 0
    empty_nodes = 0
    non_sepdel_nodes = 0
    for node in leafs_to_count:
        if node.is_key():
            # skip keys, we count list-instances above
            continue
        path = node.get_path()
        stats["all"].append(path)
        schema_nodes += 1
        if node.is_leaf() and node.get_type() == "empty":
            empty_nodes += 1
        non_sepdel = _not_separately_deletable(node)
        if non_sepdel:
            non_sepdel_nodes += 1
        file,line = node.get_pos()
        name = node.get_arg()
        grp = None
        if (file,line,name) in grouping:
            grp = grouping[(file,line,name)]
        if path in coverage:
            cov = coverage[path]
            cov.found = True
            if cov.was_read:
                stats["nodes %s read or set"].append(path)
            if cov.was_set:
                stats["nodes %s set"].append(path)
            if cov.was_deleted:
                stats["nodes %s deleted"].append(path)
            if not non_sepdel and cov.was_deleted_separately:
                stats["nodes %s deleted separately"].append(path)
            if cov.was_modified:
                stats["nodes %s set when already set"].append(path)
        # Add grouping stats
        if grp:
            if grp.was_read:
                stats["grouping nodes %s read or set"].append(path)
                if VERBOSE:
                    print("ADD %s: group_was_read" % path)
            if grp.was_set:
                stats["grouping nodes %s set"].append(path)
                if VERBOSE:
                    print("ADD %s: group_was_set" % path)
            if grp.was_deleted:
                stats["grouping nodes %s deleted"].append(path)
                if VERBOSE:
                    print("DEL %s: group_was_deleted" % path)
            if not non_sepdel and grp.was_deleted_separately:
                stats["grouping nodes %s deleted separately"].append(path)
                if VERBOSE:
                    print("DEL %s: group_was_deleted_separately" % path)
            if grp.was_modified:
                stats["grouping nodes %s set when already set"].append(path)
                if VERBOSE:
                    print("ADD %s: group_was_modified" % path)

    def print_paths(paths):
        nsmap = dict()
        for p in paths:
            ns = ""
            p = compress_path(p)
            if p.startswith("/{"):
                ns = p[2:p.index("}")]
                p = "/" + p[p.index("}")+1:]
            if not nsmap.has_key(ns):
                nsmap[ns] = list()
            nsmap[ns].append(p)
        if len(nsmap.keys()) > 1:
            for (ns, pl) in nsmap.iteritems():
                print("  namespace: " + ns + "\n  " +
                        "\n  ".join(sorted(pl)))
        else:
                print("  " + "\n  ".join(sorted(nsmap.values()[0])))

    # Print result
    if all:
        for name in stats_name:
            f = []
            if "grouping nodes " in name:
                continue
            if "with multiple entries" in name:
                f = list(set(stats["all_lists"]) - list_multiple)
            elif "lists %s " in name:
                f = list(set(stats["all_lists"]) - set(stats[name]))
            else:
                s = list(set(stats["all"]) - set(stats[name]))
                for p in s:
                    n = _Coverage.schema.get_node(p)
                    if not ("when already set" in name and n.get_type() == "empty") and \
                       not ("deleted separately" in name and _not_separately_deletable(n)):
                          f.append(p)
            if f:
                print(("\n### %s:" % name.replace("%s", "never")))
                print_paths(f)

    print("\nFound a total of %d nodes (%d of type empty) and %s lists," %
          (schema_nodes, empty_nodes, list_nodes))
    for n in stats_name:
        nodes = list_nodes if n.startswith("lists") else schema_nodes
        not_count = ""
        if "when already" in n and empty_nodes:
            nodes = nodes - empty_nodes
            not_count = " (disregarding %d empty leaves)" % empty_nodes
        if "deleted separately" in n and non_sepdel_nodes:
            nodes = nodes - non_sepdel_nodes
            not_count = " (disregarding %d bool-no|prefix-key|mandatory)" % non_sepdel_nodes
        perc = 100
        if nodes > 0:
            perc = (100 * len(stats[n]) / nodes)
        print("%6d (%3d%%) %s%s" %
              (len(stats[n]),
               perc,
               n.replace("%s ", ""), not_count))

    # Check for nodes that are set but not found in model
    not_found = []
    empty_containers = []
    all_skip = skip_leaves + skip_lists
    for c in coverage:
        if (not coverage[c].found and
            not c in all_skip and
            not common.path_in_prefixes(c, exclude_prefixes) and
            (not include_prefixes or common.path_in_prefixes(c, include_prefixes))):
            n = _Coverage.schema.get_node(c)
            if not n:
                not_found.append(c)
            elif not n.is_presence_container():
                if n.is_container():
                    empty_containers.append(c)
                else:
                    # something strange happened?
                    not_found.append(c)

    if not_found:
        print("\nNOTE: the following nodes " +
              "were set, but do not exist in the model:\n" +
              "\n".join(sorted(not_found)))
    if empty_containers:
        print("\nNOTE: the following containers " +
              "were found empty (though not marked as presence):")
        print_paths(empty_containers)

# Loop for all nodes of a certain type
def _gen_nodes(skip_nodes, include_prefixes, exclude_prefixes, ntype):
    return common.gen_nodes(_Coverage.schema, skip_nodes, include_prefixes, exclude_prefixes, ntype)

def _not_separately_deletable(node):
    return (node.get_tailf(("tailf-common", "cli-boolean-no")) or
            node.get_tailf(("tailf-common", "cli-prefix-key")) or
            node.is_mandatory())

if __name__ == '__main__':
    usage = """%prog [options] [<path1> ... <pathN>

    <pathN> X-paths of subtrees to include/exlude.

Calculate coverage of test-runs"""

    optlist = [
        optparse.make_option("-D", "--devname",
                             help="use only data from test runs with given device name. The device name 'real' can be used to exclude netsim tests."),
        optparse.make_option("-a", "--all",
                             help="output all untested paths in each category",
                             action="store_true"),
        ]
    optparser = optparse.OptionParser(usage, add_help_option = True)
    optparser.add_options(optlist)
    (o, args) = optparser.parse_args()

    test_coverage(None, args, o.all, o.devname)
