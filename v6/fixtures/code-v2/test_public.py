import unittest
from ledger import reconcile
class Smoke(unittest.TestCase):
 def test_empty(self):self.assertEqual(reconcile([]),{'orders':[],'rejected':[],'totals':[]})
if __name__=='__main__':unittest.main()
