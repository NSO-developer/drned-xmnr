import pytest
import inspect

from .node import drned_node

class Walker(object):
    def __init__(self, leaves, serial=False):
        self.leaves = leaves
        self.log = False
        self.init_walk()

    def init_walk(self):
        for leaf in self.leaves:
            leaf.init_walk()
            leaf.participated = False
            leaf.valid = False
            leaf.done = False
        self.choices = {}

    def invite_leaves(self):
        # Generate values for all leaves
        self.say("%s()" % inspect.stack()[0][3])
        self.pruned = False
        for leaf in self.leaves:
            if leaf.join_walk(self.choices):
                self.say("%s is invited with value \"%s\"" %
                         (leaf.path, leaf.value))
                for p in leaf.gen_parents(with_self=True):
                    p.valid = True

    def prune_when_must(self):
        # Update according to when/must
        self.say("%s()" % inspect.stack()[0][3])
        for leaf in self.leaves:
            if not leaf.valid:
                continue
            for p in leaf.gen_parents(with_self=True):
                # When
                for when in p.get_when():
                    if not p.evaluate_xpath(when, must=False):
                        # Invalidate entire path from this point to
                        # the leaf
                        for q in leaf.gen_parents(with_self=True):
                            # Extra test here, not required but will
                            # create cleaner logs without duplicates
                            if q.valid:
                                self.say(("%s is disabled due to when \"%s\" "
                                          + "being false") % (q.path, when))
                                q.disable_node()
                                self.pruned = True
                            if p == q:
                                break
                # Must
                for must in p.get_must():
                    if p.evaluate_xpath(must, must=True):
                        self.say("%s triggers must \"%s\"" % (p.path, must))
                        self.pruned = True

    def prune_incomplete(self):
        self.say("%s()" % inspect.stack()[0][3])
        # Remove incomplete containers/lists
        incomplete_leaf = None
        for ix,leaf in enumerate(self.leaves):
            leaf.is_incomplete = False
            parent = leaf.get_parent()
            incomplete_parent = None if not incomplete_leaf \
                                else incomplete_leaf.get_parent()
            # Trigger if last leaf was incomplete and hitting an
            # invalid or empty leaf, or leaving the top container
            if incomplete_leaf \
               and (not leaf.is_active() \
                    and (leaf.joined_walk \
                         or leaf.unjoin_reason == "full_command") \
                    or incomplete_parent.get_top_parent() !=
                       parent.get_top_parent()):
                # The last leaf is incomplete so remove all incomplete
                # leaves by looping backwards in list
                for i in range(incomplete_index, -1, -1):
                    to_remove = self.leaves[i]
                    if not to_remove.is_incomplete \
                       or to_remove.get_parent() != incomplete_parent:
                        break
                    if to_remove.disable_tree():
                        self.say("%s is disabled due to incomplete leaf %s" %
                                 (to_remove.path, incomplete_leaf.path))
                        self.pruned = True
                    i -= 1
                incomplete_leaf = None
            if leaf.is_active():
                incomplete_leaf = None
            # Check if current leaf is incomplete
            if leaf.is_active() \
               and (leaf.get_tailf(("tailf-common",
                                    "cli-incomplete-command")) \
                    or (parent != None \
                        and parent.get_tailf(("tailf-common",
                                              "cli-incomplete-command")) \
                        and (parent.get_tailf(("tailf-common",
                                               "cli-drop-node-name")) \
                             or parent.is_list()) \
                        and not leaf.get_tailf(("tailf-common",
                                                "cli-full-command")) \
                        and leaf.stmt == parent.stmt.i_children[0])):
                incomplete_leaf = leaf
                incomplete_index = ix
                incomplete_leaf.is_incomplete = True

    def prune_sequence(self):
        self.say("%s()" % inspect.stack()[0][3])
        # In containers with tailf:cli-sequence-commands, remove all
        # stuff that follows an invalid node
        for leaf in self.leaves:
            if not leaf.valid:
                continue
            for parent in leaf.gen_parents():
                if parent.stmt.keyword in ["container", "list"] \
                   and parent.get_tailf(("tailf-common",
                                         "cli-sequence-commands")):
                    sequence_break = None
                    for c in parent.stmt.i_children:
                        child = drned_node(parent.schema, c)
                        if child.get_tailf(("tailf-common",
                                            "cli-break-sequence-commands")):
                            break
                        if child.valid and sequence_break:
                            if child.disable_tree():
                                self.say(("%s is disabled due to sequence "
                                          +"break at %s") %
                                         (child.path, sequence_break.path))
                                self.pruned = True
                        if not child.is_active() \
                           and not child.get_tailf(("tailf-common",
                                                "cli-optional-in-sequence")):
                            sequence_break = child

    def prune_full(self):
        self.say("%s()" % inspect.stack()[0][3])
        # Prune all leaves following a cli-full-command
        for leaf in self.leaves:
            parent = leaf.get_parent()
            if leaf.valid and parent != None \
               and parent.get_tailf(("tailf-common", "cli-compact-syntax")):
                still_valid = True
                for c in parent.stmt.i_children:
                    child = drned_node(parent.schema, c)
                    if hasattr(child, "valid") and child.valid:
                        if not still_valid:
                            if child.disable_tree():
                                self.say(("%s is disabled due to " +
                                          "tailf:cli-full-command") %
                                         child.path)
                                self.pruned = True
                        if child.get_tailf(("tailf-common",
                                            "cli-full-command")) \
                            and not child.get_tailf(("tailf-common",
                                                     "cli-hide-in-submode")):
                            still_valid = False

    def prune_leafref(self):
        self.say("%s()" % inspect.stack()[0][3])
        # Get leafrefs when the dust has settled
        for leaf in self.leaves:
            if leaf.valid and hasattr(leaf, "is_leafref") and leaf.is_leafref:
                tailf = leaf.get_tailf(("tailf-common", "non-strict-leafref"))
                if tailf:
                    path = tailf.get_value("path")
                    target = leaf.get_node(path)
                elif leaf.get_type() == "leafref":
                    t,_ = leaf.stmt.i_leafref_ptr
                    target = drned_node(leaf.schema, t)
                else:
                    assert False
                # A leafref must have a valid target
                if hasattr(target, "valid") and target.valid:
                    leaf.value = target.value
                elif leaf.disable_node():
                    self.say("%s is disabled due to missing leafref" %
                             leaf.path)
                    self.pruned = True

    def prune_avoid(self):
        self.say("%s()" % inspect.stack()[0][3])
        # Remove leaves according to avoid_map
        for leaf in self.leaves:
            if leaf.valid:
                # Mentioned in avoid map?
                path = leaf.path
                ns = ""
                if path.startswith("/{"):
                    ns = path[:path.index("}")+1]
                    path = "/" + path[path.index("}")+1:]
                while len(path) > 0:
                    # Check both for full path and single node match
                    if leaf.schema.lookup_map("avoid_map", ns + path) \
                       or leaf.schema.lookup_map("avoid_map",
                                                 ns + path.split("/")[-1]):
                        if leaf.disable_node():
                            self.say("%s is disabled due to avoid map" %
                                     leaf.path)
                            self.pruned = True
                    path = "/".join(path.split("/")[:-1])

    def next_iteration(self):
        more = False
        self.say("%s()" % inspect.stack()[0][3])
        # Advance to next iteration
        for leaf in self.leaves:
            if leaf.joined_walk:
                try:
                    leaf.value = leaf.walk.next()
                except StopIteration:
                    leaf.done_walk(self.choices)
                    # Add dummy laps while other leaves not done
                    leaf.init_walk()
            if leaf.valid:
                leaf.participated = True
            if leaf.participated and not leaf.done:
                more = True
            leaf.valid = False
        for choice in self.choices:
            if not self.choices[choice].done:
                more = True
        return more

    def gen_walk(self):
        self.say("%s()" % inspect.stack()[0][3])
        while True:
            # Prepare one iteration
            self.invite_leaves()
            self.pruned = True
            while self.pruned:
                self.pruned = False
                self.prune_when_must()
                self.prune_incomplete()
                self.prune_sequence()
                self.prune_full()
                self.prune_leafref()
                self.prune_avoid()

            # Then yield the result
            for leaf in self.leaves:
                if leaf.valid:
                    yield leaf
            # None means end of one iteration
            yield None

            # Next iteration
            if not self.next_iteration():
                self.statistics()
                break

    def gen_containers(self):
        last_parent = None
        for leaf in self.leaves:
            if leaf.valid:
                parent = leaf.get_parent()
                if parent != last_parent:
                    yield parent
                last_parent = parent

    def statistics(self):
        total = 0
        omitted = []
        for leaf in self.leaves:
            total += 1
            if not leaf.participated:
                omitted.append(leaf.path)
        self.total = total
        self.omitted = omitted

    def say(self, what):
        if self.log:
            print(what)
