import os
import re
import glob
import shutil
from lxml import etree

import _ncs
from drned_xmnr.namespaces.drned_xmnr_ns import ns

from . import base_op
from .ex import ActionError
from .common_op import DevcliLogMatch, Handler

from typing import Any, Dict, List, Optional, Set, Tuple
from drned_xmnr.typing_xmnr import ActionResult, Tctx
from ncs.log import Log
from ncs.maagic import Node
from ncs.maapi import Transaction


state_metadata = """\
# automatically generated
# all XMNR state files need to be loaded in 'override' mode
mode = override
"""


class ConfigOp(base_op.ActionBase):
    def write_metadata(self, state_filename: str) -> None:
        with open(state_filename + self.metadata_extension, 'w') as meta:
            meta.write(state_metadata)

    def remove_state_file(self, state_filename: str) -> None:
        os.remove(state_filename)
        for suffix in (self.metadata_extension, self.flag_file_extension):
            try:
                os.remove(state_filename + suffix)
            except OSError:
                pass


class StateParamOp(ConfigOp):
    """Common superclass for actions using `state-or-pattern` grouping.
    """
    def _init_params(self, params: Node) -> None:
        self.state_name_pattern = params.state_name_pattern
        self.state_name = params.state_name

    def get_state_filenames(self) -> List[str]:
        if self.state_name_pattern is None:
            state_filenames = [self.state_name_to_filename(self.state_name)]
        else:
            state_filenames = self.get_state_files_by_pattern(self.state_name_pattern)
            if state_filenames == []:
                raise ActionError("no such states: {0}".format(self.state_name_pattern))
        return state_filenames


class DeleteStateOp(StateParamOp):
    action_name = 'delete state'

    def perform(self) -> ActionResult:
        self.log.debug("config_delete_state() with device {0}".format(self.dev_name))
        state_filenames = self.get_state_filenames()
        for state_filename in state_filenames:
            try:
                self.remove_state_file(state_filename)
            except OSError:
                return {'failure': "Could not delete " + state_filename}
        return {'success': "Deleted: " + ', '.join(self.state_filename_to_name(state_filename)
                                                   for state_filename in state_filenames)}


class DisableStateOp(StateParamOp):
    action_name = 'disable state'

    def perform(self) -> ActionResult:
        self.log.debug('disable state with device {}'.format(self.dev_name))
        state_filenames = self.get_state_filenames()
        for state_filename in state_filenames:
            flag_filename = state_filename + self.flag_file_extension
            try:
                with open(flag_filename, 'w'):
                    pass
            except OSError:
                return {'failure': 'Failed to mark {} as disabled'.format(state_filename)}
        return {'success': 'Disabled: ' + ', '.join(self.state_filename_to_name(filename)
                                                    for filename in state_filenames)}


class EnableStateOp(StateParamOp):
    action_name = 'ensable state'

    def perform(self) -> ActionResult:
        self.log.debug('enable state with device {}'.format(self.dev_name))
        state_filenames = self.get_state_filenames()
        for state_filename in state_filenames:
            flag_filename = state_filename + self.flag_file_extension
            try:
                if os.path.exists(flag_filename):
                    os.unlink(flag_filename)
            except OSError:
                return {'failure': 'Failed to mark {} as enabled'.format(state_filename)}
        return {'success': 'Enabled: ' + ', '.join(self.state_filename_to_name(filename)
                                                   for filename in state_filenames)}


class ListStatesOp(ConfigOp):
    action_name = 'list states'

    def _init_params(self, params: Node) -> None:
        pass

    def perform(self) -> ActionResult:
        self.log.debug("config_list_states() with device {0}".format(self.dev_name))
        state_files = self.get_state_files()
        disabled_files = self.get_disabled_state_files()
        if disabled_files:
            disabled_states = [self.state_filename_to_name(st) for st in disabled_files]
            disabled_msg = ' disabled states: ' + str(disabled_states)
        else:
            disabled_msg = ''
        states = [self.state_filename_to_name(st) for st in state_files]
        return {'success': "Saved device states: {}{}".format(states, disabled_msg)}


class ViewStateOp(ConfigOp):
    action_name = 'view state'

    def _init_params(self, params: Node) -> None:
        self.state_name = params.state_name

    def perform(self) -> ActionResult:
        self.log.debug("config_view_state() with device {0}".format(self.dev_name))
        state_name = self.state_name
        failed_result: ActionResult = {'failure': "Could not view " + state_name}
        state_filename = self.state_name_to_existing_filename(state_name)
        if state_filename is None:
            return failed_result
        try:
            with open(state_filename, 'r') as f:
                state_str = f.read()
                return {'success': state_str}
        except OSError:
            return failed_result


class RecordStateOp(ConfigOp):
    action_name = 'record state'

    def _init_params(self, params: Node) -> None:
        self.state_name = self.param_default(params, "state_name", "")
        self.include_rollbacks = self.param_default(params, "including_rollbacks", 0)
        self.style_format = self.param_default(params, "format", "c-style")
        self.overwrite = params.overwrite

    def perform(self) -> ActionResult:
        return self.run_with_trans(self._perform, write=True)

    def _perform(self, trans: Transaction) -> ActionResult:
        self.log.debug("config_record_state() with device {0}".format(self.dev_name))
        state_name = self.state_name
        self.log.debug("incl_rollbacks=" + str(self.include_rollbacks))
        self.log.debug("style_format=" + str(self.style_format))
        try:
            # list_rollbacks() returns one less rollback than the second argument,
            # i.e. send 2 to get 1 rollback. Therefore the +1
            rollbacks = _ncs.maapi.list_rollbacks(trans.maapi.msock, int(self.include_rollbacks) + 1)
            # rollbacks are returned 'most recent first', i.e. reverse chronological order
        except _ncs.error.Error:
            rollbacks = []
        self.log.debug("rollbacks=" + str([r.fixed_nr for r in rollbacks]))
        index = 0
        state_filenames = []
        for rb in [None] + rollbacks:
            if rb is None:
                self.log.debug("Recording current transaction state")
            else:
                self.log.debug("Recording rollback" + str(rb.fixed_nr))
                self.log.debug("Recording rollback" + str(rb.nr))
                trans.load_rollback(rb.nr)

            state_name_index = state_name
            if index > 0:
                state_name_index = state_name + "-" + str(index)
            format = 'xml' if 'nso-xml' == str(self.style_format) else 'cfg'
            existing_filename = self.state_name_to_existing_filename(state_name_index)
            if existing_filename is not None:
                if not self.overwrite:
                    raise ActionError("state {} already exists".format(state_name_index))
                self.remove_state_file(existing_filename)
            state_filename = self.format_state_filename(state_name_index, format=format)
            device_path = "/ncs:devices/device{" + self.dev_name + "}/config"
            config_type = _ncs.maapi.CONFIG_C
            if format == 'xml':
                config_type = _ncs.maapi.CONFIG_XML
            with open(state_filename, "wb") as state_file:
                save_data = self.save_config(trans, config_type, device_path)
                if format == 'xml':
                    # just pretty_print it
                    tree = etree.fromstringlist(save_data)
                    state_file.write(etree.tostring(tree, pretty_print=True))
                else:
                    for data in save_data:
                        state_file.write(data)
            self.write_metadata(state_filename)
            state_filenames += [state_name_index]
            index += 1
            trans.revert()
        return {'success': "Recorded states " + str(state_filenames)}


class ImportOp(ConfigOp):
    def _init_params(self, params: Node) -> None:
        self.pattern = params.file_path_pattern
        self.overwrite = self.param_default(params, "overwrite", None)
        self.skip_existing = self.param_default(params, "skip_existing", None)

    def verify_filenames(self) -> Tuple[List[str], List[str], Set[str]]:
        maybefiles = glob.glob(self.pattern)
        filenames = [filename for filename in maybefiles if os.path.isfile(filename)]
        if filenames == []:
            raise ActionError("no files found: " + self.pattern)
        states = [self.get_state_name(os.path.basename(filename))
                  for filename in filenames]
        checks = [self.state_name_to_existing_filename(state) for state in states]
        conflicts = {self.state_filename_to_name(filename) for filename in checks
                     if filename is not None}
        if conflicts and not self.overwrite and not self.skip_existing:
            raise ActionError("States already exist: " + ", ".join(conflicts))
        return filenames, states, conflicts

    def get_state_name(self, origname: str) -> str:
        (base, ext) = os.path.splitext(origname)
        (base1, ext1) = os.path.splitext(base)
        if ext1 == ".state":
            # happens for "import" of states from another device or XMNR instance
            return base1
        return base


class ImportStateFiles(ImportOp):
    action_name = 'import states'

    def _init_params(self, params: Node) -> None:
        super(ImportStateFiles, self)._init_params(params)
        self.file_format: str = self.param_default(params, "format", "")
        self.state_format = params.target_format
        self.merge = params.merge

    def perform(self) -> ActionResult:
        filenames, states, conflicts = self.verify_filenames()
        for (source, target) in zip(filenames, states):
            if target in conflicts and self.overwrite:
                # TODO: the conflicts should be removed only after
                # everything else have been done; but that's
                # difficult...
                cf_filename = self.state_name_to_existing_filename(target)
                self.remove_state_file(cf_filename)
            try:
                self.import_file(source, target)
            except etree.XMLSyntaxError:
                msg = ('the file {} does not appear to be valid XML, '
                       'perhaps you wanted c-style format instead?').format(source)
                raise ActionError(msg)
            except _ncs.error.Error as err:
                msg = ('the file {} could not be loaded; '
                       'try a different import format (error: {})')
                raise ActionError(msg.format(source, str(err).replace("\n", " ")))

        return {"success": "Imported states: " + ", ".join(states)}

    def import_file(self, source_file: str, state: str) -> None:
        tmpfile1 = "/tmp/" + os.path.basename(source_file) + ".tmp1"
        tmpfile2 = "/tmp/" + os.path.basename(source_file) + ".tmp2"
        if self.file_format == "c-style":
            with open(tmpfile1, "w+") as outfile:
                outfile.write("devices device " + self.dev_name + " config\n")
                with open(source_file, "r") as infile:
                    for line in infile:
                        outfile.write(line)
        elif self.file_format == "xml":
            self.run_xslt(tmpfile1, source_file)
        elif self.file_format == "nso-xml":
            config = etree.parse(source_file)
            devname = config.xpath('//ns:device/ns:name',
                                   namespaces={'ns': 'http://tail-f.com/ns/ncs'})
            devname[0].text = self.dev_name
            config.write(tmpfile1)
        else:
            devrx = re.compile('devices device \\S+')
            fixline = 'devices device {}'.format(self.dev_name)
            with open(tmpfile1, 'w+') as output:
                with open(source_file) as source:
                    for line in source:
                        output.write(devrx.sub(fixline, line))
        self.run_with_trans(lambda trans: self.run_create_state(trans, tmpfile1, tmpfile2),
                            write=True)
        os.remove(tmpfile1)
        format = 'cfg' if self.state_format == 'c-style' else 'xml'
        filename = self.format_state_filename(state, format=format)
        shutil.move(tmpfile2, filename)
        self.write_metadata(filename)

    def run_xslt(self, nso_xml_file: str, xml_file: str) -> None:
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
        nso_xml = transform(tree, device_name=etree.XSLT.strparam(self.dev_name))
        with open(nso_xml_file, "w+") as outfile:
            nso_xml.write(outfile.name)

    def run_create_state(self, trans: Transaction, source_file: str, state_file: str) -> None:
        dev_config = "/ncs:devices/device{{{}}}/config".format(self.dev_name)
        if not self.merge:
            trans.delete(dev_config)
        load_flag = (_ncs.maapi.CONFIG_C if self.file_format in ['c-style', 'nso-c-style']
                     else _ncs.maapi.CONFIG_XML)
        trans.load_config(_ncs.maapi.CONFIG_MERGE | load_flag, source_file)
        save_flag = (_ncs.maapi.CONFIG_C if self.state_format == 'c-style'
                     else _ncs.maapi.CONFIG_XML_PRETTY)
        with open(state_file, "wb") as state_data:
            for data in self.save_config(trans, save_flag, dev_config):
                state_data.write(data)


class ConvertMatch(DevcliLogMatch):
    matchexpr = (
        r'(?:(?P<convert>converting [^ ]* to [^ ]*/(?P<cnvstate>[^/]*)[.]xml)'
        r'|(?P<converted>converted [^ ]* to (?P<target>[^ ]*/(?P<donestate>[^/]*)[.]xml))'
        r'|(?P<failure>failed to convert group (?P<group>.*))'
        r'|(?P<restore_failed>failed to restore device config after group (?P<rest_group>.*))'
        r'|(?P<format>Filename format not understood: (?P<filename>.*))'
        r')$')
    matchrx = re.compile(matchexpr)

    def __init__(self, converter: 'ImportConvertCliFiles') -> None:
        super(ConvertMatch, self).__init__()
        self.failures: List[str] = []
        self.waitstate = None
        self.converter = converter

    def match(self, msg: str) -> Optional[str]:
        report = super(ConvertMatch, self).match(msg)
        if report is not None:
            return report
        match = ConvertMatch.matchrx.match(msg)
        if match is None:
            return None
        gd = match.groupdict()
        if match.lastgroup == 'convert':
            return 'importing state ' + gd['cnvstate']
        elif match.lastgroup == 'converted':
            self.converter.complete_import(gd['target'], gd['donestate'])
            return None
        elif match.lastgroup == 'failure':
            group = gd['group']
            self.failures.append(group)
            return 'failed to import group ' + group
        elif match.lastgroup == 'restore_failed':
            group = gd['rest_group']
            self.failures.append(group)
            return 'failed to restore the device config after converting ' + group
        elif match.lastgroup == 'format':
            filename = gd['filename']
            msg = 'unknown filename format: {}; should be name[:index].ext'
            self.failures.append(filename)
            return msg.format(filename)
        return None


class ImportConvertCliFiles(ImportOp):
    action_name = 'convert and import CLI states'

    NC_WORKDIR = 'drned-ncs'

    def __init__(self, *args: Any) -> None:
        super(ImportConvertCliFiles, self).__init__(*args)
        self.filter: ConvertMatch = ConvertMatch(self)

    def cli_filter(self, msg: str) -> None:
        report = self.filter.match(msg)
        if report is not None:
            super(ImportConvertCliFiles, self).cli_filter(report + '\n')

    def perform(self) -> ActionResult:
        filenames, states, conflicts = self.verify_filenames()
        if conflicts and not self.overwrite and self.skip_existing:
            filenames = [v for i, v in enumerate(filenames) if states[i] not in conflicts]
            if not filenames:
                raise ActionError('No new states to import')
            states = [state for state in states if state not in conflicts]

        files = [os.path.realpath(filename) for filename in filenames]
        result, _ = self.devcli_run('cli2netconf.py', files)
        if self.filter.devcli_error is not None:
            raise ActionError('Problems with the device driver: ' + self.filter.devcli_error)
        if result != 0 and not self.filter.failures:
            if self.filter.waitstate is not None:
                err = 'Conversion failed, ' \
                    'the device driver hung in state "{}"'.format(self.filter.waitstate)
            else:
                err = 'Conversion failed; the device driver is not working correctly'
            raise ActionError(err)
        if self.filter.failures:
            raise ActionError(
                'failed to convert configuration(s): ' + ', '.join(
                    self.filter.failures))
        return {"success": "Imported states: " + ", ".join(sorted(states))}

    def complete_import(self, filename: str, state: str) -> None:
        xml = os.path.splitext(os.path.basename(filename))[0] + '.xml'
        source = os.path.join(self.drned_run_directory, self.NC_WORKDIR, xml)
        if os.path.exists(source):
            target = self.format_state_filename(state)
            shutil.move(source, target)
            self.write_metadata(target)
        elif not self.filter.failures:
            # this should not be the case - if the source does not
            # exist, it means that the conversion has not
            # succeeded and the state/group should be among
            # failures
            self.filter.failures.append(state)


class CheckStates(ConfigOp):
    action_name = 'check states'

    def _init_params(self, params: Node) -> None:
        self.validate: bool = params.validate

    def perform(self) -> ActionResult:
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

    def test_filename_load(self, trans: Transaction, filename: str) -> None:
        flag = (_ncs.maapi.CONFIG_C if filename.endswith(self.cfg_statefile_extension)
                else _ncs.maapi.CONFIG_XML)
        trans.load_config(flag + _ncs.maapi.CONFIG_MERGE, filename)
        if self.validate:
            trans.validate(True)


class StatesProvider(Handler):
    def __init__(self, log: Log) -> None:
        self.log = log

    def get_states_data(self, tctx: Tctx, device: str) -> List[Tuple[str, bool]]:
        return StatesData.get_data(tctx, device, self.log, StatesData.states)

    def get_object(self, tctx: Tctx, kp: str, args: Dict[str, str]) -> Dict[str, Any]:
        states = sorted(self.get_states_data(tctx, args['device']))
        disabled_tag = _ncs.Value((ns.hash, ns.drned_xmnr_disabled), _ncs.C_XMLTAG)
        return {'states': [{'state': state, 'disabled': disabled_tag} if disabled
                           else {'state': state}
                           for state, disabled in states]}


class StatesData(base_op.XmnrDeviceData):
    def states(self) -> List[Tuple[str, bool]]:
        return [(self.state_filename_to_name(filename),
                 os.path.exists(filename + self.flag_file_extension))
                for filename in self.get_state_files()]
