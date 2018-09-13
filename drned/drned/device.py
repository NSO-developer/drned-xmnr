import datetime
import filecmp
import inspect
import os
import pexpect
import pytest
import re
import shutil
import subprocess
import tempfile
import time
import urllib
from lxml import etree

INDENT = "=" * 30 + " "

class Device(object):
    """The abstraction of a NCS/NED device.

    This class communicates with NCS through the CLI, and contains the
    most common NED-related functionality.

    """
    def __init__(self, name, cli="ncs_cli -C -u admin", use=[], request=None):
        if name.startswith("netsim-"):
            # All netsim targets boil down to netsim-0
            name = "netsim-0"
        self.cfg = name + ".cfg"
        self.cli = cli
        self.request=request
        self.commit_id = []
        self.rollback_id = None
        self.rollback_xml = {}
        self.log = []
        self.name = name
        self.ned_name = None
        self.device_type = None
        self.rload_path = "devices device %s config" % self.name
        self.tmo = 60
        self.verbose = False
        self.reconnect_required = False
        self.saw_compare_after_commit = True
        self.use_commit_queues = True
        self.use_transaction_id = None
        self.use_no_networking = False
        self.use_commit_no_overwrite = False
        self.use_raw_trace = True
        self.use_java_log = True
        self.use_commit_queue_retries = 2
        self.java_log_level = "level-all"
        self.extra_ned_settings = None
        # Check if NCS is started
        out = subprocess.check_output("ncs --status || true", shell=True)
        if out.find("vsn:") < 0:
            pytest.fail("Please start NCS first, with " +
                        "'make start' or 'make restart'")
        # Start cli
        self.reset_cli()

        # Get version
        self.cmd("do show ncs-state | include \"ncs-state version\"")
        self.version = self.ncs_buf.strip().split()[-1]
        # Get drned root
        drned = os.getenv("DRNED")
        assert drned

        # Handle possible settings
        if use:
            for u in use:
                var,val = u.split("=")
                assert hasattr(self, var)
                if val == "True":
                    val = True
                elif val == "False":
                    val = False
                elif val == "None":
                    val = None
            setattr(self, var, val)

        # Check commit queue support
        with open("../../package-meta-data.xml") as f:
            s = re.sub("(<!--.*?-->)", "", f.read(), flags=re.DOTALL)
            if "requires-transaction-states" in s:
                self.use_commit_queues = False
        print("NOTE: Commit queues are %s!" %
              ("enabled" if self.use_commit_queues else "disabled"))
        # Load initial config, local or drned/device
        dirs = [".",
                "./device/%s" % (name),
                "%s/device/%s" % (drned, name)]
        for d in dirs:
            if os.path.isfile(os.path.join(d, self.cfg)):
                # Run possible shell script
                with open(os.path.join(d, self.cfg)) as f:
                    script = [s[2:].strip()
                              for s in f.readlines() if s.startswith("!$")]
                    if script:
                        assert os.system("".join(script)) == 0
                # Check for license expiry
                with open(os.path.join(d, self.cfg)) as f:
                    cfg = f.read()
                    for m in re.finditer(r'^\s*!\s*license-expires\s*:\s*["]?([0-9\-]*)["]?',
                                         cfg, re.MULTILINE):
                        expires = datetime.datetime.strptime(m.group(1), "%Y-%m-%d")
                        if datetime.datetime.now() + datetime.timedelta(days=30) >= expires:
                            print("[DrNED] %s:0: Warning: License for %s will expire %s" %
                                  (self.cfg, self.name, m.group(1)))
                # Load config
                self.load(os.path.join(d, self.cfg),
                          ancient=(self.version < "3.2"))
                # Bypass normal commit
                self.cmd("commit")
                break
        else:
            pytest.fail("No device file named %s in %s" % (self.cfg, dirs))

        # Inform NCS of transid setting
        self.sethook_use_transaction_id(self.use_transaction_id)
        # Increase session timeout to avoid premature disconnects
        if self.version >= "4":
            self.cmd("devices global-settings session-pool idle-time 600")
        # Restrict commit queue retries
        try:
            self.cmd("devices global-settings commit-queue retry-attempts %d" %
                     self.use_commit_queue_retries)
        except pytest.fail.Exception:
            try:
                self.cmd("devices global-settings commit-queue connection-failure-reconnect-retries %d" %
                         self.use_commit_queue_retries)
            except pytest.fail.Exception:
                pass

        # Setup logging before first connect
        if self.use_raw_trace:
            self.cmd("devices device %s trace raw" % self.name)
        if self.use_java_log:
            self.cmd("java-vm java-logging logger com.tailf.packages.ned " +
                     "level %s" % (self.java_log_level))

        # Must use self.show() here since config may contain strings
        # that mimic a prompt
        self.show("show full-configuration devices device %s" % self.name)
        # Get NED name
        self.cmd("show full-configuration devices device %s device-type" % self.name)
        device_type = re.search("device-type\\s+(\\S+)\\s+ned-id", self.ncs_buf, re.MULTILINE)
        ned_id = re.search("device-type\\s+\\S+\\s+ned-id\\s+(\\S+)", self.ncs_buf, re.MULTILINE)
        if device_type:
            self.device_type = device_type.group(1)
        if ned_id:
            self.ned_name = ned_id.group(1)
        # Fetch host keys?
        if self.device_type != "generic" and not "protocol telnet" in self.ncs_buf:
            self.cmd("show full-configuration devices device %s ssh" % self.name)
            if not "key-data" in self.ncs_buf:
                try:
                    self.cmd("devices device %s ssh fetch-host-keys" % self.name)
                except pytest.fail.Exception as e:
                    raise
        self.cmd("commit") # Bypass normal commit
        # Timeouts are handled here to be able to expect with same value
        self.cmd("show full-configuration devices device %s read-timeout" % self.name)
        read_timeout = re.search("read-timeout\\s+(\\d+)",
                                 self.ncs_buf, re.MULTILINE)

        # Load extra ned settings as specified via command line argument
        if self.extra_ned_settings != None:
            for setting in self.extra_ned_settings.split(","):
                self.cmd("devices device %s ned-settings %s" % (self.name, setting))
            self.cmd("commit")

        if read_timeout:
            self.tmo = int(read_timeout.group(1))
        else:
            self.timeout(2 * 60 * 60)
        # Make a couple of connection attempts, with corrective actions
        retry_interval = 1
        retry_number = 8
        for i in range(retry_number):
            try:
                self.cmd("devices device %s connect" % self.name,
                         expect="result true")
                break;
            except pytest.fail.Exception as e:
                if "SSH host key" in e.msg:
                    self.cmd("devices device %s ssh fetch-host-keys" % self.name)
                    self.cmd("commit") # Bypass normal commit
                    print("\nNOTE: To speedup connection, please update SSH " +
                          "host key in %s.cfg" % self.name)
                    self.cmd("show full-configuration devices device " +
                             "%s ssh host-key" % self.name)
                elif i < (retry_number-1):
                    # This can either be due to the JVM running in a
                    # terminal, a device that's hard to contact, or
                    # intermittent network issues. Sleep a while and
                    # try again.
                    time.sleep(retry_interval)
                    retry_interval *= 2
        else:
            # Connect failed
            raise
        # First sync
        self.sync_from()
        # Start coverage session
        if os.path.isdir("drned-work/coverage"):
            self.covsession = str(int(time.time() * 1000))
            os.makedirs("drned-work/coverage/%s" % self.covsession)
        # Create an initial coverage report
        xml = self._coverage()
        self.cmd("top")

    def reset_cli(self):
        with open("drned-work/stdin.txt", "a") as f:
            f.write("!!! NEW SESSION STARTS\n")
        if hasattr(self, "ncs"):
            self.ncs.close()
        self.ncs = pexpect.spawn(self.cli, timeout=60)
        self.ncs.expect('admin@ncs# ')
        # NCS general setup
        self.cmd("complete-on-space false")
        self.cmd("idle-timeout 0")
        self.cmd("ignore-leading-space true")
        self.cmd("timestamp enable")
        self.cmd("config", expect="(config)")
        self.cmd("session paginate false")
        with open("drned-work/stdin.txt", "a") as f:
            f.write("!!! NEW SESSION STARTED\n")

    def sethook_use_transaction_id(self, value):
        if value == None:
            self.cmd("no devices device %s ned-settings use-transaction-id" % self.name)
        else:
            self.cmd("devices device %s ned-settings use-transaction-id %s" %
                     (self.name, "true" if value else "false"))
        self.cmd("commit")

    def timeout(self, tmo):
        """Set a new transaction timeout.

        Args:
            tmo: the new timeout in seconds
        Returns:
            self
        """
        self.tmo = tmo
        self.cmd("devices device %s" % self.name +
                 " write-timeout %d" % self.tmo +
                 " read-timeout %d" % self.tmo +
                 " connect-timeout 60")
        self.cmd("commit")
        self.cmd("top")
        return self

    def save(self, name, path=None, fmt="", banner=True):
        """Save device configuration to file.

        Args:
            name: the file to create
            path: the path to save, default: devices device <name> config
            fmt: file format, default cli
        Returns:
            self
        """
        if banner:
            self.trace(INDENT + inspect.stack()[0][3] + "(" + name + ")")
        # The overwrite support is version-dependent, so use non-ncs
        # solution
        try:
            os.remove(name)
        except OSError:
            pass
        p = path if path else ("devices device %s config" % self.name)
        self.cmd("save %s %s %s" % (name, fmt, p))
        return self

    def load(self, name, mode="merge", fail_on_errors=True, rename_device=False,
             ancient=False):
        """Load device configuration from file.

        The load operation can read additional load information from a
        file with the same name as the file to load, appended with
        .load (looks for init.txt.load when loading init.txt). This
        file can specify a mode to be used in the load operation, and
        whether to scrub device names from the file or not:

            # Mode for the file
            mode = replace
            scrub = false

        Args:
            name: the file to read from
            mode: load mode
            fail_on_errors: flag indicating whether we should fail on parse errors
            rename_device: replace possible device name(s) in file
            ancient: use pre-NCS3.2 SSH setup
        Returns:
            self
        """
        self.trace(INDENT + inspect.stack()[0][3] + "(" + name + ")")
        rm = None
        self.last_load = name
        if rename_device or ancient:
            suffix = "." + name.split(".")[-1]
            prefix = os.path.basename(name)
            prefix = prefix[:prefix.index(suffix)] + "_tmp"
            with tempfile.NamedTemporaryFile(dir="drned-work",
                                             prefix=prefix,
                                             suffix=suffix,
                                             delete=False) as temp:
                name = self._new_device_name(name, temp, ancient=ancient)
                rm = None if name == temp.name else temp.name
        # Get possible load options from file
        if os.path.isfile("%s.load" % name):
            print("NOTE: Get load parameters from %s.load" % name)
            with open("%s.load" % name, "r") as f:
                load = f.read()
                lmode = re.search("^\\s*mode\\s*=\\s*(\\S+)",
                                  load, re.MULTILINE)
            if lmode:
                mode = lmode.group(1)

        expect_not = None
        if not fail_on_errors:
            expect_not = "(ERROR|[Ee]rror|Failed|Aborted):(?! incomplete| on line| bad value)"
        self.cmd("load %s %s%s" % (mode, name,
                 " | best-effort" if not name.endswith(".xml")
                                  else ""), expect_not=expect_not)
        if rm:
            os.remove(rm)
        return self

    def rload(self, name, mode="merge", fail_on_errors=True, remove_device=False,
              set_path=True, banner=True):
        """Load device configuration from file at current position.

        The rload operation can read additional load information from
        a file with the same name as the file to load, appended with
        .load (looks for init.txt.load when loading init.txt). This
        file can specify a path and mode to be used in the load
        operation, and whether to scrub device names from the file or
        not:

            # Path and mode for the file
            path = devices device %device.name config
            mode = replace
            scrub = false

        Args:
            name: the file to read from
            mode: load mode, default "merge"
            fail_on_errors: flag indicating whether we should fail on parse errors
            remove_device: remove possible device name(s) in file
        Returns:
            self
        """
        if banner:
            self.trace(INDENT + inspect.stack()[0][3] + "(" + name + ")")
        rm = None
        self.last_load = name
        # Get possible load options from file
        path = self.rload_path
        if os.path.isfile("%s.load" % name):
            print("NOTE: Get load parameters from %s.load" % name)
            with open("%s.load" % name, "r") as f:
                load = f.read()
                lmode = re.search("^\\s*mode\\s*=\\s*(\\S+)",
                                  load, re.MULTILINE)
                lpath = re.search("^\\s*path\\s*=\\s*(.+)",
                                  load, re.MULTILINE)
                lremove = re.search("^\\s*remove-device\\s*=\\s*(.+)",
                                  load, re.MULTILINE)
            if lmode:
                mode = lmode.group(1)
            if lpath:
                path = lpath.group(1).replace("%device.name", self.name)
                # Reconnect to refresh NED instance vars
                self.reconnect_required = True
            if lremove:
                remove_device = lremove.group(1) in ["True", "true"]
        # Remove device name from file?
        if remove_device:
            suffix = "." + name.split(".")[-1]
            prefix = os.path.basename(name)
            prefix = prefix[:prefix.index(suffix)] + "_tmp"
            with tempfile.NamedTemporaryFile(dir="drned-work",
                                             suffix=suffix,
                                             prefix=prefix,
                                             delete=False) as temp:
                name = self._new_device_name(name, temp, remove=True)
                rm = None if name == temp.name else temp.name
        if set_path and path:
            self.cmd(path)
        expect_not = None
        if not fail_on_errors:
            expect_not = "(ERROR|[Ee]rror|Failed|Aborted):(?! incomplete| on line| bad value)"
        self.cmd("rload %s %s%s" % (mode, name,
                 " | best-effort" if not name.endswith(".xml")
                                  else ""), expect_not=expect_not)
        # To top
        if set_path:
            self.cmd("top")
        if rm:
            os.remove(rm)
        return self

    def source(self, name, prompt=None, rename_device=False, banner=True):
        """Source a command file in the CLI.

        Args:
            name: the file to source
            prompt: the prompt to match afterwards
            rename_device: rename possible device name(s) in file
            banner: print banner
        Returns:
            self
        """
        if banner:
            self.trace(INDENT + inspect.stack()[0][3] + "(" + name + ")")
        rm = None
        if rename_device:
            suffix = "." + name.split(".")[-1]
            prefix = os.path.basename(name)
            prefix = prefix[:prefix.index(suffix)] + "_tmp"
            with tempfile.NamedTemporaryFile(dir="drned-work",
                                             suffix=suffix,
                                             prefix=prefix,
                                             delete=False) as temp:
                name = self._new_device_name(name, temp)
                rm = None if name == temp.name else temp.name
        self.cmd("do source %s | details" % name, prompt=prompt)
        self.cmd("top")
        if rm:
            os.remove(rm)
        return self

    def sync_from(self):
        """Read configuration from device.

        Args:
            none
        Returns:
            self
        """
        self.trace(INDENT + inspect.stack()[0][3] + "()")
        self.cmd("devices device %s sync-from" %
                 self.name, expect="result true")
        xml = self._coverage()
        self._set_rollback_xml(xml)
        return self

    def sync_to(self):
        """Write configuration to device.

        Args:
            none
        Returns:
            self
        """
        self.trace(INDENT + inspect.stack()[0][3] + "()")
        self.cmd("devices device %s sync-to" %
                 self.name, expect="result true")
        return self

    def commit_id_next(self, index):
        """Find next valid commit ID.

        A commit without modifications will store None in the
        commit_id list. A subsequent rollback to this id will thus do
        nothing; there is no rollback file to use. The expected
        behaviour is instead to use the next ID != None in the
        commit_id list, which is returned by this function.

        Args:
            index: start index in commit_id list
        Returns:
            first valid commit ID
        """
        for i in range(index, len(self.commit_id)):
            if self.commit_id[i]:
                return self.commit_id[i]
        return None

    def commit(self, banner=True, show_dry_run=False, no_overwrite=False, no_networking=False):
        """Commit transaction to device.

        Args:
            banner: print banner on console
        Returns:
            self
        """
        if banner:
            self.trace(INDENT + inspect.stack()[0][3] + "()")
        # Save coverage data
        xml = self._coverage()
        # Compare data if there has been a rollback
        id = self.rollback_id
        self.rollback_id = None
        if xml and id and id in self.rollback_xml and self.rollback_xml[id]:
            with open(self.rollback_xml[id]) as before, open(xml) as after:
                # Strip annotations and empty containers
                def content(f):
                    s = re.sub(r"<(\S+) (annotation|xmlns)=[^>]*>", r"<\1>", f.read())
                    for i in range(10): # Max depth 10
                        r = re.sub(r"\n\s*<(\S+)[^>]*>\s*</\1>.*", "", s)
                        if s == r:
                            break
                        else:
                            s = r
                    return sorted(s.split("\n"))
                # Do a poor man's comparison of xml, sort and compare
                if content(before) != content(after):
                    try:
                        out = subprocess.check_output("diff %s %s" %
                                                      (self.rollback_xml[id], xml), shell=True)
                    except subprocess.CalledProcessError as e:
                        out = e.output
                    print(out)
                    print("NOTE: The rollback did not restore CDB to the previous state:" +
                          " %s %s" % (self.rollback_xml[id], xml))
        # Create dry-run files
        self.dry_run(fname="drned-work/drned-dry-run.txt", banner=False)
        # Check dry-run timing
        f = [self.last_load]
        if xml and self.last_load and "logs/rollback" in self.last_load:
            f = [xml, self.last_load]
        # Update dry-run log
        with open("drned-work/drned-dry-run.txt") as inf, \
             open("drned-work/drned-dry-run-all.txt", "a") as outf:
            outf.write(inf.read())
        # Show dry run results?
        if show_dry_run:
            with open("drned-work/drned-dry-run.txt") as inf:
                print(inf.read())
        # Do compare-config before commit to compensate for the
        # removed transaction ID
        if self.use_transaction_id == False \
           and not self.use_no_networking \
           and self.saw_compare_after_commit:
            self.compare_config(banner=False)
        self.saw_compare_after_commit = False

        # The actual commit
        if no_overwrite or self.use_commit_no_overwrite:
            self.cmd("commit no-overwrite")
        elif no_networking or self.use_no_networking:
            self.cmd("commit no-networking")
        elif self.use_commit_queues:
            self.cmd("commit commit-queue sync")
        else:
            self.cmd("commit")

        # Check for out-of-sync in all commit incarnations
        self.saw_not("out of sync")

        # BEWARE TO NOT MODIFY ncs_buf BEFORE TEST BELOW!
        latest_rollback = self._get_latest_rollback()
        id = None if "No modifications to commit" in self.ncs_buf else latest_rollback
        print("NOTE: Commit id: %s" % id)
        self.commit_id.append(id)
        self._set_rollback_xml(xml)

        f = [self.last_load]
        if xml and self.last_load and "logs/rollback" in self.last_load:
            f = [xml, self.last_load]
        self.last_load = None

        # Do disconnect to force reload of NED instance variables
        if self.reconnect_required:
            print("NOTE: Disconnect to force reload of NED instance vars")
            self.cmd("devices device %s disconnect" % self.name)
            self.reconnect_required = False
        return self

    def commit_compare(self, dry_run=True):
        """Commit transaction to device, and compare afterwards.

        Args:
            dry_run: display dry-run data before committing
        Returns:
            self
        """
        # Remove old rollback file to avoid confusion
        try:
            os.remove("drned-work/drned-rollback.txt")
        except OSError:
            pass
        # Create commit log
        if dry_run:
            self.dry_run(banner=False)
        self.commit()
        shutil.copyfile("drned-work/drned-dry-run.txt", "drned-work/drned-load.txt")
        self.compare_config()
        return self

    def dry_run(self, outformat="native", fname=None, banner=True):
        """Show the transaction that a commit would write to the device.

        Args:
            outformat: output format
            fname: write to this file instead of the console
            banner: print banner on console
        Returns:
            self
        """
        if banner:
            self.trace(INDENT + inspect.stack()[0][3] + "()")
        fmt = ("" if outformat == None else " outformat " + outformat)
        if fname == None:
            # Use file also when printing to console, the dry-run data
            # may contain prompt patterns
            save = " | save overwrite drned-work/tmp-dry-run.txt"
        else:
            save = " | exclude \"device %s\" | save overwrite %s" % \
                   (self.name, fname)
        self.cmd("commit dry-run %s %s" % (fmt, save))
        if fname == None:
            with open("drned-work/tmp-dry-run.txt", "r") as f:
                print(f.read())
            os.remove("drned-work/tmp-dry-run.txt")
        return self

    def rollback(self, id=-1, banner=True):
        """Rollback the configuration to a previous state.

        Args:
            id: rollback to this id, default: last commit
            banner: print banner on console
        Returns:
            self
        """
        if banner:
            self.trace(INDENT + inspect.stack()[0][3] + "()")
        if id == -1:
            self.rollback_id = self._get_latest_rollback()
            self.cmd("rollback configuration")
        elif id:
            self.rollback_id = id
            self.cmd("rollback configuration %s" % id)
        else:
            self.rollback_id = None
            print("NOTE: No rollback since commit was empty")
        self.last_load = None if not self.rollback_id \
                         else "drned-ncs/logs/rollback%s" % self.rollback_id
        return self

    def rollback_compare(self, id=-1, dry_run=True):
        """Rollback the configuration to a previous state and compare.

        Args:
            id: rollback to this id, default: last commit
            dry_run: display dry-run data before committing
        Returns:
            self
        """
        self.rollback(id=id)
        if dry_run:
            self.dry_run(banner=False)
        self.commit()
        shutil.copyfile("drned-work/drned-dry-run.txt", "drned-work/drned-rollback.txt")
        self.compare_config()
        return self

    def compare_config(self, banner=True):
        """Compare the NCS view of the configuration with the device itself.

        Args:
            none
        Returns:
            self
        """
        if self.use_no_networking:
            return self
        if banner:
            self.trace(INDENT + inspect.stack()[0][3] + "()")
        self.cmd("devices device %s compare-config" % self.name)
        self.saw_not("\ndiff")
        self.saw_compare_after_commit = True
        return self

    def check_sync(self):
        """Compare NCS transaction ID with the device.

        Args:
            none
        Returns:
            self
        """
        self.trace(INDENT + inspect.stack()[0][3] + "()")
        self.cmd("devices device %s check-sync" % self.name)
        self.saw_not("out-of-sync")
        return self

    def commit_rollback(self, dry_run=True):
        """Do a commit and rollback with compare-config steps inbetween.

        Args:
            dry_run: display dry-run data before committing
        Returns:
            self
        """
        # Commit-rollback cycle with compare-config
        self.commit_compare(dry_run=dry_run)
        self.rollback_compare(dry_run=dry_run)
        return self

    def show(self, cmdstr, fname=None, echo=True):
        """Do a show command and display the result.

        Args:
            cmdstr: the command to run
            echo: print command output
        Returns:
            self
        """
        # Use file since the output may contain prompt patterns
        if echo:
            print(cmdstr)
        outf = fname if fname else "drned-work/tmp-show.txt"
        self.cmd("%s | save overwrite %s" % (cmdstr, outf), echo=False)
        if not fname:
            with open(outf, "r") as f:
                print(f.read())
            os.remove(outf)
        return self

    def cmd(self, cmdstr, prompt=None, expect=None, expect_not=None,
            lf=True, echo=True):
        """Do a NCS CLI command and check for errors.

        Args:
            cmdstr: the command to run
            prompt: the prompt to wait for, default: NCS prompt combo
            expect: require this string to be in the output
            expect_not: require this string to not be in the output
                        (if None given, fails on a set of fixed 'bad' words, such as '[Ee]rror')
            lf: send a linefeed at the end of the command
            echo: print command output
        Returns:
            self
        """
        # Get the entire chunk of output at once, and do not expect
        # anything inbetween
        with open("drned-work/stdin.txt", "a") as f:
            f.write("%s%s" % (cmdstr, "\n" if lf else ""))
        if self.verbose:
            print(">>>> %s >>>>" % cmdstr)
        if lf:
            self.ncs.sendline(cmdstr)
        else:
            self.ncs.send(cmdstr)
        self.ncs_buf = ""
        self.last_prompt = None
        while True:
            e = self.ncs.expect(prompt if prompt
                                else ["[^ ]# ", "--More--", "[\]\)\n]: "],
                                timeout=self.tmo+60)
            ncs_buf_raw = self.ncs.before + self.ncs.after
            with open("drned-work/stdout.txt", "a") as f:
                f.write(ncs_buf_raw)
            if self.verbose:
                print("<<<< %d: %s <<<<" % (e, ncs_buf_raw))
            found_prompt = re.match(".*?(\([^\)]+\)#)",
                                    ncs_buf_raw, re.MULTILINE + re.DOTALL)
            if found_prompt:
                self.last_prompt = found_prompt.group(1)
            # Alarms give an extra prompt and must be ignored
            if self.ncs.before.find("ALARM") >= 0:
                continue
            # Remove \r, \b and prompt to unclutter log
            self.ncs.before = self.ncs.before.replace("\r", "")
            self.ncs.before = self.ncs.before.replace("\b", "")
            if prompt is None:
                self.ncs.before = re.sub("\\n[^\\n]*$", "", self.ncs.before)
            else:
                self.ncs.before = re.sub("\\n%s$" % prompt, "", self.ncs.before)
            self.ncs_buf += (("" if self.ncs_buf == "" else "\n") +
                             self.ncs.before)
            if e == 0:
                # Done
                break
            if e == 1:
                # More to come
                self.ncs.send(" ")
            if e == 2:
                # Prompt for value
                print(self.ncs_buf)
                pytest.fail("Received something that seems like a prompt " +
                            "for more input: '%s'\nPROMPT" % ncs_buf_raw)
        if echo:
            print(self.ncs_buf)
        if expect_not != None:
            self.saw_not(expect_not)
        else:
            # Always use fixed set of error msgs if none given
            self.saw_not("((ERROR|[Ee]rror|[Ff]ailed|[Aa]borted):)|([Ee]rror when|[Ee]xternal error|[Ii]nternal error)")
        if expect != None:
            self.saw(expect)
        return self

    def saw(self, regex):
        """Check that expected output from the last command actually was there.

        Args:
            regex: regular expression to match
        Returns:
            self
        """
        if not re.search(regex, self.ncs_buf):
            pytest.fail("Did expect \"%s\" in:\n%s" %
                        (regex, self.ncs_buf))
        return self

    def saw_not(self, regex):
        """Check that unexpected output from the last command wasn't there.

        Args:
            regex: regular expression to match
        Returns:
            self
        """
        if re.search(regex, self.ncs_buf):
            pytest.fail("Did not expect \"%s\" in:\n%s" %
                        (regex, self.ncs_buf))
        return self

    def buf(self):
        """Return the output from the last NCS command.

        Args:
            none
        Returns:
            command output
        """
        return self.ncs_buf

    def trace(self, s):
        """Log text to console and dry-run file.

        Args:
            s: log text
        Returns:
            nothing
        """
        print(s)
        with open("drned-work/drned-dry-run-all.txt", "a") as f:
            f.write(s + "\n")

    def _set_rollback_xml(self, xml):
        next_rollback = str(int(self._get_latest_rollback()) + 1)
        if next_rollback not in self.rollback_xml:
            self.rollback_xml[next_rollback] = xml

    def _get_latest_rollback(self):
        return subprocess.check_output(
            "ls -1rt drned-ncs/logs/rollback* | tail -1", shell=True) \
                         .replace("drned-ncs/logs/rollback", "") \
                         .replace(".prepare", "") \
                         .strip()

    def _coverage(self):
        xml = None
        if not hasattr(self, "covsession"):
            return xml
        with tempfile.NamedTemporaryFile(dir="drned-work/coverage/%s" %
                                         self.covsession,
                                         prefix=str(int(time.time() * 1000)),
                                         suffix=".xml",
                                         delete=False) as temp:
            xml = temp.name
            self.save(xml, fmt="xml", banner=False)

        return xml

    def _new_device_name(self, name, temp, remove=False, ancient=False):
        """Rename or remove device name from config file.

        Args:
            name: input file name
            temp: output file handle
            remove: remove device name, otherwise just rename
            ancient: use pre-NCS3.2 SSH setup
        Returns:
            output file name
        """
        did_header = False
        if name.endswith(".xml"):
            dir = os.path.dirname(name)
            # Header file provided
            if os.path.isfile("%s/header.xmlh" % dir):
                # Yes, use it
                with open ("%s/header.xmlh" % dir, "r") as f:
                    header = f.read()
                with open (name, "r") as f:
                    data = f.read()
                temp.write(header % (self.name, data))
                did_header = True
            else:
                # No, replace device name
                root = etree.parse(name)
                dev = root.xpath('//ns:device/ns:name',
                                 namespaces={'ns':'http://tail-f.com/ns/ncs'})
                dev[0].text = self.name
                temp.write(etree.tostring(root, pretty_print=True))
        else:
            with open(name) as n:
                lines = n.read().splitlines(True)
                if ancient:
                    lines = [line for line in lines
                             if not re.search("^\\s*ssh host-key\\s+", line)
                             and not re.search("^\\s*key-data\\s+", line)]
                if remove:
                    lines = [line for line in lines
                             if not re.search("^\\s*devices\\s+device\\s+\\S+",
                                              line)
                             and not re.search("^\\s*config\\s*$", line)]
                else:
                    lines = [re.sub("^\\s*devices\\s+device\\s+\\S+",
                                    "devices device %s" % self.name,
                                    line) for line in lines]
                temp.writelines(lines)
        temp.flush()
        # Check if anything has changed
        if not filecmp.cmp(name, temp.name):
            # Check for .load file
            if os.path.isfile("%s.load" % name):
                with open("%s.load" % name, "r") as f:
                    load = f.read()
                    lscrub = re.search("^\\s*scrub\\s*=\\s*(\\S+)",
                                       load, re.MULTILINE)
                    if lscrub and lscrub.group(1) == "false":
                        # No scrubbing selected in .load file
                        return name
                # Copy .load file to new location
                shutil.copy("%s.load" % name, "%s.load" % temp.name)
            print("NOTE: Modifying file before load")
            if not did_header:
                os.system("diff %s %s" % (name, temp.name))
            return temp.name
        # No change, use original file
        return name
