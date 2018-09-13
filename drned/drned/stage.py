from lxml import etree

import node
import re

class Stage(object):
    XMLNS = "http://tail-f.com/ns/config/1.0"
    XML = "{%s}" % XMLNS
    XMLNSMAP = {None : XMLNS}
    NCSNS = "http://tail-f.com/ns/ncs"
    NCS = "{%s}" % NCSNS
    NCSNSMAP = {None : NCSNS}
    name_instance = 0

    def __init__(self, schema):
        self.sdict = {}
        self.DEV = "{%s}" % schema.namespace
        self.DEVNSMAP = {None : schema.namespace}

    def add_leaf(self, leaf, value=None):
        # Empty type?
        if value == "<empty-false>":
            return
        # Provide sample?
        if value == None:
            value = leaf.get_sample()
        assert value != None
        # Enter sequence number
        value = value.replace("%d", str(Stage.name_instance + 1))
        path = leaf.path
        if "{" in path:
            while re.match(".*?{([^}]+)}.*?({\\1}).*", path):
                path = re.sub("(.*?{([^}]+)}.*?)({\\2})(.*)", "\\1\\4", path)
        if path.startswith("/{"):
            path = "/" + path[path.index("}")+1:]

        # Keys have to be ordered so put the key index in the path to
        # make the correct order when sorted
        if leaf.is_key():
            key_index = None
            # Check which key
            stmt = leaf.stmt
            while stmt.parent != None:
                key = node._stmt_get_value(stmt, "key")
                if key != None:
                    key_index = key.split(" ").index(leaf.get_arg())
                    break
                stmt = stmt.parent
            else:
                assert False
            path = ("/%c".join(path.rsplit("/", 1))) % (int(key_index) + 1)
        self.sdict[path] = value

    def save(self, dev, fname):
        self._xml(dev)
        f = open(fname, "w")
        f.write(etree.tostring(self.root, pretty_print=True))
        f.close()
        self.sdict = {}
        Stage.name_instance = (Stage.name_instance + 1) % 9

    def flush(self, dev):
        self.save(dev, "drned-work/drned-commit.xml")
        dev.load("drned-work/drned-commit.xml")

    def _xml(self, dev):
        root = etree.Element(Stage.XML + "config",
                             nsmap=Stage.XMLNSMAP)
        devices = etree.SubElement(root, Stage.NCS + "devices",
                                   nsmap=Stage.NCSNSMAP)
        device = etree.SubElement(devices, 'device')
        name = etree.SubElement(device, 'name')
        name.text = dev.name
        config = etree.SubElement(device, 'config')
        xml_map = {}
        for s in sorted(self.sdict):
            sxml = "".join([c for c in s if ord(c) >= ord(" ")])
            elems = sxml.split("/")[1:]
            for i,elem in enumerate(elems):
                path = "/".join(elems[:i+1])
                if path in xml_map:
                    e = xml_map[path]
                elif i == 0:
                    e = etree.SubElement(config, self.DEV + elem,
                                         nsmap=self.DEVNSMAP)
                else:
                    e = etree.SubElement(e, elem)
                xml_map[path] = e
            text = self.sdict[s]
            if not text.startswith("<empty-"):
                e.text = text
        self.etree = etree
        self.root = root
