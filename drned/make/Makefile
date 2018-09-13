# Create drned symlinks
symlinks:
	rm -f conftest.py && ln -s $(abspath $(DRNED))/adm/conftest.py conftest.py
	rm -f setup.cfg && ln -s $(abspath $(DRNED))/adm/setup.cfg setup.cfg
	rm -f src/test_builtin.py \
	    &&  ln -s $(abspath $(DRNED))/adm/test_builtin.py src/test_builtin.py
.PHONY: symlinks

# Create environment script
env.sh: symlinks
	@echo 'export DRNED="$(abspath $(DRNED))"' > $@
	@echo 'export PYTHONPATH="$(abspath $(DRNED))":$${PYTHONPATH}' >> $@
	@echo 'export PYTHONPATH="$${PYTHONPATH}":$${NCS_DIR}/lib/pyang' >> $@
	@echo 'export PATH="$${PATH}":$(abspath $(DRNED))/bin' >> $@
.PHONY: env.sh

# Prepare for collection of test coverage data
covstart:
	rm -rf drned-work/coverage
	mkdir -p drned-work/coverage
.PHONY: covstart
