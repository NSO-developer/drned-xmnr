#!/usr/bin/env python

import glob
import hashlib
import optparse
import subprocess
import os
import re
import sys
import json
import tempfile

class Ystmt(object):
    def __init__(self, keyword, arg, in_uses=None, path=None, subs=None):
        self.keyword = keyword
        self.arg = arg
        self.keys = []
        self.path = path
        self.subs = subs
        self.is_key_leaf = False
        self.in_uses = in_uses

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __ne__(self, other):
        return self.__hash__() != other.__hash__()

    def __hash__(self):
        hstr = self.keyword + str(self.arg)
        hstr += str([hash(s) for s in self.subs] if self.subs else None)
        return hash(hstr)

    def get(self, subname):
        if self.subs:
            for s in self.subs:
                if s.keyword == subname:
                    return s
        return None

    def get_path(self):
        return self.path

    def is_key(self):
        return self.is_key_leaf

    def in_grp(self):
        grpname = self.in_uses
        if grpname:
            grpname = grpname[grpname.rindex(":")+1:]
        return grpname

    def is_empty_leaf(self):
        return ((self.keyword == "leaf") and
                (self.get("type").arg == "empty"))

    def is_leaflist(self):
        return (self.keyword == "leaf-list")

    def is_presence_container(self):
        return ((self.keyword == "container") and
                (self.get("presence") != None))

    def emit(self, ilevel=0):
        lines = list()
        indent = ilevel * "  "
        if self.subs:
            comments = [s for s in self.subs if isinstance(s, Ycomment)]
            for c in comments:
                if not c.node:
                    self.subs.remove(c)
                    lines += c.emit(ilevel)
        argstr = ""
        if self.arg != None:
            quot = "\"" if self.keyword not in { "leaf", "leaf-list", "container", "list", "type", "enum", "ordered-by" } else ""
            argstr =  " %s%s%s" % (quot, self.arg, quot)
        if not self.subs and self.keyword != "container":
            lines.append("%s%s%s;" % (indent, self.keyword, argstr))
        else:
            lines.append("%s%s%s {" % (indent, self.keyword, argstr))
            for s in self.subs:
                lines += s.emit(ilevel+1)
            lines.append("%s}" % indent)
        return lines

    @staticmethod
    def extract_flat_substmts(dump):
        substmts = list()
        for substmt in dump:
            keyword = str(substmt[0])
            si = 1
            name = None
            substmt_subs = None
            if len(substmt) > 1:
                if isinstance(substmt[si], str) or isinstance(substmt[si], unicode):
                    name = str(substmt[si])
                    si += 1
                else:
                    name = None
                if len(substmt) > si:
                    substmt_subs = Ystmt.extract_flat_substmts(substmt[si])
            substmts.append(Ystmt(keyword, name, substmt_subs))
        return substmts

class Ycomment(Ystmt):
    def __init__(self, comment, node=None):
        Ystmt.__init__(self, comment, None)
        self.comment = comment
        self.node = node

    def emit(self, ilevel=0):
        indent = ilevel * "  "
        lines = list(["%s// %s" % (indent, self.comment)])
        if self.node:
            commented = self.node.ystmt()
            stmt_lines = commented.emit(ilevel)
            for sl in stmt_lines:
                lines.append("%s// %s" % (indent, sl))
        return lines

have_drned = True

try:
    import common.test_common as common
except:
    have_drned = False

in_terminal = True
DEBUG = False

outbuf = list()
def print_line(line):
    outbuf.append(line)

def flush_lines():
    global outbuf
    lines = outbuf
    outbuf = list()
    return lines

def bold_str(str):
    if in_terminal:
        str = "\x1b[1m%s\x1b[0m" % str
    return str

def collapse_common_suffixes(paths):
    def maxsuf(p):
        return p[p.index("}")+1:].count("/")-1
    def prefix(p, suf_len):
        l = p.split("/")
        return "/".join(l[:len(l)-suf_len])
    p0 = paths[0]
    for n in range(1, maxsuf(p0)+1):
        prf = prefix(p0, n)
        suf = p0[len(prf):]
        all_impl_pref = [p[:-len(suf)] for p in paths if p.endswith(suf)]
        prefcnt = len(all_impl_pref)
        if (prefcnt < len(paths)) and ((len(paths) % prefcnt) == 0):
            all_impl_suf = [p[len(prf)+1:] for p in paths if p.startswith(prf)]
            if (len(all_impl_suf) * prefcnt) == len(paths):
                return (all_impl_pref, all_impl_suf)
    return None

def strippath(path, strip_namespaces=False, strip_prefixes=False):
    if strip_namespaces and "}" in path:
        path = "/" + path[path.index("}")+1:]
    if strip_prefixes:
        path = re.sub("[^/^:]+:", "", path)
    return path

def add_suffix(paths, suffix, strip_namespaces=False, strip_prefixes=False):
    return [strippath(p, strip_namespaces=strip_namespaces,
                      strip_prefixes=strip_prefixes) + suffix for p in paths]

def do_regex_compress(paths, regex_list):
    for regex in regex_list:
        if all([re.match(regex, p) for p in paths]):
            return list(set([re.sub(regex, "\\1*\\3", p) for p in paths]))
    return paths

def collapse_groupings(title, paths, node_info, strip_namespaces=False, regex_compress=[], compact_groupings=False):
    grp_list = list()
    grpmap = dict()
    collapsed_paths = list(paths)
    for p in paths:
        nodei = node_info[p]
        if "in_uses" in nodei:
            grpname = nodei["in_uses"]
            useat = grpname[:grpname.rindex(":")]
            grpname = grpname[grpname.rindex(":")+1:]
            if grpname not in grpmap:
                grpmap[grpname] = dict()
            relpath = p[len(useat)+1:]
            if relpath not in grpmap[grpname]:
                grpmap[grpname][relpath] = list()
            grpmap[grpname][relpath].append(useat)
            collapsed_paths.remove(p)
    for (grpname, relpaths) in grpmap.items():
        max_uses = 1
        all_uses = None
        for uses in relpaths.values():
            if len(uses) > max_uses:
                max_uses = len(uses)
                all_uses = uses
        all_relpaths = list()
        for (rp, uses) in relpaths.items():
            if len(uses) == 1 or (len(uses) < max_uses):
                collapsed_paths += [absp + "/" + rp for absp in uses]
            else:
                all_relpaths.append(rp)
        if all_uses:
            indent = ""
            grp_in_grp = collapse_common_suffixes(all_uses) # to collapse groupings in groupings
            fold_grp_in_grp = (grp_in_grp != None) and ((len(grp_in_grp[0]) + len(grp_in_grp[1])) < len(all_uses))
            did_fold = False
            if fold_grp_in_grp:
                (outer_abspaths, outer_relpaths) = grp_in_grp
                grp_list.append("")
                grp_list.append("%s nodes from embedded grouping <%s>" % (title, grpname))
                outer_abspaths = add_suffix(outer_abspaths, "/...",
                                            strip_namespaces=strip_namespaces,
                                            strip_prefixes=strip_namespaces)
                if regex_compress:
                    outer_abspaths = do_regex_compress(outer_abspaths, regex_compress)
                if not compact_groupings:
                    grp_list += sorted(outer_abspaths)
                all_uses = outer_relpaths
                did_fold = True
                indent = "    "
            else:
                grp_list.append("")
                grp_list.append("%s nodes in grouping <%s>" % (title, grpname))

            all_uses = add_suffix(all_uses, "/...",
                                  strip_namespaces=strip_namespaces,
                                  strip_prefixes=strip_namespaces)

            if regex_compress:
                all_uses = do_regex_compress(all_uses, regex_compress)

            if not compact_groupings or did_fold:
                grp_list += [indent + p for p in sorted(all_uses)]

            indent += "    "
            grp_list += sorted([indent + strippath(rp, strip_prefixes=strip_namespaces) for rp in all_relpaths])

    did_collapse = False
    if collapsed_paths:
        collapsed2_paths = collapse_common_suffixes(collapsed_paths)
        if collapsed2_paths:
            (outer_abspaths, outer_relpaths) = collapsed2_paths
            if (len(outer_abspaths) + len(outer_relpaths)) < len(collapsed_paths):
                if regex_compress:
                    outer_abspaths = do_regex_compress(outer_abspaths, regex_compress)
                outer_abspaths = add_suffix(outer_abspaths, "/...",
                                            strip_namespaces=strip_namespaces,
                                            strip_prefixes=strip_namespaces)
                collapsed_paths = sorted(outer_abspaths)
                collapsed_paths += sorted(["    " + strippath(rp, strip_prefixes=strip_namespaces) for rp in outer_relpaths])
                did_collapse = True
    if not did_collapse:
        collapsed_paths = add_suffix(collapsed_paths, "",
                                     strip_namespaces=strip_namespaces,
                                     strip_prefixes=strip_namespaces)
        collapsed_paths = sorted(collapsed_paths)

    return collapsed_paths + grp_list

def print_paths(title, paths, node_info, outbuf, strip_namespaces=False, regex_compress=[], compact_groupings=False):
    outbuf.append("\n  %s nodes:" % title)
    paths = [p for p in paths if node_info[p]["keyword"] not in ["choice", "case"]]
    lines = collapse_groupings(title, paths, node_info, strip_namespaces=strip_namespaces, regex_compress=regex_compress, compact_groupings=compact_groupings)
    outbuf += ["  " + l for l in lines]

def data_nodes(paths, node_info):
    return [p for p in paths if node_info[p]["keyword"] != "container"]

def print_changes_text(json_diff, from_commit, outbuf, title=None, include_incompats=False, include_removed=True, strip_namespaces=False, include_changes=True, regex_compress=[], compact_groupings=False):
    new_nodes = json_diff["new_nodes"]
    rem_nodes = json_diff["rem_nodes"]
    diff_nodes = json_diff["diff_nodes"]
    new_node_info = json_diff["new_node_info"]
    old_node_info = json_diff["old_node_info"]

    if title is None:
        title = "YANG model changes since %s:" % from_commit

    outbuf.append(title)

    new_data_nodes = data_nodes(new_nodes, new_node_info)
    if len(new_data_nodes):
        print_paths("New", new_data_nodes, new_node_info, outbuf, strip_namespaces=strip_namespaces, regex_compress=regex_compress, compact_groupings=compact_groupings)

    rem_data_nodes = data_nodes(rem_nodes, old_node_info)
    if include_removed and len(rem_data_nodes):
        print_paths("Removed", rem_data_nodes, old_node_info, outbuf, strip_namespaces=strip_namespaces, regex_compress=regex_compress, compact_groupings=compact_groupings)

    if include_incompats:
        incompat_nodes = json_diff["incompat_nodes"]
        if incompat_nodes:
            outbuf.append("")
            outbuf.append("  Incompatible nodes:")
            print_incompatible_nodes(incompat_nodes, json_diff["old_node_info"], json_diff["new_node_info"], outbuf=outbuf, strip_namespaces=strip_namespaces, regex_compress=regex_compress)
            diff_nodes = list(set(diff_nodes) - set(incompat_nodes))

    if len(diff_nodes) and include_changes:
        print_paths("Changed", diff_nodes, new_node_info, outbuf, strip_namespaces=strip_namespaces, regex_compress=regex_compress, compact_groupings=compact_groupings)

def filter_diff(json_diff, include_paths, exclude_paths):
    def filter(nodes):
        for nsp in list(nodes):
            p  = "/" + nsp[nsp.index("}")+1:]
            if any([p.startswith(ep) for ep in exclude_paths]):
                if isinstance(nodes, list):
                    nodes.remove(nsp)
                else:
                    nodes.pop(nsp)
            elif include_paths and not any([p.startswith(ip) for ip in include_paths]):
                if isinstance(nodes, list):
                    nodes.remove(nsp)
                else:
                    nodes.pop(nsp)
    filter(json_diff["new_nodes"])
    filter(json_diff["rem_nodes"])
    filter(json_diff["diff_nodes"])
    filter(json_diff["incompat_nodes"])

def filter_diff_regex(json_diff, regex_include=[], regex_exclude=[], strip_namespaces=False):
    def filter(nodes):
        for nsp in list(nodes):
            if strip_namespaces:
                p  = "/" + nsp[nsp.index("}")+1:]
            else:
                p = nsp
            if any([re.match(ep, p) for ep in regex_exclude]):
                if isinstance(nodes, list):
                    nodes.remove(nsp)
                else:
                    nodes.pop(nsp)
            elif regex_include and not any([re.match(ip, p) for ip in regex_include]):
                if isinstance(nodes, list):
                    nodes.remove(nsp)
                else:
                    nodes.pop(nsp)

    filter(json_diff["new_nodes"])
    filter(json_diff["rem_nodes"])
    filter(json_diff["diff_nodes"])
    filter(json_diff["incompat_nodes"])

def aggregate_diff(agg_diff, new_diff):
    agg_diff["old_node_info"].update(new_diff["old_node_info"])
    agg_diff["new_node_info"].update(new_diff["new_node_info"])
    agg_diff["incompat_nodes"].update(new_diff["incompat_nodes"])
    agg_diff["new_nodes"] += new_diff["new_nodes"]
    agg_diff["rem_nodes"] += new_diff["rem_nodes"]
    agg_diff["diff_nodes"] += new_diff["diff_nodes"]

def run(args):
    usage = """%prog [options] [<commit> [<ned-dir>]]

    <commit>|<from-commit>..<to-commit> git tag or commit, or commit-range as: '<first-commit>..<last-commit>' (defaults to latest release tag).
    <ned-dir>  NED repository working directory, assumes inside ned repository if not given.

Diff yang files between ned working-directory and given commit"""

    optlist = [
        optparse.make_option("-a", "--all",
                             help="Print all changes including incompatiblities",
                             action="store_true"),
        optparse.make_option("-d", "--debug",
                             help="Debug",
                             action="store_true"),
        optparse.make_option("-i", "--incompatible",
                             help="Print detailed listing of incompatibilities found",
                             action="store_true"),
        optparse.make_option("-j", "--json-intermediate",
                             help="Dump diff in json intermediate format",
                             action="store_true"),
        optparse.make_option("-k", "--keep-namespaces",
                             help="Keep namespace prefixes in paths",
                             action="store_true"),
        optparse.make_option("-K", "--keep-nonpresence",
                             help="Keep non-presence containers in removed nodes list",
                             action="store_true"),
        optparse.make_option("-f", "--file-with-diff",
                             help="Use the given precomputed diff (in json-format, generated with --json-intermediate)"),
        optparse.make_option("-l", "--left",
                             help="When running on a single yang-module, this is the 'left' or 'old' model"),
        optparse.make_option("-r", "--right",
                             help="When running on a single yang-module, this is the 'right' or 'new' model"),
        optparse.make_option("-t", "--title",
                             help="Title to print at top of output (defaults to 'YANG model changes since <commit>'"),
        optparse.make_option("-I", "--include",
                             help="Paths to include in diff (comma separeted if more than one)"),
        optparse.make_option("-E", "--exclude",
                             help="Paths to exclude from diff (comma separeted if more than one)"),
        optparse.make_option("-X", "--include-regex",
                             help="Regex of paths to include in diff"),
        optparse.make_option("-x", "--exclude-regex",
                             help="Regex of paths to exclude from diff"),
        optparse.make_option("-P", "--plugin-dir",
                             help="Yanger plugin dir if not running in drned and not present in nso dist dir"),
        optparse.make_option("-D", "--ned-dir",
                             help="Ned directory (e.g. where to find src/yang for -p if module includes other modules)"),
        optparse.make_option("-v", "--verbose",
                             help="Verbose description of changes (yang diff per changed node)",
                             action="store_true"),
        optparse.make_option("-V", "--verbose-context",
                             help="Verbose description of changes (yang unified diff per changed node)",
                             action="store_true"),
        optparse.make_option("-L", "--list-yang-files",
                             help="Only filter out and display yang-files that will be used for diff",
                             action="store_true"),
        optparse.make_option("-c", "--compact-groupings",
                             help="When printing paths in groupings, omit all uses, only show reltive paths withing grouping.",
                             action="store_true"),
    ]

    optparser = optparse.OptionParser(usage, add_help_option = True)
    optparser.add_options(optlist)
    (o, args) = optparser.parse_args(args)

    global DEBUG
    DEBUG = o.debug
    verbose = o.verbose or o.verbose_context

    strip_namespaces = not o.keep_namespaces
    keep_nonpresence = o.keep_nonpresence
    show_incompatible = o.incompatible
    jsondump = o.json_intermediate
    to_commit = "WORKING"
    from_commit = None

    if verbose and show_incompatible:
        print("Use either -i or -v/-V")
        return

    include_paths=[]
    if (o.include):
        include_paths = o.include.split(",")
    exclude_paths=[]
    if (o.exclude):
        exclude_paths = o.exclude.split(",")

    include_regex=[]
    if (o.include_regex):
        include_regex = [o.include_regex]
    exclude_regex=[]
    if (o.exclude_regex):
        exclude_regex = [o.exclude_regex]

    plugin_dir = o.plugin_dir
    drneddir = os.environ['DRNED']

    plugin_dir_arg = ""
    if plugin_dir:
        plugin_dir_arg = "-P %s" % plugin_dir
    elif have_drned:
        plugin_dir_arg = "-P %s/yanger/plugins" % drneddir
        subprocess.check_output("make -C %s/make/ yanger_plugins" % drneddir, shell=True)

    if o.list_yang_files:
        modinfo = find_yang(neddir + "/src/yang/*.yang")
        files = modinfo.files
        aug_mods = modinfo.augmenting_mods
        all_mods = modinfo.all_mods

        print("---")
        print("Found %d yang-files in %s" % (len(files), neddir))
        print("---")
        all_augmented = set()
        augmented_by = dict()
        for (am, a) in aug_mods.items():
            # am = re.sub("^.*/(.+)\.yang$", "\\1", f)
            for m in a:
                if m not in augmented_by:
                    augmented_by[m] = list()
                augmented_by[m].append(am)
                all_augmented.add(m)
            print("%s augments: %s" % (am, ",".join(a)))
        print("---")
        all_augmenting = set(aug_mods.keys())
        for (am, mods) in augmented_by.items():
            print("%s augmented by %d modules" % (am, len(mods)))
        print("---")
        both = all_augmented.intersection(all_augmenting)
        if both:
            print("BOTH: " + ",".join(both))
        not_augmented = set(all_mods.keys()).difference(all_augmenting)
        not_augmented = not_augmented.difference(all_augmented)
        print("Total modules: %d" % len(all_mods))
        print("Stand-alone modules: %d" % len(not_augmented))
        print("Augmenting modules %d" % len(all_augmenting))
        print("Augmented modules %d" % len(all_augmented))
        print("Multi modules %d" % len(both))

        for c in modinfo.chains:
            s = "CHAIN "
            for m in c:
                s += ": " + m
            print(s)

        print("NUM CHAINS: %d" % len(modinfo.chains))

        exit()

    if o.left:
        if not o.right:
            print_line("Must give both --left and --right arguments")
            return
        json_diff = None
        if os.path.isdir(o.left):
            leftmodinfo = find_yang(o.left + "/*.yang")
            rightmodinfo = find_yang(o.right + "/*.yang")

            (added, removed, changed) = leftmodinfo.diff(rightmodinfo)

            if added:
                print("*** Added %d modules" % len(added))
                print("  " + "\n  ".join(sorted(added)))
            if removed:
                print("*** Removed %d modules" % len(removed))
                print("  " + "\n  ".join(sorted(removed)))
            for m in changed:
                leftstandalone = m in leftmodinfo.standalone
                rightstandalone = m in rightmodinfo.standalone
                lmodlist = []
                rmodlist = []
                if leftstandalone or rightstandalone:
                    modlist = [m]
                    extras = []
                    if m not in leftstandalone and leftmodinfo.augmenting_mods:
                        extras = leftmodinfo.augmenting_mods[m]
                    elif m not in rightstandalone and rightmodinfo.augmenting_mods:
                        extras = rightmodinfo.augmenting_mods[m]
                    extras = list(filter(lambda em: em in leftmodinfo.all_mods
                                         and em in rightmodinfo.all_mods,
                                         extras))
                    modlist += extras
                    lmodlist = modlist
                    rmodlist = modlist
                else:
                    lc = leftmodinfo.get_chain(m)
                    rc = rightmodinfo.get_chain(m)
                    lmodlist = list(lc)
                    rmodlist = list(rc)
                    for lm in lc:
                        if lm not in rc and lm in rightmodinfo.all_mods:
                            rmodlist.append(lm)
                    for rm in rc:
                        if rm not in lc and rm in leftmodinfo.all_mods:
                            lmodlist.append(rm)
                lmodlist.remove('tailf-ncs')
                rmodlist.remove('tailf-ncs')
                lfiles = [leftmodinfo.all_mods[lm] for lm in lmodlist]
                rfiles = [rightmodinfo.all_mods[rm] for rm in rmodlist]
                jdiff = yang_diff_files(lfiles, rfiles, include_paths=include_paths, exclude_paths=exclude_paths, plugin_dir_arg=plugin_dir_arg)
                if json_diff is None:
                    json_diff = jdiff
                else:
                    aggregate_diff(json_diff, jdiff)


            json_diff["new_nodes"] = list(set(json_diff["new_nodes"]))
            json_diff["rem_nodes"] = list(set(json_diff["rem_nodes"]))
            json_diff["diff_nodes"] = list(set(json_diff["diff_nodes"]))

            # for (lc, rc) in zip(leftmodinfo.chains, rightmodinfo.chains):
            #     all_eq = True
            #     for m in lc:
            #         if leftmodinfo.mod2md5[m] != rightmodinfo.mod2md5[m]:
            #             all_eq = False
            #             break
            #     if all_eq:
            #         continue

            #     lfiles = [leftmodinfo.all_mods[m] for m in lc]
            #     rfiles = [rightmodinfo.all_mods[m] for m in rc]
            #     jdiff = yang_diff_files(lfiles, rfiles, include_paths=include_paths, exclude_paths=exclude_paths, plugin_dir_arg=plugin_dir_arg)
            #     if json_diff is None:
            #         json_diff = jdiff
            #     else:
            #         aggregate_diff(json_diff, jdiff)

            # json_diff["new_nodes"] = list(set(json_diff["new_nodes"]))
            # json_diff["rem_nodes"] = list(set(json_diff["rem_nodes"]))
            # json_diff["diff_nodes"] = list(set(json_diff["diff_nodes"]))

        else:
            left = [o.left]
            right = [o.right]
            if "," in o.left:
                left = o.left.split(",")
                right = o.right.split(",")

        if json_diff is None:
            json_diff = yang_diff_files(left, right, include_paths=include_paths, exclude_paths=exclude_paths, plugin_dir_arg=plugin_dir_arg)
    elif not o.file_with_diff:
        if not have_drned:
            raise Exception("Can't use drned, not found in environment, please give explicit files to diff")
        if not neddir:
            print_line("Must provide argument --ned-dir=<ned-directory>")
            return
        if not args:
            from_commit = common.find_last_release_tag()
        else:
            from_commit = args[0]
            range_sep = from_commit.find("..")
            if range_sep > 0:
                (from_commit, to_commit) = from_commit.split("..")
        json_diff = yang_diff_commits(neddir, from_commit, to_commit=to_commit,include_paths=include_paths, exclude_paths=exclude_paths, plugin_dir_arg=plugin_dir_arg)
    else:
        with open(o.file_with_diff) as f:
            json_diff = json.loads(f.read())
            filter_diff(json_diff, include_paths, exclude_paths)

    if include_regex or exclude_regex:
        filter_diff_regex(json_diff, include_regex, exclude_regex, strip_namespaces=strip_namespaces)

    if jsondump:
        print_line(json.dumps(json_diff, sort_keys=True, indent=4))
    elif show_incompatible:
        print_incompatible_nodes(json_diff["incompat_nodes"], json_diff["old_node_info"], json_diff["new_node_info"], strip_namespaces=strip_namespaces)
        print_removed_nodes(compact_rem_nodes(json_diff["rem_nodes"], json_diff["old_node_info"], keep_nonpresence=keep_nonpresence), json_diff["old_node_info"], strip_namespaces=strip_namespaces)
    else:
        outbuf = list()
        print_changes_text(json_diff, from_commit, outbuf, title=o.title, include_incompats=o.all, strip_namespaces=strip_namespaces, compact_groupings=o.compact_groupings)
        print_line("\n".join(outbuf))
        if verbose:
            print_verbose_diff(json_diff, context=o.verbose_context)

# Diff all yang-files except these (most NEDs only have one top-module, but
# e.g. fortigate-fortios has 2 top-level modules and one "import-module"
def find_yang(dir):
    exclude_suffix = ("-id.yang", "-stats.yang", "-oper.yang", "-meta.yang", "-secrets.yang", "cliparser-extensions-v11.yang", "-rpc.yang", "cliparser-extensions-v10.yang", "tailf-ned-loginscripts.yang", "-deviation.yang", "-deviations.yang", "-actions.yang", "-act.yang", "-datatypes.yang")
    exclude_prefix = ("ietf-", "iana-", "tailf-common")
    fname = glob.glob(dir)
    return filter_yang([f for f in fname if not (f.endswith(exclude_suffix) or os.path.basename(f).startswith(exclude_prefix))], exclude_prefix)

class ModulesInfo(object):
    def __init__(self, augmenting_mods, files, mod2md5):
        self.all_mods = dict()
        for f in files:
            m = re.sub("^.*/(.+)\.yang$", "\\1", f)
            self.all_mods[m] = f
        self.files = files
        self.augmenting_mods = augmenting_mods
        self.mod2md5 = mod2md5

        self.all_augmented = set()
        augmented_by = dict()
        for (am, a) in augmenting_mods.items():
            # am = re.sub("^.*/(.+)\.yang$", "\\1", f)
            for m in a:
                if m not in augmented_by:
                    augmented_by[m] = list()
                augmented_by[m].append(am)
                self.all_augmented.add(m)

        self.all_augmenting = set(augmenting_mods.keys())
        self.standalone = set(self.all_mods.keys()).difference(self.all_augmenting)
        self.standalone = self.standalone.difference(self.all_augmented)

        self.chains = list()

        def build_chain(chain, next_mod):
            chain.append(next_mod)
            if next_mod in self.all_augmenting:
                for a in augmenting_mods[next_mod]:
                    build_chain(list(chain), a)
            else:
                self.chains.append(chain)

        for (m, augments) in augmenting_mods.items():
            if m not in self.all_augmented:
                for a in augments:
                    build_chain(list([m]), a)

    def get_chain(self, mod):
        for c in self.chains:
            if c[0] == mod:
                return c
        return [mod]

    def diff(self, other):
        added = set(other.all_mods.keys())
        removed = set()
        changed = set()
        for m in self.all_mods.keys():
            if not m in other.all_mods.keys():
                removed.add(m)
            else:
                added.remove(m)
                if not (self.mod2md5[m] == other.mod2md5[m]):
                    changed.add(m)
        return (added, removed, changed)


def filter_yang(files, exclude_prefix):
    filtered = list()
    non_imps = set(["organization", "contact", "description", "revision", "typedef", "grouping"])
    augmented_mods = dict()
    mod2md5 = dict()
    for fn in files:
        do_include = True
        checked_type = False
        checked_imports = False
        imports = dict()
        augments = set()
        imp_mod = None
        my_prefix = None
        modname = None
        with open(fn) as f:
            md5 = hashlib.md5()
            for line in f.readlines():
                line = line.strip()
                if len(line) == 0:
                    continue
                md5.update(line.encode())
                if not checked_type:
                    if line.startswith("submodule"):
                        do_include = False
                        checked_type = True
                        break
                    elif line.startswith("module"):
                        modname = line.split()[1]
                        if modname[-1] == "{":
                            modname = modname[:-1]
                        checked_type = True
                elif not checked_imports:
                    if line.startswith("import "):
                        imp_mod = line.split()[1]
                        if imp_mod[-1] == "{":
                            imp_mod = imp_mod[:-1]
                    elif line.startswith("prefix "):
                        prefix = line.split()[1][:-1]
                        if not imp_mod:
                            my_prefix = prefix
                        else:
                            imports[prefix] = imp_mod
                            imp_mod = None
                    elif (not imp_mod) and line.split()[0] in non_imps:
                        checked_imports = True
                elif line.startswith("augment "):
                    line = line.split()[1]
                    if line[0] == '"':
                        line = line[1:-1]
                    for f in re.finditer("/([^/^:]+):", line):
                        prefix = f.group(1)
                        if prefix == my_prefix:
                            continue
                        augmented_mod = imports[prefix]
                        if any((augmented_mod.startswith(excl_pref) for excl_pref in exclude_prefix)):
                            continue
                        augments.add(augmented_mod)
            mod2md5[modname] = md5.digest()
            if do_include:
                filtered.append(fn)
                if len(augments) > 0:
                    augmented_mods[modname] = augments
    return ModulesInfo(augmented_mods, sorted(filtered, reverse=True), mod2md5)

def common_mods(leftmodinfo, rightmodinfo):
    return [m for m in leftmodinfo.all_mods.keys() if m in rightmodinfo.all_mods.keys()]

def common_files(left_files, right_files):
    left_names = [os.path.basename(f) for f in left_files]
    right_names = [os.path.basename(f) for f in right_files]
    return ([f for f in left_files if os.path.basename(f) in right_names], [f for f in right_files if os.path.basename(f) in left_names])

def yang_diff_commits(neddir, from_commit, to_commit="WORKING", include_paths = [], exclude_paths = [], plugin_dir_arg=""):
    left_neddir = common.git_arch(from_commit, neddir=neddir)
    oldmodinfo = find_yang(left_neddir + "/src/yang/*.yang")
    oldy = oldmodinfo.files
    right_neddir = common.git_arch(to_commit, neddir=neddir)
    curmodinfo = find_yang(right_neddir + "/src/yang/*.yang")
    cury = curmodinfo.files
    (left_files, right_files) = common_files(oldy, cury)
    return yang_diff_files(left_files, right_files, include_paths=include_paths, exclude_paths=exclude_paths, plugin_dir_arg=plugin_dir_arg)

def yang_full_schema(neddir, include_paths = [], exclude_paths = [], plugin_dir_arg=""):
    right_neddir = common.git_arch("WORKING", neddir=neddir)
    curmodinfo = find_yang(right_neddir + "/src/yang/*.yang")
    cury = curmodinfo.files
    return yang_diff_files([], cury, include_paths=include_paths, exclude_paths=exclude_paths, plugin_dir_arg=plugin_dir_arg)

def yang_diff_files(left_yang_files, right_yang_files, skip_choice=True, include_paths=[], exclude_paths=[], plugin_dir_arg=""):
    incl_arg = " ".join(["--diff-include=%s" % p for p in include_paths])
    excl_arg = " ".join(["--diff-exclude=%s" % p for p in exclude_paths])
    skip_choice_arg = "--diff-skip-choice" if skip_choice else ""

    left_yang_files_arg = " ".join(["--diff-left=%s" % f for f in left_yang_files]) if (len(left_yang_files) > 0) else "--diff-new"
    right_yang_files_arg = " ".join(right_yang_files)

    left_path_arg = ("--diff-left-path=%s" % os.path.dirname(left_yang_files[0])) if len(left_yang_files) > 0 else ""
    right_path = os.path.dirname(right_yang_files[0])

    cmd = ("YANGERROR=prune_stack yanger -W none %s %s -p %s/src/ncs/yang:%s -f diff --diff-json --diff-keep-ns %s %s %s %s %s 2> /tmp/diff.err" % (plugin_dir_arg, left_path_arg, os.environ['NCS_DIR'], right_path, skip_choice_arg, incl_arg, excl_arg, left_yang_files_arg, right_yang_files_arg))

    if DEBUG:
        print("RUNNING: '%s'" % cmd)

    diff = subprocess.check_output(cmd, shell=True)
    return json.loads(diff)

def get_node(path, node_info_dict):
    if "__NODES__" not in node_info_dict:
        node_info_dict["__NODES__"] = dict()
    nodes = node_info_dict["__NODES__"]
    if path in nodes:
        return nodes[path]
    node_json = node_info_dict[path]
    substmts = []
    in_uses = None
    if "substmts" in node_json:
        substmts = Ystmt.extract_flat_substmts(node_json["substmts"])
    if "in_uses" in node_json:
        in_uses = node_json["in_uses"]
    name = path[path.rindex('/')+1:]
    ystmt = Ystmt(node_json["keyword"], name, in_uses, path, substmts)
    ppath = path[:path.rindex("/")]
    if ystmt.keyword == "leaf" and ppath in node_info_dict:
        parent = get_node(ppath, node_info_dict)
        if parent.keyword == "list" and ystmt.arg in parent.keys:
            ystmt.is_key_leaf = True
    elif ystmt.keyword == "list":
        ystmt.keys = node_json["keys"]
    nodes[path] = ystmt
    return ystmt

def list_keys_changed(path, oldn, newn, old_node_info, new_node_info):
    if ((oldn.keyword != newn.keyword) or
        ("list" != newn.keyword)):
        return False
    oldkey_names = old_node_info[path]["keys"]
    newkey_names = new_node_info[path]["keys"]
    if (oldkey_names != newkey_names):
        return True
    return False

def list_keys_type_narrowed(path, oldn, newn, old_node_info, new_node_info):
    if ((oldn.keyword != newn.keyword) or
        ("list" != newn.keyword)):
        return False
    if list_keys_changed(path, oldn, newn, old_node_info, new_node_info):
        return True
    newkey_names = new_node_info[path]["keys"]
    for p in ["%s/%s" % (path, key) for key in newkey_names]:
        if ((p in old_node_info) and (p in new_node_info)):
            narrowed = type_narrowed(get_node(p, old_node_info), get_node(p, new_node_info))
            if narrowed:
                return "%s_%s" % (p[p.rindex("/")+1:], narrowed)
    return None

integer_types = ["uint8", "uint16", "uint32", "uint64", "int8", "int16", "int32", "int64"]

def type_range(type_node):
    range_node = type_node.get("range")
    # TODO: handle split ranges and or explicit values (i.e. values/ranges split with '|')
    if range_node and (not "|" in range_node.arg) and (".." in range_node.arg):
        return tuple([int(v) for v in range_node.arg.split("..")])
    else:
        is_unsigned = type_node.arg.startswith("u")
        bits = int(re.match("u?int([0-9]+)", type_node.arg).group(1))
        if not is_unsigned:
            bits -= 1
        pow = 1 << bits
        min = 0 if is_unsigned else -pow
        max = pow - 1
        return (min, max)

def integer_narrowing(oldt, newt):
    if ((not oldt.arg in integer_types) or
        (not newt.arg in integer_types)):
        return False
    (newlo, newhi) = type_range(newt)
    (oldlo, oldhi) = type_range(oldt)
    if ((oldlo < newlo) or
        (oldhi > newhi)):
        return True
    return False

def enum_narrowing(oldt, newt):
    if ((oldt.arg != newt.arg) or
        (newt.arg != "enumeration")):
        return False
    if len(oldt.subs) > len(newt.subs):
        return True
    return any([l.arg != r.arg for (l, r) in zip(oldt.subs, newt.subs)])

def string_shortened(oldt, newt):
    def strlen(len_stmt):
        min_len = 0
        max_len = sys.maxint
        if len_stmt:
            if ".." in len_stmt.arg:
                (min_len, max_len) = tuple([int(v) for v in len_stmt.arg.split("..")])
            else:
                min_len = max_len = int(len_stmt.arg)
        return (min_len, max_len)
    (old_min_len, old_max_len) = strlen(oldt.get("length"))
    (new_min_len, new_max_len) = strlen(newt.get("length"))
    return ((old_min_len < new_min_len) or
            (old_max_len > new_max_len))

def type_narrowed(oldn, newn):
    if ((oldn.keyword != newn.keyword) or
        ("leaf" != newn.keyword)):
        return False
    oldtype = oldn.get("type")
    newtype = newn.get("type")
    narrow_cause = None
    if (oldtype != newtype):
        if integer_narrowing(oldtype, newtype):
            narrow_cause = "integer_narrow"
        elif enum_narrowing(oldtype, newtype):
            narrow_cause = "enumeration_narrow"
        elif string_shortened(oldtype, newtype):
            narrow_cause = "string_narrow"
        elif ((oldtype.arg != newtype.arg) and
              ((oldtype.arg == "empty") or ((newtype.arg != "string") and (newtype.arg != "union")))):
            narrow_cause  = "general_narrow_%s_%s" % (oldtype.arg, newtype.arg)
    return narrow_cause

def num_elements_shrunk(oldn, newn):
    old_min_elmts = oldn.get("min-elements")
    new_min_elmts = newn.get("min-elements")
    old_max_elmts = oldn.get("max-elements")
    new_max_elmts = newn.get("max-elements")
    old_min_elmts = int(old_min_elmts.arg) if old_min_elmts else 0
    new_min_elmts = int(new_min_elmts.arg) if new_min_elmts else 0
    old_max_elmts = int(old_max_elmts.arg) if old_max_elmts else sys.maxint
    new_max_elmts = int(new_max_elmts.arg) if new_max_elmts else sys.maxint
    return ((old_min_elmts < new_min_elmts) or
            (old_max_elmts > new_max_elmts))

def presence_changed(oldn, newn):
    if ((oldn.keyword != newn.keyword) or
        ("container" != newn.keyword)):
        return False
    old_pres = oldn.get("presence")
    new_pres = newn.get("presence")
    return ((old_pres != new_pres) and
            ((old_pres == None) or (new_pres == None)))

def mandatory_added(oldn, newn):
    old_mand = oldn.get("mandatory")
    new_mand = newn.get("mandatory")
    return ((old_mand != new_mand) and
            ((old_mand == None) or
             (old_mand.arg != "true")))

def must_added(oldn, newn):
    old_must = oldn.get("must")
    new_must = newn.get("must")
    return ((old_must == None) and
            (new_must != None))

def print_diff(path, oldn, newn, indent="", outbuf=None, context=False):
    oldy = "\n".join(oldn.emit()) + "\n"
    newy = "\n".join(newn.emit()) + "\n"
    path = "/" + path[path.index("}")+1:]
    tmpdir = tempfile.mkdtemp()
    with open("%s/OLD" % tmpdir, "w") as f:
        f.write(oldy)
    with open("%s/NEW" % tmpdir, "w") as f:
        f.write(newy)
    diff = subprocess.check_output("diff %s%s/OLD %s/NEW || true " % ("-c " if context else "", tmpdir, tmpdir), shell=True)
    if (diff.strip() != ""):
        diff = diff.split("\n")
        line = bold_str("%sDiff in %s:" % (indent, path))
        if outbuf:
            outbuf.append(line)
        else:
            print_line(line)
        for l in diff:
            if not context:
                if re.match("^[0-9]+(?:a|c|d)[0-9]+$", l):
                    continue
                l = re.sub("^>( .*)$", "+\\1", l)
                l = re.sub("^<( .*)$", "-\\1", l)
            else:
                if "/OLD" in l:
                    l = "*** <old model> ***"
                elif "/NEW" in l:
                    l = "--- <new model> ---"
            l = "%s%s" % (indent, l)
            if outbuf:
                outbuf.append(l)
            else:
                print_line(l)

def print_verbose_diff(json_diff, context=False):
    new_node_info = json_diff["new_node_info"]
    old_node_info = json_diff["old_node_info"]
    diff_nodes = json_diff["diff_nodes"]
    if len(diff_nodes) > 0:
        print_line("")
        print_line(bold_str("Detailed diffs follow"))
        print_line("")
        for p in sorted(diff_nodes):
            newn = get_node(p, new_node_info)
            oldn = get_node(p, old_node_info)
            print_diff(p, oldn, newn, context=context)

def incompatible_nodes(json_diff):
    incompat_nodes = json_diff["incompat_nodes"]
    # diff_nodes = json_diff["diff_nodes"]
    # new_node_info = json_diff["new_node_info"]
    # old_node_info = json_diff["old_node_info"]
    # for p in diff_nodes:
    #     if len(is_incompatible(p, new_node_info, old_node_info)) > 0:
    #         incompat_nodes.append(p)
    return incompat_nodes

def is_incompatible(p, new_node_info, old_node_info):
    newn = get_node(p, new_node_info)
    oldn = get_node(p, old_node_info)
    incompats = list()
    type_narrowing = type_narrowed(oldn, newn)
    list_keys_narrowing = list_keys_type_narrowed(p, oldn, newn, old_node_info, new_node_info)
    if (mandatory_added(oldn, newn)):
        incompats.append("mandatory_added")
    if (must_added(oldn, newn)):
        incompats.append("must_added")
    if type_narrowing:
        incompats.append(type_narrowing)
    if list_keys_changed(p, oldn, newn, old_node_info, new_node_info):
        incompats.append("list_keys_changed")
    elif list_keys_narrowing:
        incompats.append("list_key_%s" % list_keys_narrowing)
    if presence_changed(oldn, newn):
        incompats.append("presence_changed")
    if (newn.keyword != oldn.keyword):
        incompats.append("keyword_changed_%s_%s" % (oldn.keyword, newn.keyword))
    if num_elements_shrunk(oldn, newn):
        incompats.append("num_elements_shrunk")
    return incompats

i_descriptions = {
    "mandatory_added"         : "An existing node can not be changed to mandatory",
    "must_added"              : "An existing node can not have a must expression added",
    "list_keys_changed"       : "The keys of a list can't be changed",
    "presence_changed"        : "An existing container can't have 'presence' added/removed",
    "num_elements_shrunk"     : "The max/min-elements range of a node can't be shrunk",
    "enum_change"             : "An enumeration can't change order or have elements removed."
}
def incompatible_desc(icause):
    desc = "unknown"
    if "_narrow" in icause:
        if "list_key_" in icause:
            desc = "The type of key '%s' in list was 'narrowed'" % icause.split("_")[2]
        elif "general" in icause:
            (oldt, newt) = tuple(icause.split("_")[2:])
            desc = "The change of type from %s to %s is not allowed" % (oldt, newt)
        else:
            desc = "The %s type of a node cannot be 'narrowed'" % icause.split("_")[0]
    elif "keyword_changed_" in icause:
        (oldk, newk) = tuple(icause.split("_")[2:])
        desc = "A node's keyword can't be changed from %s to %s" % (oldk, newk)
    else:
        desc = i_descriptions[icause]
    return desc

def descs2key(descs):
    h = 0
    for d in descs:
        h = h ^ hash(d)
    return h

def print_incompatible_nodes(incompat_nodes, old_node_info, new_node_info, outbuf=None, strip_namespaces=False, regex_compress=[], compact_groupings=False):
    incompat_paths = dict()
    for p in incompat_nodes:
        incompats = is_incompatible(p, new_node_info, old_node_info)
        if "enum_change" in incompat_nodes[p]:
            incompats.append("enum_change")
        descs = list()
        for ic in incompats:
            descs.append(incompatible_desc(ic))
        key = descs2key(descs)
        if key not in incompat_paths:
            incompat_paths[key] = (descs, list())
        (_, paths) = incompat_paths[key]
        paths.append(p)

    do_print = False
    if outbuf is None:
        do_print = True
        outbuf = list()

    outbuf.append("")

    for (descs, paths) in incompat_paths.values():
        if (len(descs) == 1):
            s = "  Incompatible diff: %s" % descs[0]
            if do_print:
                s = bold_str(s)
            outbuf.append(s)
        else:
            s = "  Incompatible diffs:"
            if do_print:
                s = bold_str(s)
            outbuf.append(s)
            for d in descs:
                outbuf.append("  " + d)
        tmpbuf = list()
        print_paths("", paths, new_node_info, tmpbuf, strip_namespaces=strip_namespaces, regex_compress=regex_compress, compact_groupings=compact_groupings)
        tmpbuf = tmpbuf[1:] # strip title
        for l in tmpbuf:
            outbuf.append(l)
        outbuf.append("")

    if do_print:
        for l in outbuf:
            print_line(l)

def compact_rem_nodes(rem_nodes, old_node_info, keep_nonpresence=False):
    rem_lists = [p for p in rem_nodes if old_node_info[p]["keyword"] == "list"]
    compact_rem_nodes = list(rem_lists)
    for rem_leaf in rem_nodes:
        if not any([rem_leaf.startswith(rem_list) for rem_list in rem_lists]):
            compact_rem_nodes.append(rem_leaf)
    if not keep_nonpresence:
        for p in list(compact_rem_nodes):
            n = get_node(p, old_node_info)
            if n.keyword == "container" and not n.is_presence_container():
                compact_rem_nodes.remove(p)
    return compact_rem_nodes

def print_removed_nodes(rem_nodes, old_node_info, strip_namespaces=False):
    outbuf = list()
    if len(rem_nodes) > 0:
        print_paths("Removed", rem_nodes, old_node_info, outbuf, strip_namespaces=strip_namespaces)
        print_line(bold_str("Removing nodes in model is not allowed") + "\n".join(outbuf))

if __name__ == '__main__':
    run(sys.argv[1:])
    print("\n".join(outbuf))
