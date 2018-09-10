import os
import re
import pytest
import itertools
from pyang import statements

from .choice import Choice, get_choice

class Node(object):
    def __init__(self, schema, stmt, register=True):
        self.schema = schema
        self.stmt = stmt
        self.path = _stmt_get_path(self.stmt)
        self.participated = False
        stmt.drned_node = self
        if register \
           and stmt.keyword in ['container', 'leaf', 'leaf-list', 'list']:
            assert self.path not in schema.node_map
            schema.node_map.update({self.path : self})
            schema.groupings.update(stmt.i_groupings)

    def __str__(self):
        return self.path

    def __eq__(self, other):
        return self.__hash__() == other.__hash__()

    def __ne__(self, other):
        return self.__hash__() != other.__hash__()

    def __hash__(self):
        h = _hash_stmt(self.stmt)
        if self.is_list():
            for c in self.get_children():
                if c.is_key():
                    h ^= hash(c)
        return h

    def diff(self, other, deep=False):
        diff = {}
        skips = _skip_substmts + ["type", "key"]
        oursubs = set([Node(self.schema, s, register=False) for s in self.stmt.substmts if not s.keyword in skips])
        othersubs = set([Node(self.schema, s, register=False) for s in other.stmt.substmts if not s.keyword in skips])
        added = oursubs - othersubs
        deleted = othersubs - oursubs
        changed = set()
        for an in added.copy():
            for dn in deleted.copy():
                if (an.stmt.keyword == dn.stmt.keyword):
                    changed.add(an)
                    added.discard(an)
                    deleted.discard(dn)
        if len(added) > 0:
            diff["added"] = added
        if len(deleted) > 0:
            diff["deleted"] = deleted
        if len(changed) > 0:
            diff["changed"] = changed
        ourkw = self.stmt.keyword
        otherkw = other.stmt.keyword
        if ourkw != otherkw:
            diff["keyword"] = (otherkw, ourkw)
        ourtype = self.get_subnode("type")
        othertype = other.get_subnode("type")
        if ourtype != othertype:
            diff["type"] = (othertype, ourtype)
        if self.is_list():
            ourkey = self.get_subnode("key")
            otherkey = other.get_subnode("key")
            if ourkey != otherkey:
                diff["list_key"] = (otherkey, ourkey)
            ourkeys = set([k for k in self.get_children() if k.is_key()])
            otherkeys = set([k for k in other.get_children() if k.is_key()])
            diff["list_key_leaves"] = (otherkeys, ourkeys)
        return diff

    def get_arg(self):
        return self.stmt.arg

    def get_keyword(self):
        return self.stmt.keyword

    def get_path(self):
        return _stmt_get_path(self.stmt, raw=False)

    def is_config(self):
        is_oper = hasattr(self.stmt, "i_config") and not self.stmt.i_config
        return (not is_oper and
                (not self.stmt.search_one("config") or
                 self.stmt.search_one("config").arg != "false"))

    def get_top_parent(self):
        p = self.path
        if p.startswith("{"):
            p = p[p.index("}")+1:]
        return p.split("/")[1]

    def get_raw_path(self):
        return _stmt_get_path(self.stmt, raw=True)

    def get_pos(self):
        return _stmt_get_pos(self.stmt)

    def get_parent(self):
        for node in self.gen_parents():
            if node.stmt.keyword in ["container", "list"]:
                return node
        return None

    def get_children(self):
        if hasattr(self.stmt, "i_children"):
            return [drned_node(self.schema, c) for c in self.stmt.i_children]
        else:
            return []

    def get_container(self):
        for node in self.gen_parents():
            if node.stmt.keyword == "container":
                return node
        return None

    def get_list(self):
        for node in self.gen_parents():
            if node.stmt.keyword == "list":
                return node
        return None

    # Get data relative to the current leaf node

    def get_default(self):
        return self.get_value("default")

    def get_fraction_digits(self):
        return self.get_subnode("type").get_value("fraction-digits")

    def get_length(self):
        return self.get_subnode("type").get_value("length")

    def get_must(self):
        return self.get_values("must")

    def get_pattern(self):
        return self.get_subnode("type").get_value("pattern")

    def get_range(self):
        return self.get_subnode("type").get_value("range")

    def get_tailf(self, ext):
        return self.get_subnode(ext)

    def get_type(self):
        return self.get_value("type")

    def get_when(self):
        return self.get_values("when")

    # Get iteration values for schema types

    def get_enum(self):
        typenode = self.get_subnode("type")
        if typenode != None:
            return [e.arg for e in typenode.stmt.substmts
                    if e.keyword == "enum"]
        return []

    def get_union(self):
        stmt = self.stmt
        nodes = []
        typenode = self.get_subnode("type")
        if typenode != None:
            for s in typenode.stmt.substmts:
                if s.keyword == "type":
                    # Create a fake parent
                    parent = statements.Statement(stmt.top, stmt.parent,
                                                  stmt.pos, stmt.keyword,
                                                  stmt.arg)
                    parent.substmts.append(s)
                    nodes.append(drned_node(self.schema, parent,
                                            register=False))
        return nodes

    def get_integer(self):
        r = self.get_range()
        if r != None:
            if r.find("|") >= 0:
                # Set of discrete values
                value = []
                for s in r.split("|"):
                    for t in s.split(".."):
                        value.append(t.strip())
                return value
            elif r.find("..") >= 0:
                # Normal range
                rs = r.split("..")
                rs = [s.strip() for s in rs]
                return [rs[0], str((int(rs[1]) + int(rs[0])) / 2), rs[1]]
            elif re.match("\\-?\\d+", r):
                return [r.strip()]
            else:
                assert False
        # No range, use min/max for type
        typename = self.get_type()
        integer = re.match("u?int(\\d+)", typename)
        assert integer
        bits = int(integer.group(1))
        if typename.startswith("u"):
            return ["0", str(2**(bits-2)), str((2**bits)-1)]
        else:
            return [str(-(2**(bits-1))), str(2**(bits-2)),str((2**(bits-1))-1)]

    def get_decimal(self):
        value = None
        frac = self.get_fraction_digits()
        r = self.get_range()
        if r != None:
            f = 1 if frac == None else int(frac)
            if r.find("..") >= 0:
                # Range
                rs = r.split("..")
                value = ["%.*f" % (f, float(rs[0])),
                         "%.*f" % (f, (float(rs[1]) + float(rs[0])) / 2),
                         "%.*f" % (f, float(rs[1]))]
            elif r.find("|") >= 0:
                # Set of discrete values
                value = [s.strip() for s in r.split("|")]
            elif re.match("\\d+(\\.\\d+)", r):
                value = [r.strip()]
            else:
                assert False
            # Add fraction if not present
            if value != None:
                tail = "." + ("0" * f)
                return [(v + ("" if v.find(".") >= 0 else tail)) for v in value]
        # No range, use min/max for type
        typename = self.get_type()
        value = ["-9223372036854775808",
                 "1111111111111111111",
                 "9223372036854775807"]
        if frac != None:
            f = int(frac)
            val = []
            for v in value:
                val.append(v[:len(v)-f] + "." + v[len(v)-f:])
            value = val
        return value

    def get_string(self):
        pattern = self.get_pattern()
        if pattern == None:
            # Create a value from the name and parent
            string = self.path.upper()[1:]
            string = "-".join(string.split("/")[-2:])
            length = self.get_length()
            if length != None:
                # Truncate if too long
                length = length.split("..")[1].strip()
                string = string[:int(length)-1]
            return [string + "%d"]
        else:
            value = self.schema.lookup_map("pattern_map", pattern)
            if value == None:
                # Regular expressions are not handled, so on error, the
                # user should create a new entry in the pattern_map.
                pytest.fail("Missing pattern map entry at %s (type %s): %s" %
                            (self.path, self.get_type(), pattern))
            else:
                return value

    # Select values from the iteration

    def get_all(self):
        return [w for w
                in itertools.islice(self.gen_walk(), 0, None)]

    def get_min(self):
        return [w for w
                in itertools.islice(self.gen_walk(), 0, None)][0]

    def get_max(self):
        return [w for w
                in itertools.islice(self.gen_walk(), 0, None)][-1]

    def get_sample(self):
        default = self.get_default()
        if default:
            return default
        v = [w for w in itertools.islice(self.gen_walk(), 0, None)]
        return v[len(v)/2]

    # Get generic nodes and values

    def get_subnode(self, name):
        return drned_node(self.schema, self.stmt.search_one(name))

    def get_value(self, name):
        node = self.stmt.search_one(name)
        return node.arg if node else None

    def get_values(self, name):
        nodes = self.stmt.search(name)
        return [n.arg for n in nodes]

    def gen_subnode(self, ntype):
        for ch in self.stmt.i_children:
            if not ntype or ch.keyword in ntype:
                yield drned_node(self.schema, ch)

    # Is

    def is_key(self):
        return hasattr(self.stmt, "i_is_key") and self.stmt.i_is_key

    def is_leaf(self):
        return self.stmt.keyword == "leaf"

    def is_leaflist(self):
        return self.stmt.keyword == "leaf-list"

    def is_list(self):
        return self.stmt.keyword == "list"

    def is_container(self):
        return self.stmt.keyword == "container"

    def is_active(self):
        return hasattr(self, "valid") and self.valid \
            and (not self.is_leaf() or self.value != "<empty-false>")

    def is_mandatory(self):
        m = self.get_value("mandatory")
        return m == "true"

    def is_presence_container(self):
        return self.get_value("presence")

    def has_leaf_value(self, value):
        return self.is_leaf() and self.valid and self.value == value

    def get_leaf_value(self):
        return self.value if self.is_leaf() and self.valid else None

    def set_leaf(self, value):
        self.valid = True
        if value != None:
            self.value = value

    def has_parent(self, parent):
        for node in self.gen_parents():
            if node == parent:
                return True
        return False

    def nearest_uses(self):
        allu = self.all_uses()
        nearest = None
        if allu:
            nearest = allu[-1]
        return nearest

    def all_uses(self):
        return [drned_node(self.schema, ustmt, register=False) for ustmt in self.stmt.i_uses] \
            if (hasattr(self.stmt, "i_uses") and
                self.stmt.i_uses) else []

    def get_grouping_path(self):
        grp_path = None
        if hasattr(self.stmt, "i_uses_top"):
            stmt = self.stmt
            grp_path = stmt.arg
            while not stmt.i_uses_top:
                stmt = stmt.parent
                if not (stmt.keyword in ["choice", "case"]):
                    grp_path = stmt.arg + "/" + grp_path
        return grp_path

    def search_grouping(self, name):
        grp = statements.search_grouping(self.stmt, name)
        if grp is None:
            # hack to support nested grouping in grouping
            alluses = self.all_uses()
            if len(alluses) > 1:
                outerg = alluses[-2].stmt.arg
                ogrp = self.search_grouping(outerg)
                allgrps = ogrp.stmt.search("grouping")
                for cg in allgrps:
                    if cg.arg == name:
                        grp = cg
                        break
        if grp:
            grp = drned_node(self.schema, grp)
        return grp


    # Walk helpers

    def gen_parents(self, with_self=False):
        if with_self:
            yield self
        stmt = self.stmt
        while stmt.parent != None:
            stmt = stmt.parent
            yield drned_node(self.schema, stmt)

    def gen_children(self, with_self=False):
        if with_self:
            yield self
        for child in _gen_children(self.stmt):
            yield drned_node(self.schema, child)

    def init_walk(self):
        self.walk = self.gen_walk()
        self.value = self.walk.next()

    def join_walk(self, choices):
        child = self
        child.has_done_walk = False
        for parent in child.gen_parents():
            # First, check for the normal "choice" keyword
            if parent.get_keyword() == "choice":
                # Requires a choice
                choice = get_choice(choices, parent.get_raw_path(),
                                    parent.get_children(), "choice")
                if not choice.joined(child, "choice"):
                    self.joined_walk = False
                    self.unjoin_reason = "choice"
                    return False

            # Then, check if there are any cli-full-command leaves
            # that cannot be set simultaneously and therefore require
            # a pseudo-choice
            if parent.get_keyword() in ["container", "list"] \
               and child.get_keyword() in ["leaf", "leaf-list"] \
               and parent.get_tailf(("tailf-common", "cli-compact-syntax")) \
               and parent.get_tailf(("tailf-common", "cli-reset-container")) \
               and child.get_tailf(("tailf-common", "cli-full-command")):
                # Get all cli-full-command leaves
                children = [c for c in parent.get_children() \
                            if c.get_tailf(("tailf-common",
                                            "cli-full-command")) \
                            and not c.get_tailf(("tailf-common",
                                                 "cli-hide-in-submode"))]
                # Now we have a list of leaves that must be selected
                # exclusively, so put them in a pseudo-choice
                if children != []:
                    choice = get_choice(choices, parent.get_raw_path(),
                                        [None] + children, "full_command")
                    if not choice.joined(child, "full_command"):
                        self.joined_walk = False
                        self.unjoin_reason = "full_command"
                        return False
            child = parent
        self.joined_walk = True
        return True

    def done_walk(self, choices):
        self.has_done_walk = True
        self.done = True
        for parent in self.gen_parents():
            raw_path = parent.get_raw_path()
            if raw_path in choices:
                choice = choices[raw_path]
                if choice.increment():
                    return False
        return True

    def gen_walk(self):
        for value in self.gen_walk_list():
            for v in value:
                yield v

    def gen_walk_list(self):
        # Hints take preference
        value = self.schema.lookup_map("leaf_map", self.path)
        if value != None:
            yield value
        else:
            # Ignore annotations
            keyword = self.stmt.keyword
            if keyword == "default":
                return
            if keyword == "mandatory":
                return
            if "".join(keyword).startswith("tailf"):
                return
            # Select according to type
            for y in self.handle_type():
                yield y

    def handle_type(self):
        typename = self.get_type()
        assert typename != None
        if typename == "leafref" \
           or self.get_tailf(('tailf-common', 'non-strict-leafref')):
            # Will be handled later
            self.is_leafref = True
            value = ["<leafref>"]
        elif self.schema.lookup_map("type_map", typename):
            value = self.schema.lookup_map("type_map", typename)
        elif typename == "string":
            value = self.get_string()
        elif re.match("u?int(\\d+)", typename):
            value = self.get_integer()
        elif typename == "decimal64":
            value = self.get_decimal()
        elif typename == "enumeration":
            value = self.get_enum()
        elif typename == "boolean":
            value = ["false", "true"]
        elif typename == "empty":
            value = ["<empty-true>"] if self.is_mandatory() \
                    else ["<empty-false>", "<empty-true>"]
        elif typename == "union":
            nodes = self.get_union()
            for node in nodes:
                for y in node.handle_type():
                    yield y
            return
        elif typename.find(":") >= 0:
            # External types must be mapped in the yang_type_map
            pytest.fail("Missing type map entry at " +
                        self.path + ": " + typename)
        else:
            # Oops, missing in pyang?
            if not hasattr(self.stmt, "i_orig_module"):
                self.stmt.i_orig_module = self.stmt.parent.i_orig_module
            if not hasattr(self.stmt, "i_typedefs"):
                self.stmt.i_typedefs = self.stmt.parent.i_typedefs
            # Typedef?
            typedef = statements.search_typedef(self.stmt, typename)
            if typedef == None:
                statements.print_tree(self.stmt)
                raise Exception("Unexpected type: " + typename)
            t = drned_node(self.schema, typedef)
            for y in t.handle_type():
                yield y
            return
        yield value

    def evaluate_xpath(self, text, must=False):
        # Handle the most common when expressions with a simple regex
        # parser. Must expressions can have side effects and are
        # deferred to the xpath map.
        text = text.strip()
        if not must:
            path = re.match("([\\w\\-\\.\\/:]+)$", text)
            not_path = re.match("not\\(([\\w\\-\\.\\/:]+)\\)$", text)
            compare_path = re.match("([\\w\\-\\.\\/:]+)\\s+=" +
                                    "\\s+\\'([\\w\\-]+)\\'$", text)
            not_compare_path = re.match("not\\(([\\w\\-\\.\\/:]+)\\s+=" +
                                        "\\s+\\'([\\w\\-]+)\\'\\)$", text)
            if path:
                node = self.get_node(path.group(1))
                return node.is_active()
            elif not_path:
                node = self.get_node(not_path.group(1))
                return not node.is_active()
            elif compare_path:
                return self.get_node(compare_path.group(1)).value == \
                       compare_path.group(2)
            elif not_compare_path:
                return not self.get_node(not_compare_path.group(1)).value == \
                           not_compare_path.group(2)
        # Special xpath expressions are handled here. The user should
        # create a new entry for all non-trivial expressions in the
        # xpath_map.
        code = self.schema.lookup_map("xpath_map", text)
        if code == None:
            pytest.fail("Missing xpath map entry at " +
                        self.path + ": " + text)
        retval = None
        try:
            exec(code)
        except:
            pytest.fail("Exception when executing xpath code at " +
                        self.path + ": " + code)
        return retval

    def get_node(self, path):
        path = re.sub("/[^\\/]+:", "/", path)
        if path.startswith("/"):
            path = self.path[:self.path.index("}")+1] + path
        elif not path.startswith("{"):
            path = os.path.normpath(self.path + "/" + path).replace(":/", "://")
        return self.schema.get_node(path)

    def disable_node(self):
        pruned = hasattr(self, "valid") and self.valid
        self.valid = False
        # Disabling a key node means that the list must go
        if self.is_key() and pruned:
            self.get_parent().disable_tree()
        return pruned

    def disable_tree(self):
        pruned = False
        for node in self.gen_children(with_self=True):
            if node.disable_node():
                pruned = True
        return pruned

    def all_done(self):
        for node in self.gen_children(with_self=False):
            if node.get_keyword() in ["leaf", "leaf-list"] \
               and node.joined_walk \
               and not (node.has_done_walk or node.done):
                return False
        return True

# Collection of helpers that operate directly on pyang statements

def drned_node(schema, stmt, register=True):
    if stmt == None:
        return None
    if not hasattr(stmt, "drned_node"):
        stmt.drned_node = Node(schema, stmt, register)
    return stmt.drned_node

def _stmt_get_path(stmt, raw=False):
    path = ""
    nsmodule = stmt.i_module
    while stmt.parent != None:
        if stmt.arg != None \
           and (raw or stmt.keyword not in ["choice", "case"]):
            module = stmt.i_module
            if nsmodule or module:
                if module and (nsmodule != module):
                    nsmodule = module
                ns = nsmodule.search_one('namespace')
                ns = ("{%s}" % ns.arg) if ns else ""
                path = "/%s%s%s" % (ns, stmt.arg, path)
            else:
                path = "/%s%s" % (stmt.arg, path)
        stmt = stmt.parent
    return path

def _stmt_get_pos(stmt):
    return (stmt.pos.ref,stmt.pos.line)

def _stmt_get_value(stmt, name):
    node = stmt.search_one(name)
    return node.arg if node else None

def _gen_children(stmt):
    yield stmt
    if hasattr(stmt, "i_children"):
        for s in stmt.i_children:
            for y in _gen_children(s):
                yield y

_skip_substmts = [
    ("tailf-common", "info"),
    ("tailf-common", "cli-mode-name"),
]
_skip_substmts += statements.data_definition_keywords

def _hash_stmt(stmt):
    h = hash(stmt.keyword)
    h ^= hash(stmt.arg)
    h ^= _hash_substmts(stmt)
    return h

def _hash_substmts(stmt):
    h = 0
    chk_order = False
    if stmt.keyword == 'type' and stmt.arg == 'enumeration':
        chk_order = True
    for s in stmt.substmts:
        if not s.keyword in _skip_substmts:
            if chk_order:
                h += 1 # capture order
            h ^= hash(s.keyword)
            h ^= hash(s.arg)
            if s.substmts:
                h ^= _hash_substmts(s)
    return h
