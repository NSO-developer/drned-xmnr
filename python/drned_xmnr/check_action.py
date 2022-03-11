import os
import sys
import importlib

from typing import Iterator, List, Optional, Tuple
from ncs.log import Log

Version = List[int]
Requirement = Tuple[str, Optional[Version]]

REQ_GE = '>='

REQ_DEFAULTS: List[Requirement] = [
    ('pexpect', None),
    ('pytest', [3, 0]),
    ('lxml', None)]


class XmnrCheckException(Exception):
    pass


def parse_version(verstr: str) -> Version:
    return [int(vnum) for vnum in verstr.split('.')]


def check(log: Optional[Log] = None) -> None:
    if sys.version_info < (3, 6):
        raise XmnrCheckException('Required Python 3.6 or newer')
    for (package, version) in xmnr_requirements(log):
        try:
            mod = importlib.import_module(package)
        except ModuleNotFoundError as ex:
            if package == 'pyang':
                if log is not None:
                    log.warning('running without pyang')
            else:
                errmsg = 'XMNR cannot run without the package {}'.format(package)
                raise XmnrCheckException(errmsg) from ex
        modversion = getattr(mod, '__version__', None)
        if version is not None and modversion is not None:
            imported_version = parse_version(modversion)
            if imported_version < version:
                version_str = '.'.join(map(str, version))
                raise XmnrCheckException('Required {}>={}'.format(package, version_str))
            if log is not None:
                log.debug('using package {} ({})'.format(package, imported_version))
        else:
            if log is not None:
                log.debug('using package {}'.format(package))


def xmnr_requirements(log: Optional[Log]) -> Iterator[Requirement]:
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
        if log is not None:
            log.info('no requirements file found at {}, using defaults'.format(base))
        for p in REQ_DEFAULTS:
            yield p


check()
