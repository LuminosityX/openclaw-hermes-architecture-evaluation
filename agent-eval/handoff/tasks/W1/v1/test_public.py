import unittest
from pagination import paginate
class PublicTests(unittest.TestCase):
    def test_shape(self):
        result=paginate([1,2,3,4,5,6],1,2)
        self.assertEqual(set(result),{"items","total_pages","has_next"})
        self.assertLessEqual(len(result["items"]),2)
    def test_invalid(self):
        with self.assertRaises(ValueError):paginate([1],0,1)
if __name__=="__main__":unittest.main()
