# -*- mode: python; python-indent: 4 -*-

import os
import glob
import shutil
from lxml import etree

import _ncs

from . import base_op
from .ex import ActionError


state_metadata = """\
# automatically generated
# all XMNR state files need to be loaded in 'override' mode
mode = override
"""


class ConfigOp(base_op.ActionBase):
    def write_metadata(self, state_filename):
        with open(state_filename + ".load", 'w') as meta:
            meta.write(state_metadata)


class DeleteStateOp(ConfigOp):
    action_name = 'delete state'

    def _init_params(self, params):
        self.state_name_pattern = params.state_name_pattern
        self.state_name = params.state_name

    def perform(self):
        self.log.debug("config_delete_state() with device {0}".format(self.dev_name))
        name_or_pattern = self.state_name_pattern
        if name_or_pattern is None:
            name_or_pattern = self.state_name
        state_filename_pattern = self.state_name_to_filename(name_or_pattern)
        state_filenames = glob.glob(state_filename_pattern)
        if state_filenames == []:
            raise ActionError("no such states: {0}".format(self.state_name))
        for state_filename in state_filenames:
            try:
                os.remove(state_filename)
                try:
                    os.remove(state_filename + ".load")
                except OSError:
                    pass
            except OSError:
                return {'failure': "Could not delete " + state_filename}
        return {'success': "Deleted: " + ', '.join(self.state_filename_to_name(state_filename)
                                                   for state_filename in state_filenames)}


class ListStatesOp(ConfigOp):
    action_name = 'list states'

    def _init_params(self, params):
        pass

    def perform(self):
        self.log.debug("config_list_states() with device {0}".format(self.dev_name))
        state_files = self.get_state_files()
        return {'success': "Saved device states: " +
                str([self.state_filename_to_name(st) for st in state_files])}


class RecordStateOp(ConfigOp):
    action_name = 'record state'

    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")
        self.include_rollbacks = self.param_default(params, "including_rollbacks", 0)
        self.style_format = self.param_default(params, "format", "c-style")

    def perform(self):
        return self.run_with_trans(self._perform, write=True)

    def _perform(self, trans):
        self.log.debug("config_record_state() with device {0}".format(self.dev_name))
        state_name = self.state_name
        self.log.debug("incl_rollbacks="+str(self.include_rollbacks))
        self.log.debug("style_format="+str(self.style_format))
        try:
            # list_rollbacks() returns one less rollback than the second argument,
            # i.e. send 2 to get 1 rollback. Therefore the +1
            rollbacks = _ncs.maapi.list_rollbacks(trans.maapi.msock, int(self.include_rollbacks)+1)
            # rollbacks are returned 'most recent first', i.e. reverse chronological order
        except _ncs.error.Error:
            rollbacks = []
        self.log.debug("rollbacks="+str([r.fixed_nr for r in rollbacks]))
        index = 0
        state_filenames = []
        for rb in [None] + rollbacks:
            if rb is None:
                self.log.debug("Recording current transaction state")
            else:
                self.log.debug("Recording rollback"+str(rb.fixed_nr))
                self.log.debug("Recording rollback"+str(rb.nr))
                trans.load_rollback(rb.nr)

            state_name_index = state_name
            if index > 0:
                state_name_index = state_name+"-"+str(index)
            state_filename = self.state_name_to_filename(state_name_index)
            device_path = "/ncs:devices/device{"+self.dev_name+"}/config"
            is_xml = "xml" == str(self.style_format)
            config_type = _ncs.maapi.CONFIG_C
            if is_xml:
                config_type = _ncs.maapi.CONFIG_XML
            with open(state_filename, "wb") as state_file:
                save_data = self.save_config(trans, config_type, device_path)
                if is_xml:
                    xslt_root = etree.XML('''\
        <xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
           <xsl:output method="xml" indent="yes" omit-xml-declaration="yes"/>
           <xsl:strip-space elements="*"/>
           <xsl:template xmlns:config="http://tail-f.com/ns/config/1.0" xmlns:ncs="http://tail-f.com/ns/ncs"
                         match="/config:config/ncs:devices/ncs:device">
              <xsl:apply-templates select="ncs:config"/>
           </xsl:template>

           <xsl:template xmlns:ncs="http://tail-f.com/ns/ncs" match="ncs:config">
              <config xmlns="http://tail-f.com/ns/config/1.0">
                <xsl:copy-of select="*"/>
              </config>
           </xsl:template>
        </xsl:stylesheet>''')
                    tree = etree.fromstringlist(save_data)
                    # run XSLT to remove /config/devices/device and wrap child elements in /config
                    transform = etree.XSLT(xslt_root)
                    xml_data = transform(tree)
                    state_file.write(etree.tostring(xml_data, pretty_print=True))
                else:
                    for data in save_data:
                        state_file.write(data)
            self.write_metadata(state_filename)
            state_filenames += [state_name_index]
            index += 1
            trans.revert()
        return {'success': "Recorded states " + str(state_filenames)}


class ImportStateFiles(ConfigOp):
    action_name = 'import states'

    def _init_params(self, params):
        self.pattern = params.file_path_pattern
        self.file_format = self.param_default(params, "format", "")
        self.overwrite = params.overwrite
        self.merge = params.merge

    def perform(self):
        filenames = glob.glob(self.pattern)
        if filenames == []:
            raise ActionError("no files found: " + self.pattern)
        states = [self.get_state_name(os.path.basename(filename))
                  for filename in filenames]
        if not self.overwrite:
            conflicts = [state for state in states
                         if os.path.exists(self.state_name_to_filename(state))]
            if conflicts != []:
                raise ActionError("States already exists: " + ", ".join(conflicts))
        for (source, target) in zip(filenames, states):
            self.import_file(source, target)
        return {"success": "Imported states: " + ", ".join(states)}

    def import_file(self, source_file, state):
        if self.file_format == "c-style":
            tmpfile = "/tmp/" + os.path.basename(source_file) + ".tmp"
            with open(tmpfile, "w+") as outfile:
                outfile.write("devices device " + self.dev_name + " config\n")
                with open(source_file, "r") as infile:
                    for line in infile:
                        outfile.write(line)
            if self.merge:
                tmpfile2 = tmpfile + ".tmp2"
                flags = _ncs.maapi.CONFIG_C + _ncs.maapi.CONFIG_MERGE
                self.create_state(tmpfile, tmpfile2, flags)
                tmpfile = tmpfile2
            source_file = tmpfile
        elif self.file_format == "xml":
            tmpxmlfile = "/tmp/" + os.path.basename(source_file) + ".xmltmp"
            tmpfile = "/tmp/" + os.path.basename(source_file) + ".tmp"
            self.run_xslt(tmpxmlfile, source_file)
            flags = _ncs.maapi.CONFIG_XML
            if self.merge:
                flags += _ncs.maapi.CONFIG_MERGE
            self.create_state(tmpxmlfile, tmpfile, flags)
            source_file = tmpfile
        elif self.file_format == "nso-xml":
            tmpfile = "/tmp/" + os.path.basename(source_file) + ".tmp"
            flags = _ncs.maapi.CONFIG_XML
            if self.merge:
                flags += _ncs.maapi.CONFIG_MERGE
            self.create_state(source_file, tmpfile, flags)
            source_file = tmpfile
        elif self.file_format == "nso-c-style":
            # file(s) already in state format (== nso-c-style format)
            if self.merge:
                tmpfile = "/tmp/" + os.path.basename(source_file) + ".tmp"
                flags = _ncs.maapi.CONFIG_C + _ncs.maapi.CONFIG_MERGE
                self.create_state(source_file, tmpfile, flags)
        dirname = os.path.dirname(source_file)
        if dirname == self.states_dir:
            tmpfile = source_file
        else:
            tmpfile = os.path.join(self.states_dir, ".new_state_file")
            shutil.copyfile(source_file, tmpfile)
        os.rename(tmpfile, self.state_name_to_filename(state))
        self.write_metadata(self.state_name_to_filename(state))

    def get_state_name(self, origname):
        (base, ext) = os.path.splitext(origname)
        while ext != "":
            (base, ext) = os.path.splitext(base)
        return base

    def run_xslt(self, nso_xml_file, xml_file):
        xslt_root = etree.XML('''\
        <xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform" version="1.0">
          <xsl:output method="xml" indent="yes" omit-xml-declaration="yes"/>
          <xsl:strip-space elements="*"/>
          <xsl:param name="device_name"/>
          <xsl:template match="/">
              <config xmlns="http://tail-f.com/ns/config/1.0">
                <devices xmlns="http://tail-f.com/ns/ncs">
                  <device>
                    <name><xsl:value-of select="$device_name"/></name>
                    <config>
                      <xsl:apply-templates select="@*|node()"/>
                    </config>
                  </device>
                </devices>
              </config>
          </xsl:template>
          <xsl:template match="@*|node()">
            <xsl:copy>
              <xsl:apply-templates select="@*|node()"/>
            </xsl:copy>
          </xsl:template>
          <!-- If in the XML file, omit the confd config tag from the results -->
          <xsl:template match="*[local-name()='config' and
                                 namespace-uri()='http://tail-f.com/ns/config/1.0']">
            <xsl:apply-templates select="@*|node()"/>
          </xsl:template>
        </xsl:stylesheet>''')
        tree = etree.parse(xml_file)
        transform = etree.XSLT(xslt_root)
        nso_xml = transform(tree,  device_name=etree.XSLT.strparam(self.dev_name))
        with open(nso_xml_file, "w+") as outfile:
            nso_xml.write(outfile)

    def create_state(self, source_file, state_file, flags):
        try:
            self.run_with_trans(lambda trans: self.run_create_state(trans, source_file, state_file,
                                                                    flags), write=True)
        except _ncs.error.Error as err:
            raise ActionError(os.path.basename(source_file) + " " +
                              str(err).replace("\n", ""))

    def run_create_state(self, trans, source_file, state_file, flags):
        trans.load_config(flags, source_file)
        with open(state_file, "w+") as state_file:
            for data in self.save_config(trans,
                                         _ncs.maapi.CONFIG_C,
                                         "/ncs:devices/device{"+self.dev_name+"}/config"):
                state_file.write(data)


class CheckStates(ConfigOp):
    action_name = 'check states'

    def _init_params(self, params):
        self.validate = params.validate

    def perform(self):
        states = self.get_states()
        self.log.debug('checking states: {}'.format(states))
        failures = []
        for filename in [self.state_name_to_filename(state) for state in states]:
            try:
                self.run_with_trans(lambda trans: self.test_filename_load(trans, filename),
                                    write=True)
            except _ncs.error.Error as err:
                failures.append("\n{}: {}".format(self.state_filename_to_name(filename),
                                                  str(err).replace("\n", " ")))
        if failures == []:
            return {'success': 'all states are consistent'}
        else:
            msg = 'states not consistent with the device model: {}'
            return {'failure': msg.format(''.join(failures))}

    def test_filename_load(self, trans, filename):
        trans.load_config(_ncs.maapi.CONFIG_C + _ncs.maapi.CONFIG_MERGE, filename)
        if self.validate:
            trans.validate(True)


class StatesProvider(object):
    def __init__(self, log):
        self.log = log

    def get_states_data(self, tctx, args):
        return StatesData.get_data(tctx, args['device'], self.log, StatesData.states)

    def get_object(self, tctx, kp, args):
        states = self.get_states_data(tctx, args)
        return {'states': [{'state': st} for st in states]}


class StatesData(base_op.XmnrDeviceData):
    def states(self):
        return self.get_states()
