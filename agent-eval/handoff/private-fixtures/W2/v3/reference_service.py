from .model import ALLOWED, can_transition
def transition_many(store, ids, target):
    if target not in ALLOWED:
        raise ValueError("unknown target")
    if not isinstance(ids, (list, tuple)) or any(not isinstance(x, str) for x in ids):
        raise ValueError("ids must be a list or tuple of strings")
    unique = list(dict.fromkeys(ids))
    staged = []
    for ident in unique:
        item = store.get(ident)
        if not can_transition(item["status"], target):
            raise ValueError("invalid transition")
        item["status"] = target
        staged.append(item)
    for item in staged:
        store.save(item)
    return [store.get(x) for x in unique]
