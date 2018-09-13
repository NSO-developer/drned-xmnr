import os
import re

# Compare two config files but ignore comments
def filecmp(a, b):
    return os.system("diff -I '^ *!' -I '^ */\*' %s %s" % (a, b)) == 0

def path_in_prefixes(path, prefixes):
    pathnons = path
    if path.startswith("/{"):
        pathnons = re.sub("{[^}]+?}", "", path)
    for p in prefixes:
        if path.startswith(p) or pathnons.startswith(p):
            return True
    return False

def gen_nodes(schema, skip_nodes, include_prefixes, exclude_prefixes, ntype):
    nodes = schema.list_nodes(ntype=ntype)
    for node in nodes:
        p = node.get_path()
        if (not p in skip_nodes and
            not path_in_prefixes(p, exclude_prefixes) and
            (not include_prefixes or path_in_prefixes(p, include_prefixes))):
            yield node

