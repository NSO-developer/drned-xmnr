set -e
FLAKE8_ARGS="--count --max-line-length=120 --statistics"
flake8 ${XMNR_DIR}/python ${XMNR_DIR}/test/unit/ ${FLAKE8_ARGS} --show-source
flake8 ${XMNR_DIR}/python ${XMNR_DIR}/test/unit/ ${FLAKE8_ARGS} --exit-zero --max-complexity=25
