install: all

all: $(FXS) hooks

INCLUDE += -I.

hooks.o: hooks.h

hooks: hooks.o
	$(CC) -o $@ $^ $(LIBS)

EXTRA_FILES += hooks
