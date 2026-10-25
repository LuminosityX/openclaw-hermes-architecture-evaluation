import unittest
from queueboard.store import TaskStore
class PublicTests(unittest.TestCase):
    def test_store_copy(self):
        s=TaskStore([{"id":"a","status":"todo","title":"keep"}]);x=s.get("a");x["title"]="changed"
        self.assertEqual(s.get("a")["title"],"keep")
if __name__=="__main__":unittest.main()
