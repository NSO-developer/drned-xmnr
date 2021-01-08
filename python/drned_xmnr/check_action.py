import os
import sys
import importlib

from ncs import application

if sys.version_info < (3, 0):
    FileNotFoundError = IOError
    ModuleNotFoundError = ImportError

REQ_GE = '>='

REQ_DEFAULTS = [
    ('pexpect', None),
    ('pytest', (3, 0)),
    ('lxml', None)]


class XmnrCheckException(Exception):
    pass


def parse_version(verstr):
    return [int(vnum) for vnum in verstr.split('.')]


class XmnrCheck(application.Application):
    def setup(self):
        if sys.version_info < (2, 7) or \
           sys.version_info >= (3, 0) and sys.version_info < (3, 6):
            raise XmnrCheckException('Required Python 2.7 or 3.6 or newer')
        for (package, version) in self.xmnr_requirements():
            try:
                mod = importlib.import_module(package)
            except ModuleNotFoundError:
                errmsg = 'XMNR cannot run without the package {}'.format(package)
                raise XmnrCheckException(errmsg)
            if version is not None:
                imported_version = parse_version(mod.__version__)
                if imported_version < version:
                    version_str = '.'.join(map(str, version))
                    raise XmnrCheckException('Required {}>={}'.format(package, version_str))

    def xmnr_requirements(self):
        base = os.path.realpath(os.path.dirname(__file__))
        pkg_path = os.path.dirname(os.path.dirname(base))
        try:
            with open(os.path.join(pkg_path, 'requirements.txt')) as reqs:
                for req_line in reqs:
                    req = req_line[:-1]
                    # only REQ_GE supported
                    if REQ_GE in req:
                        [pkg, verstr] = req.split(REQ_GE)
                        yield pkg, parse_version(verstr)
                    else:
                        yield req, None
        except FileNotFoundError:
            self.log.info('no requirements file found at {}, using defaults'.format(base))
            for p in REQ_DEFAULTS:
                yield p
