from common.test_here import *  # noqa
from common.test_template import *  # noqa


def test_coverage(fname, argv, all, devname, yangpath=""):
    tc = __import__('common.test_coverage')
    tc.test_coverage.test_coverage(fname, argv, all, devname,
                                   yangpath=yangpath)
