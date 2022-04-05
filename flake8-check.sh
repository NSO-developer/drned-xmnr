set -e
FLAKE8_ARGS="--count --max-line-length=120 --statistics --exclude namespaces"
FLAKE8_CMD="flake8 ${XMNR_DIR}/python/drned_xmnr ${XMNR_DIR}/drned-skeleton ${XMNR_DIR}/test/unit/ ${FLAKE8_ARGS}"
${FLAKE8_CMD} --show-source
${FLAKE8_CMD} --exit-zero --max-complexity=25
