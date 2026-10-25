import copy,sys,unittest
sys.path.insert(0,sys.argv.pop(1))
from queueboard.model import can_transition
from queueboard.store import TaskStore
from queueboard.service import transition_many
class HiddenTests(unittest.TestCase):
    def fresh(self):return TaskStore([{"id":"a1","status":"todo","title":"A","extra":7},{"id":"b1","status":"doing","title":"B"},{"id":"c1","status":"done","title":"C"}])
    def test_model(self):
        for s in ["todo","doing","done","bad"]:
            for t in ["todo","doing","done","bad"]:
                good=s in ("todo","doing","done") and t in ("todo","doing","done") and (s==t or (s,t) in [("todo","doing"),("doing","todo"),("doing","done")])
                self.assertEqual(can_transition(s,t),good)
    def test_order_and_fields(self):
        s=self.fresh();r=transition_many(s,["b1","a1","b1"],"doing")
        self.assertEqual([x["id"] for x in r],["b1","a1"]);self.assertEqual(s.get("a1")["extra"],7)
        r[1]["title"]="bad";self.assertEqual(s.get("a1")["title"],"A")
    def test_atomic(self):
        for ids,target,exc in [(["a1","missing"],"doing",KeyError),(["a1","c1"],"doing",ValueError),(["a1"],"unknown",ValueError)]:
            s=self.fresh();before=s.all()
            with self.assertRaises(exc):transition_many(s,ids,target)
            self.assertEqual(s.all(),before)
    def test_inputs(self):
        for ids in ["a1",[1],None]:
            with self.assertRaises(ValueError):transition_many(self.fresh(),ids,"doing")
        self.assertEqual(transition_many(self.fresh(),[],"todo"),[])
        with self.assertRaises(ValueError):transition_many(self.fresh(),[],"bad")
if __name__=="__main__":unittest.main()
