# Include standard NCS examples build definitions and rules
include $(NCS_DIR)/src/ncs/build/include.ncs.mk

SRC = $(wildcard yang/*.yang)
FXS = $(SRC:yang/%.yang=../load-dir/%.fxs)

CLI = $(wildcard *.cli)
CCL = $(CLI:%.cli=../load-dir/%.ccl)

../load-dir/%.ccl:	%.cli
	$(NCSC) -c $< -o $@

py:
	PYTHONPATH=../python:$$PYTHONPATH python ../python/drned_xmnr/action.py

../load-dir/%.fxs:	yang/%.yang
	$(NCSC)  `ls $*-ann.yang  > /dev/null 2>&1 && echo "-a $*-ann.yang"` \
             $(YANGPATH) -c -o $@ $<
	$(NCSC) --emit-python ../python/drned_xmnr/namespaces/$(notdir $(basename $<)).py $@
	test -f ../python/drned_xmnr/namespaces/__init__.py || touch ../python/drned_xmnr/namespaces/__init__.py

all:	$(FXS) $(CCL) py

clean:
	rm -rf  ../load-dir/* ../python/drned_xmnr/namespaces/*.py
	rm -rf  ./src/*/*.pyc
