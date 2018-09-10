import os
import re
import sys
import pyang
import itertools
from pyang import statements

from .node import drned_node

class Match(object):
    def __init__(self, root=None, depth=None, ntype=None):
        self.root = root
        self.ntype = ntype

    def equals(self, ntype):
        return None == self.ntype or ntype in self.ntype

class Schema(object):
    def __init__(self, name, map_list=[], yangpath=""):
        self.defined_maps = ["avoid_map", "leaf_map", "pattern_map",
                             "type_map", "xpath_map"]
        self.maps = {}
        for map_name,map_def in map_list:
            self.replace_map(map_name, map_def)
        self.node_map = {}
        self.missing_map = {}

        path = os.getenv("NCS_DIR") + "/src/confd/yang"
        if not os.path.exists(path):
            path = os.getenv("NCS_DIR") + "/src/ncs/yang"
        if yangpath != "":
            if type(yangpath) is list:
                yangpath = ':'.join(yangpath)
            path = yangpath + ":" + path
        repos = pyang.FileRepository(path)
        ctx = pyang.Context(repos)
        # String or list?
        if hasattr(name, "lower"):
            filenames = [name]
        else:
            filenames = name
        modules = []

        if len(filenames) == 0:
            text = sys.stdin.read()
            module = ctx.add_module("<stdin>", text)
            assert module is not None
            modules.append(module)

        r = re.compile(r"^(.*?)(\@(\d{4}-\d{2}-\d{2}))?\.(yang|yin)$")
        for filename in filenames:
            fd = open(filename)
            text = fd.read()
            # Submodules should be ignored
            if "belongs-to" in text:
                continue
            m = r.search(filename)
            ctx.yin_module_map = {}
            if m is not None:
                (name, _dummy, rev, format) = m.groups()
                name = os.path.basename(name)
                module = ctx.add_module(filename, text, format, name, rev,
                                        expect_failure_error=False)
            else:
                module = ctx.add_module(filename, text)
            assert module is not None
            self.namespace = module.search_one("namespace").arg
            modules.append(module)

        ctx.validate()
        ctx.errors = []
        self.modules = modules
        self.groupings = {}
        for module in self.modules:
            self.groupings.update(module.i_groupings)

    def append_map(self, map_name, map_def):
        assert map_name in self.defined_maps
        self.maps[map_name].update(map_def)

    def replace_map(self, map_name, map_def):
        assert map_name in self.defined_maps
        self.maps[map_name] = map_def

    def lookup_map(self, map_name, name):
        assert map_name in self.defined_maps
        try:
            return self.maps[map_name][name]
        except KeyError:
            try:
                if "{" in name:
                    while re.match(".*?{([^}]+)}.*?({\\1}).*", name):
                        name = re.sub("(.*?{([^}]+)}.*?)({\\2})(.*)", "\\1\\4", name)
                if name.startswith("/{"):
                    if not "}" in name:
                        raise KeyError();
                    name = "/" + name[name.index("}")+1:]
                return self.maps[map_name][name]
            except KeyError:
                return None

    def get_node(self, path):
        try:
            if path in self.missing_map:
                return None
            return self.node_map[path]
        except KeyError:
            for leaf in self.gen_nodes():
                if path == leaf.path:
                    return leaf
            self.missing_map[path] = True
            return None

    def gen_nodes(self, root=None, ntype=None):
        match = Match(root=root, ntype=ntype)
        if match.root == None:
            path = None
        else:
            path = match.root.split("/")
            if path != [] and path[0] == "":
                path = path[1:]

        for module in self.modules:
            chs = [ch for ch in module.i_children
                   if ch.keyword in statements.data_definition_keywords]
            if path not in [None, []]:
                chs = [ch for ch in chs if ch.arg == path[0]]
                path = path[1:]
            if len(chs) > 0:
                for y in _gen_children(chs, path):
                    if match.equals(ntype=y.keyword):
                        yield drned_node(self, y)

        for augment in module.search("augment"):
            if (hasattr(augment.i_target_node, "i_module") and
                augment.i_target_node.i_module not in self.modules):
                for y in _gen_children(augment.i_children, path):
                    if match.equals(ntype=y.keyword):
                        yield drned_node(self, y)

    def list_nodes(self, root=None, ntype=None):
        return [node for node in itertools
                .islice(self.gen_nodes(root=root, ntype=ntype), 0, None)]

    def get_grouping(self, node_pos):
        groupings = sorted([(g.pos.line, g) for (n, g) in self.groupings.iteritems()])
        prev = None
        for (g_pos, g) in groupings:
            if g_pos > node_pos:
                break
            prev = g
        return prev

def _gen_children(i_children, path):
    for ch in i_children:
        for y in _gen_node(ch, path):
            yield y

def _gen_node(s, path):
    yield s
    if hasattr(s, "i_children"):
        chs = s.i_children
        if path is not None and len(path) > 0:
            chs = [ch for ch in chs
                   if ch.arg == path[0]]
            path = path[1:]
        for y in _gen_children(chs, path):
            yield y
