APP_DIR = erlang-lib/ec_transform
HRL_DIR = $(APP_DIR)/include
USERS_HRL = $(HRL_DIR)/users.hrl

AAA_HDR = tailf-aaa.hrl ietf-netconf-acm.hrl

all: hdr

hdr: $(AAA_HDR) $(USERS_HRL)
	$(MAKE) -C $(APP_DIR) all


$(AAA_HDR): %.hrl: $(CONFD_DIR)/etc/confd/%.fxs
	$(CONFDC) --emit-hrl $@ $<

$(USERS_HRL): users.fxs
	$(CONFDC) --emit-hrl $@ $<

install: erl-install

erl-install:
	cp -r erlang-lib $${DEST_DIR}

clean: erl-clean

erl-clean:
	@rm -f *.hrl $(USERS_HRL)
	$(MAKE) -C $(APP_DIR) clean
