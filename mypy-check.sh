MYPY_STUBS="python/stubs"

MYPY_ARGS=""
MYPY_ARGS+=" --strict"
MYPY_ARGS+=" --follow-imports=normal"
MYPY_ARGS+=" --implicit-reexport"
MYPY_ARGS+=" --ignore-missing-imports"
MYPY_ARGS+=" --namespace-packages"

MYPY_TARGETS=""
MYPY_TARGETS+=" drned-skeleton"
MYPY_TARGETS+=" python/drned_xmnr"

MYPYPATH="${MYPY_STUBS}" mypy ${MYPY_ARGS} ${MYPY_TARGETS}
