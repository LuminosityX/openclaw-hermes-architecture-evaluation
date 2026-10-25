import copy,random,sys,unittest
sys.path.insert(0,sys.argv.pop(1))
from pagination import paginate
class HiddenTests(unittest.TestCase):
    def test_cases(self):
        rng=random.Random(102)
        for _ in range(50):
            n=rng.randint(0,31);size=rng.randint(1,9);page=rng.randint(1,12)
            items=[{"key":rng.randint(0,1000)} for _ in range(n)];before=copy.deepcopy(items)
            expected={"items":items[(page-1)*size:page*size],"total_pages":(n+size-1)//size,"has_next":page<(n+size-1)//size}
            self.assertEqual(paginate(items,page,size),expected)
            self.assertEqual(items,before)
            self.assertEqual(paginate(tuple(items),page,size),expected)
    def test_invalid(self):
        for bad in [0,-1,True,False,1.5,"2",None]:
            with self.assertRaises(ValueError):paginate([1],bad,2)
            with self.assertRaises(ValueError):paginate([1],1,bad)
if __name__=="__main__":unittest.main()
