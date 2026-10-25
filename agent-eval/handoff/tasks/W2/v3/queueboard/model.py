ALLOWED = {"todo": {"doing"}, "doing": {"done", "todo"}, "done": set()}
def can_transition(source, target):
    return source == target
