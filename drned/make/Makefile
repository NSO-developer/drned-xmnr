NCSVER := $(shell ncsc --version 2> /dev/null)

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


yanger_plugins: $(DRNED)/yanger/plugins/$(NCSVER)/yangdiff.beam
.PHONY: yanger_plugins

YPLUGIN_SRC := $(DRNED)/yanger/yangdiff.erl $(DRNED)/yanger/jsondump.erl
$(DRNED)/yanger/plugins/$(NCSVER)/yangdiff.beam: $(DRNED)/yanger/hrl/$(NCSVER) $(YPLUGIN_SRC)
	@mkdir -p $(DRNED)/yanger/plugins/$(NCSVER)
	@if [ -f "$$NCS_DIR/erlang/yanger/include/yang.hrl" ]; then \
	    echo 'Found yang.hrl in NSO dist'; \
	    erlc -I "$$NCS_DIR/erlang/" -o $(DRNED)/yanger/plugins/$(NCSVER) $(DRNED)/yanger/jsondump.erl ;\
	    erlc -I "$$NCS_DIR/erlang/" -o $(DRNED)/yanger/plugins/$(NCSVER) $(DRNED)/yanger/yangdiff.erl ;\
	else \
	    echo 'No yang.hrl in NSO dist, using local'; \
	    erlc -I $(DRNED)/yanger/hrl/$(NCSVER) -o $(DRNED)/yanger/plugins/$(NCSVER) $(DRNED)/yanger/jsondump.erl ;\
	    erlc -I $(DRNED)/yanger/hrl/$(NCSVER) -o $(DRNED)/yanger/plugins/$(NCSVER) $(DRNED)/yanger/yangdiff.erl ;\
	fi
