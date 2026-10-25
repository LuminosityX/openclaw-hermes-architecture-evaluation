ALLOWED = {"todo": {"doing"}, "doing": {"done", "todo"}, "done": set()}
def can_transition(source, target):
    return source in ALLOWED and target in ALLOWED and (source == target or target in ALLOWED[source])
