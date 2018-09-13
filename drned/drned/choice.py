
class Choice(object):
    def __init__(self, children, name):
        self.children = {}
        self.indexes = {}
        self.add(children, name)
        self.done = False

    def add(self, children, name):
        if name not in self.children:
            self.children[name] = children
            self.indexes[name] = 0

    def current(self, name):
        return self.children[name][self.indexes[name]]

    def joined(self, child, name):
        return self.current(name) == child

    def increment(self):
        for name in self.children:
            current = self.current(name)
            if current and not current.all_done():
                return False
            # Increment index
            self.indexes[name] += 1
            if self.indexes[name] >= len(self.children[name]):
                self.indexes[name] = 0
                self.done = True
            else:
                return True
        return False

def get_choice(choices, path, children, name):
    if path in choices:
        choice = choices[path]
        choice.add(children, name)
    else:
        choice = Choice(children, name)
        choices[path] = choice
    return choice
