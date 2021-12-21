import os
import coverage


def lookup_path(filename):
    if '/namespaces/' in filename:
        return -1
    ix = filename.find('python/drned_xmnr/')
    if ix == -1:
        ix = filename.find('drned-skeleton/')
    return ix


class CovTracer(coverage.FileTracer):
    def __init__(self, root, filename, full_filename):
        self.filename = filename
        self.full_filename = full_filename

    def source_filename(self):
        return self.full_filename


class CovPlugin(coverage.CoveragePlugin):
    def __init__(self, root):
        self.root = root

    def file_tracer(self, filename):
        ix = lookup_path(filename)
        if ix != -1:
            full_filename = os.path.join(self.root, filename[ix:])
            return CovTracer(self.root, filename, full_filename)
        return None

    def file_reporter(self, filename):
        ix = lookup_path(filename)
        if ix != -1:
            return 'python'
        return None


def coverage_init(reg, options):
    root = os.environ.get('XMNR_ROOT')
    reg.add_file_tracer(CovPlugin(root))
