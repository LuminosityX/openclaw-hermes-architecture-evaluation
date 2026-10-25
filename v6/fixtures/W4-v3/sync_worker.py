import argparse,json,urllib.request
p=argparse.ArgumentParser();p.add_argument('--base-url',required=True);p.add_argument('--output',required=True);a=p.parse_args()
data=json.load(urllib.request.urlopen(a.base_url+'/orders'));json.dump({'rows':len(data.get('items',[]))},open(a.output,'w'))
