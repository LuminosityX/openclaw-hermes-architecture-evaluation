from copy import deepcopy
class TaskStore:
    def __init__(self,tasks): self._tasks={x["id"]:deepcopy(x) for x in tasks}
    def get(self,ident): return deepcopy(self._tasks[ident])
    def save(self,item): self._tasks[item["id"]]=deepcopy(item)
    def all(self): return [deepcopy(x) for x in self._tasks.values()]
