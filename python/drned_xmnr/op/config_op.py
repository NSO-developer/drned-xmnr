# -*- mode: python; python-indent: 4 -*-

import os
import glob
import shutil

import _ncs

import base_op
from ex import ActionError


state_metadata = """\
# automatically generated
# all XMNR state files need to be loaded in 'override' mode
mode = override
"""


class ConfigOp(base_op.BaseOp):
    def write_metadata(self, state_filename):
        with open(state_filename + ".load", 'w') as meta:
            print >> meta, state_metadata


class DeleteStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")

    def perform(self):
        self.log.debug("config_delete_state() with device {0}".format(self.dev_name))
        state_filename = self.state_name_to_filename(self.state_name)
        try:
            os.remove(state_filename)
            try:
                os.remove(state_filename + ".load")
            except OSError:
                pass
        except:
            return {'error': "Could not delete " + state_filename}
        return {'success': "Deleted " + self.state_name}


class ListStatesOp(ConfigOp):
    def _init_params(self, params):
        pass

    def perform(self):
        self.log.debug("config_list_states() with device {0}".format(self.dev_name))
        state_files = self.get_state_files()
        return {'success': "Saved device states: " +
                str(map(self.state_filename_to_name, state_files))}


class RecordStateOp(ConfigOp):
    def _init_params(self, params):
        self.state_name = self.param_default(params, "state_name", "")
        self.include_rollbacks = self.param_default(params, "including_rollbacks", 0)

    def perform(self):
        return self.run_with_trans(self._perform, write=True)

    def _perform(self, trans):
        self.log.debug("config_record_state() with device {0}".format(self.dev_name))
        state_name = self.state_name
        self.log.debug("incl_rollbacks="+str(self.include_rollbacks))
        try:
            # list_rollbacks() returns one less rollback than the second argument,
            # i.e. send 2 to get 1 rollback. Therefore the +1
            rollbacks = _ncs.maapi.list_rollbacks(trans.maapi.msock, int(self.include_rollbacks)+1)
            # rollbacks are returned 'most recent first', i.e. reverse chronological order
        except:
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
            with open(state_filename, "w") as state_file:
                for data in self.save_config(trans,
                                             _ncs.maapi.CONFIG_C,
                                             "/ncs:devices/device{"+self.dev_name+"}/config"):
                    state_file.write(data)
            self.write_metadata(state_filename)
            state_filenames += [state_name_index]
            index += 1
            trans.revert()
        return {'success': "Recorded states " + str(state_filenames)}


class ImportStateFiles(ConfigOp):
    def _init_params(self, params):
        self.pattern = params.file_path_pattern
        self.overwrite = params.overwrite

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
